"""
此模块负责将抽象的拓扑模型（Topology）实例化为具体的Docker容器和网络。
"""
import docker
import logging
import shutil
import re
import json
import io
import tarfile
from pathlib import Path
from .topology import Topology
from .abstractions import Node, Link, Interface


class DockerController:
    """
    管理将拓扑模型部署为Docker容器和网络。
    """

    def __init__(self, topology: Topology, config_root_dir: str = "runtime_configs"):
        self.topology = topology
        self.client = docker.from_env()
        self.logger = logging.getLogger('VortinetCore.DockerController')
        self.group_label = "vortinet_simulation"
        self.config_root_dir = Path(config_root_dir)
        self._created_networks = {}  # key: link_name, value: docker_network_obj
        self._created_containers = {}  # key: node_name, value: docker_container_obj

    def _get_base_image(self, dockerfile_path: Path) -> str | None:
        """解析Dockerfile以找到基础镜像 (FROM指令)。"""
        if not dockerfile_path.exists():
            return None

        try:
            with open(dockerfile_path, 'r', encoding='utf-8') as f:
                for line in f:
                    match = re.match(r'^\s*FROM\s+(--platform=\S+\s+)?([\w\d/:-]+)', line, re.IGNORECASE)
                    if match:
                        return match.group(2)
        except Exception as e:
            self.logger.error(f"读取Dockerfile失败 {dockerfile_path}: {e}")

        return None

    def _build_image(self, image_tag: str, build_info: dict):
        """构建单个Docker镜像。"""
        self.logger.info(f"-> 开始构建镜像: {image_tag}")
        build_context_path = build_info.get('path')
        dockerfile_rel_path = build_info.get('dockerfile')

        if not build_context_path or not dockerfile_rel_path:
            self.logger.error(f"镜像 {image_tag} 的构建信息不完整，缺少路径或Dockerfile名称。")
            return

        try:
            # path: 构建上下文的路径
            # dockerfile: 相对于构建上下文的Dockerfile路径
            self.logger.info(f"  [BUILD] Context: {Path(__file__).parent.parent / build_context_path}")
            self.logger.info(f"  [BUILD] Dockerfile: {dockerfile_rel_path}")

            # 为build操作增加超时设置，防止无限期挂起
            api_client = docker.APIClient()
            build_log_generator = api_client.build(
                path=str(Path(__file__).parent.parent / build_context_path),
                dockerfile=dockerfile_rel_path,
                tag=image_tag,
                rm=True,
                timeout=300  # 设置300秒超时
            )

            for chunk in build_log_generator:
                # docker-py返回的日志是bytes类型，需要解码
                # 同时处理单行和多行JSON的情况
                lines = chunk.decode('utf-8').strip().split('\n')
                for line in lines:
                    try:
                        log_entry = json.loads(line)
                        if 'stream' in log_entry:
                            self.logger.info(f"    [BUILD] {log_entry['stream'].strip()}")
                        elif 'error' in log_entry:
                            self.logger.error(f"    [BUILD ERROR] {log_entry['error']}")
                        elif 'status' in log_entry:
                            self.logger.info(f"    [BUILD STATUS] {log_entry['status']}")
                    except json.JSONDecodeError:
                        self.logger.info(f"    [BUILD RAW] {line}")

            # 重新获取镜像对象以确认构建成功
            self.client.images.get(image_tag)
            self.logger.info(f"-> 镜像 {image_tag} 构建成功。")
        except docker.errors.BuildError as e:
            self.logger.error(f"构建镜像 {image_tag} 失败: {e}")
            for chunk in e.build_log:
                if 'stream' in chunk:
                    self.logger.error(f"    [BUILD ERROR] {chunk['stream']}")
            raise

    def provision(self):
        """
        根据拓扑模型，预创建所有的Docker网络和容器。
        """
        self.logger.info("开始预配置Docker环境...")

        # 1. 检查并按需构建镜像
        self.logger.info("--- 步骤 1: 检查并构建自定义镜像 ---")

        # 定义基础镜像信息
        base_image_tag = 'vortinet_base:latest'
        base_build_info = {
            'path': './dockerfile/vortinet_base',
            'dockerfile': 'Dockerfile'  # 相对于path的路径
        }

        # 首先，确保基础镜像存在
        try:
            self.client.images.get(base_image_tag)
            self.logger.info(f"-> 基础镜像 {base_image_tag} 已存在。")
        except docker.errors.ImageNotFound:
            self.logger.info(f"-> 基础镜像 {base_image_tag} 未找到，将进行构建。")
            self._build_image(base_image_tag, base_build_info)

        # 然后，构建拓扑中明确使用的其他镜像
        unique_images_in_topo = {node.attributes.get('image'): node.attributes.get('build')
                                 for node in self.topology.nodes.values()
                                 if node.attributes.get('build') and node.attributes.get('image')}

        for image_tag, build_info in unique_images_in_topo.items():
            if image_tag == base_image_tag:
                continue  # 基础镜像已处理，跳过

            try:
                self.client.images.get(image_tag)
                self.logger.info(f"-> 镜像 {image_tag} 已存在，无需构建。")
            except docker.errors.ImageNotFound:
                self.logger.info(f"-> 镜像 {image_tag} 未找到，将进行构建。")
                self._build_image(image_tag, build_info)

        self.logger.info("镜像检查和构建完成。")

        # 2. 创建网络
        self.logger.info("--- 步骤 2: 创建Docker网络 ---")
        for link_name, link in self.topology.links.items():
            self._create_docker_network(link)
        self.logger.info("网络创建完成。")

        # 3. 创建容器
        self.logger.info("--- 步骤 3: 创建Docker容器 ---")
        for node_name, node in self.topology.nodes.items():
            self._create_docker_container(node)
        self.logger.info("Docker环境预配置完成。")

    def _create_docker_network(self, link: Link):
        """为单个链路创建Docker网络。"""
        net_name = f"vortinet_{link.name}"
        try:
            network = self.client.networks.create(
                name=net_name,
                driver="bridge",
                labels={"group": self.group_label, "link_name": link.name},
                ipam=docker.types.IPAMConfig(
                    pool_configs=[docker.types.IPAMPool(subnet=str(link.subnet))]
                )
            )
            self._created_networks[link.name] = network
            self.logger.info(f"-> 网络 {net_name} ({link.subnet}) 已创建。")
        except docker.errors.APIError as e:
            self.logger.error(f"创建网络 {net_name} 失败: {e}")
            raise

    def _create_docker_container(self, node: Node):
        """为单个节点创建Docker容器，并处理配置。"""
        container_name = f"vortinet_{node.name}"
        image = node.attributes.get('image', 'ubuntu:latest')
        command = node.attributes.get('command', "sh -c 'tail -f /dev/null'")

        # 检查节点是否需要生成配置
        if hasattr(node, 'generate_config') and callable(node.generate_config):
            node_config_dir = self.config_root_dir / node.name
            if node_config_dir.exists():
                shutil.rmtree(node_config_dir)
            node_config_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"为节点 {node.name} 生成配置文件于 {node_config_dir}")
            node.generate_config(str(node_config_dir.resolve()))

        try:
            container = self.client.containers.create(
                image=image,
                name=container_name,
                detach=True,
                tty=True,
                command=command,
                labels={"group": self.group_label, "node_name": node.name},
                cap_add=["NET_ADMIN", "NET_RAW", "SYS_ADMIN"],
                # 不再使用volumes挂载配置
            )
            self._created_containers[node.name] = container
            self.logger.info(f"-> 容器 {container_name} ({image}) 已创建。")
        except docker.errors.APIError as e:
            self.logger.error(f"创建容器 {container_name} 失败: {e}")
            raise

    def _copy_config_to_container(self, node: Node, container):
        """将配置文件复制到容器中。"""
        if hasattr(node, 'generate_config') and callable(node.generate_config):
            node_config_dir = self.config_root_dir / node.name
            if not node_config_dir.is_dir():
                return

            self.logger.info(f"-> 正在将配置从 {node_config_dir} 复制到容器 {container.name} 的根目录")

            # 创建一个内存中的tar归档
            tar_stream = io.BytesIO()
            with tarfile.open(fileobj=tar_stream, mode='w') as tar:
                for item in node_config_dir.rglob('*'):
                    arcname = item.relative_to(node_config_dir).as_posix()
                    tar.add(str(item), arcname=arcname)

            tar_stream.seek(0)
            if container.put_archive(path='/', data=tar_stream):
                self.logger.info(f"  -> 配置成功复制到 {container.name}")
            else:
                self.logger.error(f"  -> 配置复制到 {container.name} 失败")

    def start(self):
        """
        启动所有容器，并将它们连接到正确的网络。
        """
        self.logger.info("正在启动仿真...")
        if not self._created_containers:
            self.logger.warning("没有预配置的容器，请先调用 provision()")
            return

        try:
            default_bridge = self.client.networks.get("bridge")
        except docker.errors.NotFound:
            self.logger.warning("找不到默认的 'bridge' 网络，跳过断开连接的步骤。")
            default_bridge = None

        for node_name, container in self._created_containers.items():
            node = self.topology.get_node(node_name)

            # 1. 启动容器
            container.start()
            self.logger.info(f"-> 容器 {container.name} 已启动。")

            # 1.5. 复制配置文件
            self._copy_config_to_container(node, container)

            # 2. 从默认的 bridge 网络断开，释放 eth0
            if default_bridge:
                try:
                    default_bridge.disconnect(container)
                    self.logger.info(f"-> 容器 {container.name} 已从默认 bridge 网络断开。")
                except docker.errors.APIError as e:
                    # 如果容器没有连接到bridge网络，API会返回404错误，可以安全地忽略
                    if e.response.status_code == 404 or "is not connected to network bridge" in str(e):
                        self.logger.info(f"-> 容器 {container.name} 未连接到默认 bridge 网络，无需断开。")
                    else:
                        self.logger.error(f"从默认 bridge 网络断开 {container.name} 时出错: {e}")
                        raise # 对于其他错误，重新引发异常

            # 3. 按接口名称顺序连接到拓扑中定义的网络
            sorted_interfaces = sorted(node.interfaces.items(), key=lambda item: item[0])
            for iface_name, interface in sorted_interfaces:
                link = interface.link
                if link and link.name in self._created_networks:
                    docker_network = self._created_networks[link.name]
                    self._connect_container_to_network(container, docker_network, interface)
                else:
                    self.logger.warning(f"节点 {node.name} 的接口 {iface_name} 没有连接到有效链路。")

            # 4. 清理并按需设置路由
            # a. 首先移除Docker可能添加的默认路由，确保路由表干净
            self.logger.info(f"-> 在容器 {container.name} 中清理默认路由")
            exec_result = container.exec_run("ip route del default")
            if exec_result.exit_code == 0:
                self.logger.info(f"  -> Docker 默认路由已移除。")
            else:
                output = exec_result.output.decode()
                # 如果没有默认路由，命令会失败，这是正常情况，无需警告
                if "No such process" in output or "not in table" in output:
                    self.logger.info(f"  -> 容器中没有默认路由，无需移除。")
                else:
                    self.logger.warning(f"  -> 清理默认路由时遇到问题 (退出码: {exec_result.exit_code}): {output.strip()}")

            # b. 如果节点定义了 default_gateway，则为其添加默认路由
            if 'default_gateway' in node.attributes:
                gateway_ip = node.attributes['default_gateway']
                self.logger.info(f"-> 为容器 {container.name} 添加默认网关 -> {gateway_ip}")
                command = f"ip route add default via {gateway_ip}"
                exec_result = container.exec_run(command)
                if exec_result.exit_code == 0:
                    self.logger.info(f"  -> 默认网关添加成功。")
                else:
                    self.logger.error(f"  -> 添加默认网关失败 (退出码: {exec_result.exit_code}): {exec_result.output.decode().strip()}")

            # 5. 应用TC规则
            # 再次遍历接口以应用TC规则
            for iface_name, interface in sorted_interfaces:
                if interface.link:
                    self._apply_tc_rules(container, iface_name, interface.link)

            # 6. 执行启动后命令
            if 'post_start_command' in node.attributes:
                command = node.attributes['post_start_command']
                self.logger.info(f"-> 在容器 {container.name} 中执行启动后命令: '{command}'")
                exec_result = container.exec_run(command)
                if exec_result.exit_code != 0:
                    self.logger.error(f"  -> 命令执行失败，退出码: {exec_result.exit_code}\n{exec_result.output.decode()}")
                else:
                    self.logger.info(f"  -> 命令执行成功。")

        self.logger.info("仿真启动完成。")

    def _apply_tc_rules(self, container, iface_name: str, link: Link):
        """在容器的指定接口上应用流量控制规则。"""
        if not any([link.delay, link.loss, link.bandwidth]):
            return  # 如果没有设置任何TC参数，则直接返回

        self.logger.info(f"-> 在 {container.name} 的接口 {iface_name} 上应用TC规则...")

        # 基础命令: 添加一个netem qdisc
        # 我们需要先删除接口上可能存在的任何现有qdisc
        base_cmd_delete = f"tc qdisc del dev {iface_name} root"
        container.exec_run(base_cmd_delete) # 忽略错误，因为它可能不存在

        base_cmd_add = f"tc qdisc add dev {iface_name} root netem"
        tc_options = []

        if link.delay:
            # 假设延迟格式为 "10ms"
            tc_options.append(f"delay {link.delay}")
            self.logger.info(f"  - 设置延迟: {link.delay}")

        if link.loss:
            # 假设loss为百分比，如 0.1
            tc_options.append(f"loss {link.loss}%")
            self.logger.info(f"  - 设置丢包率: {link.loss}%")

        if link.bandwidth:
            # 带宽限制需要一个不同的qdisc (tbf)，这里我们先用netem的rate
            # 注意: netem的rate功能不如TBF精确，但对于简单场景足够
            # 带宽单位是kbit
            tc_options.append(f"rate {link.bandwidth}kbit")
            self.logger.info(f"  - 设置带宽: {link.bandwidth}kbit")

        # 组合成最终命令
        full_command = f"{base_cmd_add} {' '.join(tc_options)}"
        exec_result = container.exec_run(full_command)

        if exec_result.exit_code != 0:
            self.logger.error(f"  -> 应用TC规则失败 (退出码: {exec_result.exit_code}): {exec_result.output.decode().strip()}")
        else:
            self.logger.info(f"  -> TC规则应用成功。")

    def _connect_container_to_network(self, container, network, interface: Interface):
        """将容器连接到指定的网络并配置IP。"""
        try:
            network.connect(
                container,
                ipv4_address=str(interface.ip_address)
            )
            self.logger.info(f"-> 容器 {container.name} 已连接到网络 {network.name}，IP: {interface.ip_address}")
        except docker.errors.APIError as e:
            self.logger.error(f"连接容器 {container.name} 到网络 {network.name} 失败: {e}")
            raise

    def stop_and_cleanup(self):
        """
        停止并移除所有由该控制器创建的容器和网络。
        """
        self.logger.info("开始清理环境...")
        # 清理容器
        containers = self.client.containers.list(all=True, filters={"label": f"group={self.group_label}"})
        for container in containers:
            try:
                container.stop()
                container.remove()
                self.logger.info(f"-> 容器 {container.name} 已停止并移除。")
            except docker.errors.APIError as e:
                self.logger.error(f"清理容器 {container.name} 失败: {e}")

        # 清理网络
        networks = self.client.networks.list(filters={"label": f"group={self.group_label}"})
        for network in networks:
            try:
                network.remove()
                self.logger.info(f"-> 网络 {network.name} 已移除。")
            except docker.errors.APIError as e:
                self.logger.error(f"清理网络 {network.name} 失败: {e}")

        # 清理配置文件目录
        if self.config_root_dir.exists():
            shutil.rmtree(self.config_root_dir)
            self.logger.info(f"-> 配置文件目录 {self.config_root_dir} 已移除。")

        self._created_containers.clear()
        self._created_networks.clear()
        self.logger.info("环境清理完毕。")

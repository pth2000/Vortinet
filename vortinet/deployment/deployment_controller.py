"""
部署控制器
统一管理容器创建、网络配置和资源跟踪
"""

import docker
import logging
import signal
import atexit
from typing import Dict, List, Optional, Union

from ..models.topology import Topology
from ..models.node import Node
from ..container import ContainerManager, ImageManager
from ..network import NetworkManager
from ..utils import ResourceTracker
from ..services.registry import ServiceRegistry


logger = logging.getLogger(__name__)


class DeploymentController:
    """部署控制器，统一管理容器和网络"""
    
    # 类级别的实例跟踪，用于信号处理
    _instances = []
    _signal_handlers_registered = False
    
    def __init__(
        self,
        project_name: str,
        client: Optional[docker.DockerClient] = None,
        verbose: bool = True,
        auto_cleanup: bool = True,
        log_level: int = logging.INFO
    ):
        """
        初始化部署控制器
        
        Args:
            project_name: 项目名称
            client: Docker 客户端（可选）
            verbose: 是否显示详细日志（默认 True）
            auto_cleanup: 是否在退出时自动清理（默认 True）
            log_level: 日志级别（默认 logging.INFO）
        """
        self.project_name = project_name
        self.client = client or docker.from_env()
        self.auto_cleanup = auto_cleanup
        self._cleanup_done = False
        
        # 配置日志级别
        if verbose:
            # 如果 root logger 已经配置过，basicConfig 不会生效
            # 所以我们显式设置级别，以防万一
            logging.basicConfig(
                level=log_level,
                format='%(levelname)s - %(message)s'
            )
            logging.getLogger().setLevel(log_level)
        
        # 创建资源跟踪器
        self.resource_tracker = ResourceTracker(project_name)
        
        # 创建容器和网络管理器
        self.container_manager = ContainerManager(
            self.client,
            self.resource_tracker
        )
        self.image_manager = ImageManager(self.client)
        self.network_manager = NetworkManager(
            self.resource_tracker
        )
        
        # 部署状态
        self.topology: Optional[Topology] = None
        self.deployed = False
        
        # 注册此实例用于信号处理
        DeploymentController._instances.append(self)
        
        # 首次创建时注册信号处理器和 atexit
        if not DeploymentController._signal_handlers_registered:
            self._register_signal_handlers()
            DeploymentController._signal_handlers_registered = True
    
    @classmethod
    def _register_signal_handlers(cls):
        """注册信号处理器，确保在收到 SIGTERM/SIGINT 时清理资源"""
        def signal_handler(signum, frame):
            signal_names = {
                signal.SIGTERM: "SIGTERM",
                signal.SIGINT: "SIGINT"
            }
            logger.info(f"\n收到 {signal_names.get(signum, signum)} 信号，正在清理资源...")
            logger.info(f"当前有 {len(cls._instances)} 个活动实例")
            
            # 清理所有实例
            for i, instance in enumerate(cls._instances[:], 1):
                logger.info(f"[{i}/{len(cls._instances)}] 检查实例: {instance.project_name}")
                logger.info(f"  - cleanup_done={instance._cleanup_done}, auto_cleanup={instance.auto_cleanup}")
                
                if not instance._cleanup_done and instance.auto_cleanup:
                    try:
                        session_id = instance.resource_tracker.session_id
                        logger.info(f"  - 开始清理 (session={session_id[:8]}...)")
                        instance.cleanup()
                        logger.info(f"  - 清理完成")
                    except Exception as e:
                        logger.error(f"  - 清理失败: {e}")
                        import traceback
                        traceback.print_exc()
                else:
                    logger.info(f"  - 跳过清理")
            
            cls._instances.clear()
            logger.info("所有实例清理完成，程序退出")
            
            # 正常退出
            import sys
            sys.exit(0)
        
        # 注册 SIGTERM (timeout 命令) 和 SIGINT (Ctrl+C)
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        # 注册 atexit 作为最后的保险
        atexit.register(cls._cleanup_all_instances)
    
    @classmethod
    def _cleanup_all_instances(cls):
        """清理所有活动实例"""
        for instance in cls._instances[:]:  # 复制列表以避免迭代时修改
            if not instance._cleanup_done and instance.auto_cleanup:
                try:
                    instance.cleanup()
                except Exception as e:
                    logger.error(f"清理实例 {instance.project_name} 时出错: {e}")
    
    def deploy(
        self,
        topology: Topology,
        default_image: str = "vortinet_base:latest",
        visualize: bool = True,
        save_topology: Optional[str] = None
    ):
        """
        部署拓扑
        
        Args:
            topology: 拓扑对象
            default_image: 默认镜像
            visualize: 是否在部署前显示拓扑可视化摘要
            save_topology: 如果提供路径，将拓扑保存为 Mermaid 文件 (e.g. "topology.mmd")
        """
        if self.deployed:
            raise RuntimeError("已经部署，请先清理")
        
        logger.info(f"开始部署项目 {self.project_name}")
        logger.info(f"会话 ID: {self.resource_tracker.session_id}")
        
        self.topology = topology
        
        if visualize or save_topology:
            try:
                from ..utils.visualization import TopologyVisualizer
                viz = TopologyVisualizer(topology)
                
                if visualize:
                    viz.show()
                
                if save_topology:
                    viz.save_mermaid(save_topology)
                    
            except Exception as e:
                logger.warning(f"拓扑可视化/保存失败: {e}")
        
        try:
            # 1. 创建容器
            self._create_containers(default_image)
            
            # 2. 启动容器
            self._start_containers()
            
            # 3. 配置网络
            self._setup_network()
            
            # 4. 配置默认网关
            self._setup_gateways()
            
            self.deployed = True
            logger.info("部署完成")
            
        except Exception as e:
            logger.error(f"部署失败: {e}")
            # 清理已创建的资源
            self.cleanup()
            raise
    
    def _create_containers(self, default_image: str):
        """创建所有容器"""
        logger.info(f"创建 {len(self.topology.nodes)} 个节点")
        
        # 1. 预处理镜像：确保所有需要的镜像都存在
        self._prepare_images(default_image)
        
        # 2. 创建容器
        for node in self.topology.nodes.values():
            extra_volumes = []
            
            # 检查是否有针对该节点类型的服务处理器
            # 使用 ServiceRegistry 动态查找，完全解耦
            service = ServiceRegistry.get(node.node_type)
            if service:
                try:
                    volumes = service.prepare(node, self.resource_tracker.session_id)
                    if volumes:
                        extra_volumes.extend(volumes)
                except Exception as e:
                    logger.error(f"准备节点 {node.name} 资源时出错: {e}")
                    raise

            # 委托给 ContainerManager 进行置备
            self.container_manager.provision_node(
                node=node,
                project_name=self.project_name,
                session_id=self.resource_tracker.session_id,
                default_image=default_image,
                extra_volumes=extra_volumes
            )

    def _prepare_images(self, default_image: str):
        """准备所需的镜像（拉取或构建）"""
        checked_images = set()
        
        for node in self.topology.nodes.values():
            if not hasattr(node.config, 'backend'):
                continue
                
            backend = node.config.backend
            if backend.get_backend_type() != 'container':
                continue
            
            # 获取镜像名称
            image = getattr(backend, 'image', None) or default_image
            
            # 如果已经检查过，跳过
            if image in checked_images:
                continue
            
            # 检查是否需要构建
            if hasattr(backend, 'build') and backend.build:
                logger.info(f"节点 {node.name} 需要构建镜像 {image}")
                success = self.image_manager.build_image(
                    path=str(backend.build.context_path),
                    tag=image,
                    dockerfile=backend.build.dockerfile,
                    buildargs=backend.build.build_args
                )
                if not success:
                    raise RuntimeError(f"构建镜像 {image} 失败")
            else:
                # 确保镜像存在（拉取）
                success = self.image_manager.ensure_image(image, pull=True)
                if not success:
                    raise RuntimeError(f"镜像 {image} 不可用且无法拉取")
            
            checked_images.add(image)
    
    def _start_containers(self):
        """启动所有容器"""
        logger.info("启动容器")
        
        for node_name, node in self.topology.nodes.items():
            # 只启动容器后端的节点
            if hasattr(node.config, 'backend'):
                backend = node.config.backend
                if backend.get_backend_type() == 'container':
                    self.container_manager.start_container(node_name, node)
    
    def _setup_network(self):
        """配置网络"""
        logger.info(f"配置 {len(self.topology.links)} 条链路")
        
        # 获取容器映射
        containers = {}
        for node_name in self.topology.nodes.keys():
            container = self.container_manager.get_container(node_name)
            if container:
                containers[node_name] = container
        
        self.network_manager.setup_network(self.topology, containers)
    
    def _setup_gateways(self):
        """配置默认网关"""
        if not self.topology.gateways:
            logger.debug("没有需要配置的默认网关")
            return
        
        logger.info(f"配置 {len(self.topology.gateways)} 个默认网关")
        
        for client_node_name, gateway_node_name in self.topology.gateways.items():
            try:
                # 获取网关节点的 IP 地址
                client_node = self.topology.get_node(client_node_name)
                gateway_node = self.topology.get_node(gateway_node_name)
                
                # 找到连接两个节点的链路和网关接口（支持直接连接或通过交换机连接）
                gateway_ip = None
                
                for client_iface in client_node.interfaces.values():
                    if not client_iface.is_connected or not client_iface.has_ip:
                        continue
                    
                    client_subnet = client_iface.link.subnet
                    if not client_subnet:
                        continue
                        
                    # 遍历网关的所有接口，寻找同一子网的接口
                    for gw_iface in gateway_node.interfaces.values():
                        if not gw_iface.is_connected or not gw_iface.has_ip:
                            continue
                        
                        if gw_iface.link.subnet == client_subnet:
                            gateway_ip = str(gw_iface.ip_address)
                            break
                    
                    if gateway_ip:
                        break
                
                if not gateway_ip:
                    logger.warning(
                        f"无法为 {client_node_name} 找到网关 {gateway_node_name} 的 IP"
                    )
                    continue
                
                # 在容器中配置默认路由
                cmd = f"ip route add default via {gateway_ip}"
                exit_code, output = self.container_manager.exec_run(
                    client_node_name,
                    cmd
                )
                
                if exit_code != 0:
                    logger.warning(
                        f"配置 {client_node_name} 的默认网关失败: {output.decode()}"
                    )
                else:
                    logger.info(
                        f"✓ {client_node_name} -> 默认网关 {gateway_ip}"
                    )
                    
            except Exception as e:
                logger.error(f"配置 {client_node_name} 的网关时出错: {e}")
    
    def cleanup(self):
        """清理部署的资源"""
        if self._cleanup_done:
            logger.debug("跳过清理：已经清理过")
            return  # 避免重复清理
        
        logger.info(f"清理会话 {self.resource_tracker.session_id}")
        self._cleanup_done = True
        
        try:
            # 使用 ResourceTracker 进行清理
            stats = ResourceTracker.cleanup_session(
                self.client,
                self.resource_tracker.session_id
            )
            
            logger.info(f"清理完成: 容器={stats['containers']}, OVS={stats['ovs_bridges']}, Veth={stats['veth_interfaces']}")
            
            if stats['errors']:
                logger.warning(f"清理过程中有 {len(stats['errors'])} 个错误")
                for error in stats['errors']:
                    logger.warning(f"  {error}")
            
        except Exception as e:
            logger.error(f"清理失败: {e}")
            import traceback
            traceback.print_exc()
            # 不要 raise，确保清理流程继续
        finally:
            self.deployed = False
            self.topology = None
            # 从实例列表中移除
            try:
                DeploymentController._instances.remove(self)
            except ValueError:
                pass
    
    def get_session_info(self) -> Dict:
        """获取会话信息"""
        sessions = ResourceTracker.list_all_sessions(self.client)
        return sessions.get(self.resource_tracker.session_id, {})
    
    def exec_in_node(self, node_name: Union[str, Node], cmd: str) -> tuple:
        """
        在节点中执行命令
        
        Args:
            node_name: 节点名称或节点对象
            cmd: 命令
        
        Returns:
            (exit_code, output)
        """
        if isinstance(node_name, Node):
            node_name = node_name.name
        return self.container_manager.exec_run(node_name, cmd)
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出，根据 auto_cleanup 决定是否清理"""
        if self.auto_cleanup:
            self.cleanup()

    def ping(self, source: Union[str, Node], target: Union[str, Node], count: int = 3, timeout: int = 2) -> bool:
        """
        从源节点 ping 目标
        
        Args:
            source: 源节点名称或节点对象
            target: 目标节点名称、节点对象或 IP 地址
            count: 发送包数量
            timeout: 超时时间（秒）
            
        Returns:
            bool: 是否成功
        """
        # 处理 source 参数
        if isinstance(source, Node):
            source = source.name
            
        # 处理 target 参数
        target_name = target.name if isinstance(target, Node) else target
        target_ip = target_name
        
        # 检查 target 是否为节点名称
        if self.topology and target_name in self.topology.nodes:
            target_node = self.topology.get_node(target_name)
            # 获取节点的第一个 IP
            # TODO: 未来可以根据源节点 IP 选择最佳目标 IP
            found_ip = False
            for iface in target_node.interfaces.values():
                if iface.has_ip:
                    target_ip = str(iface.ip_address)
                    found_ip = True
                    break
            
            if not found_ip:
                logger.warning(f"目标节点 {target} 没有分配 IP 地址")
                return False
        
        logger.info(f"Ping: {source} -> {target} ({target_ip})")
        
        # 使用 env LANG=C 确保输出为英文，以便解析
        cmd = f"env LANG=C ping -c {count} -W {timeout} {target_ip}"
        exit_code, output = self.exec_in_node(source, cmd)
        
        if exit_code == 0:
            # 尝试提取 RTT 信息
            import re
            rtt_match = re.search(r"min/avg/max/.*? = (.*?)/(.*?)/(.*?) ms", output.decode())
            rtt_info = ""
            if rtt_match:
                rtt_info = f" (avg={rtt_match.group(2)}ms)"
            
            logger.info(f"✓ Ping 成功: {source} -> {target}{rtt_info}")
            return True
        else:
            logger.warning(f"✗ Ping 失败: {source} -> {target}")
            return False

    def ping_all(self, timeout: int = 1) -> bool:
        """
        测试所有主机节点之间的连通性
        
        Returns:
            bool: 是否全部连通
        """
        if not self.topology:
            return False
            
        hosts = [n for n in self.topology.nodes.values() if n.is_host]
        if len(hosts) < 2:
            logger.warning("主机节点数量不足 2 个，无法执行 ping_all")
            return True
            
        total_pairs = 0
        success_count = 0
        
        logger.info(f"开始 Ping All 测试 ({len(hosts)} 个主机)")
        
        for src in hosts:
            for dst in hosts:
                if src == dst:
                    continue
                
                total_pairs += 1
                # 使用较少的包和较短的超时来加快全网测试
                if self.ping(src.name, dst.name, count=1, timeout=timeout):
                    success_count += 1
        
        success_rate = (success_count / total_pairs) * 100 if total_pairs > 0 else 0
        logger.info(f"Ping All 完成: {success_count}/{total_pairs} 成功 ({success_rate:.1f}%)")
        
        return success_count == total_pairs

    def get_ovs_bridge_name(self, node_name: Union[str, Node]) -> str:
        """获取 OVS 节点的实际网桥名称
        
        Args:
            node_name: 节点名称或对象
            
        Returns:
            实际的 Linux 网桥接口名称
        """
        if isinstance(node_name, Node):
            node = node_name
        else:
            if not self.topology or node_name not in self.topology.nodes:
                raise ValueError(f"节点 {node_name} 不存在")
            node = self.topology.get_node(node_name)
            
        if not node.is_switch:
             raise ValueError(f"节点 {node.name} 不是交换机")
             
        # 检查是否是 OVS 后端
        if not hasattr(node.config, 'backend') or node.config.backend.get_backend_type() != 'ovs_bridge':
            raise ValueError(f"节点 {node.name} 不是 OVS 交换机")
            
        backend = self.network_manager.backends.get("ovs_bridge")
        if not backend:
             raise RuntimeError("OVS backend not available")
             
        return backend.get_bridge_name(node)

    def run_ovs_ofctl(self, node_name: Union[str, Node], args: List[str]) -> str:
        """在 OVS 节点上运行 ovs-ofctl 命令
        
        Args:
            node_name: OVS 节点名称
            args: ovs-ofctl 参数列表 (e.g. ["dump-flows"])
            
        Returns:
            命令输出
        """
        if isinstance(node_name, Node):
            node = node_name
        else:
            if not self.topology or node_name not in self.topology.nodes:
                raise ValueError(f"节点 {node_name} 不存在")
            node = self.topology.get_node(node_name)
            
        backend = self.network_manager.backends.get("ovs_bridge")
        if not backend:
             raise RuntimeError("OVS backend not available")
             
        return backend.run_ofctl(node, args)

"""
OVS Bridge 网络后端

用于通过 Open vSwitch 连接多个容器。
"""

import subprocess
import logging
import hashlib
from typing import Dict, Any, Set, Optional, TYPE_CHECKING

from .network_backend import NetworkBackend
from ..config import OVSBridgeConfig

if TYPE_CHECKING:
    from vortinet.models import Link, Interface, Node
    from vortinet.utils import ResourceTracker

logger = logging.getLogger(__name__)


class OVSBridgeBackend(NetworkBackend):
    """OVS Bridge 后端实现
    
    使用 Open vSwitch 创建虚拟交换机，连接多个容器。
    支持 OpenFlow、VLAN 等高级特性。
    """
    
    def __init__(self, resource_tracker: Optional["ResourceTracker"] = None):
        self._created_bridges: Set[str] = set()
        self._resource_tracker = resource_tracker
        self._ovs_checked = False
    
    def _check_ovs_available(self) -> bool:
        """检查 OVS 是否可用
        
        Returns:
            True 如果 OVS 可用，否则 False
        """
        if self._ovs_checked:
            return True
            
        try:
            result = subprocess.run(
                ['ovs-vsctl', '--version'],
                capture_output=True,
                timeout=5,
                text=True
            )
            self._ovs_checked = result.returncode == 0
            return self._ovs_checked
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def set_resource_tracker(self, tracker: "ResourceTracker") -> None:
        """设置资源跟踪器
        
        Args:
            tracker: ResourceTracker 实例
        """
        self._resource_tracker = tracker
    
    def get_backend_name(self) -> str:
        return "ovs_bridge"
    
    def get_bridge_name(self, node: "Node") -> str:
        """获取 OVS 节点的实际网桥名称
        
        Args:
            node: OVS 交换机节点
            
        Returns:
            实际的 Linux 网桥接口名称
        """
        if not node.is_switch:
             raise ValueError(f"节点 {node.name} 不是交换机")
             
        # 检查是否是 OVS 后端
        if not hasattr(node.config, 'backend') or node.config.backend.get_backend_type() != 'ovs_bridge':
            raise ValueError(f"节点 {node.name} 不是 OVS 交换机")
            
        ovs_config: OVSBridgeConfig = node.config.backend
        base_bridge_name = ovs_config.bridge_name
        
        if self._resource_tracker:
            session_prefix = self._resource_tracker.session_id[:6]
            bridge_name = f"{session_prefix}-{base_bridge_name}"
            if len(bridge_name) > 15:
                h = hashlib.md5(base_bridge_name.encode()).hexdigest()[:4]
                bridge_name = f"{session_prefix}-{h}"
        else:
            bridge_name = base_bridge_name
            
        return bridge_name

    def run_ofctl(self, node: "Node", args: list[str]) -> str:
        """在 OVS 节点上运行 ovs-ofctl 命令
        
        Args:
            node: OVS 节点
            args: ovs-ofctl 参数列表 (e.g. ["dump-flows"] 或 ["add-flow", "flow..."])
            
        Returns:
            命令输出
        """
        if not args:
            raise ValueError("args 不能为空")
            
        bridge_name = self.get_bridge_name(node)
        of_version = node.config.backend.openflow_version
        
        # ovs-ofctl 语法: ovs-ofctl [options] command switch [args]...
        # 我们需要将 bridge_name 插入到 command (args[0]) 之后
        cmd = ["ovs-ofctl", "-O", of_version, args[0], bridge_name] + args[1:]
        
        logger.info(f"执行 OVS 命令: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"OVS 命令失败: {e.stderr}")

    def create_link(self, link: "Link", containers: Dict[str, Any]) -> None:
        """创建 OVS bridge 并连接容器
        
        Args:
            link: 必须是交换链路（带 switch 属性）
            containers: 节点名称 -> Docker 容器对象
            
        Raises:
            ValueError: 如果不是交换链路或交换机不是 OVS 类型
            RuntimeError: 如果创建失败或 OVS 不可用
        """
        # 检查 OVS 是否可用
        if not self._check_ovs_available():
            raise RuntimeError(
                "Open vSwitch 未安装或未运行。\n"
                "请安装: sudo apt install openvswitch-switch\n"
                "启动服务: sudo systemctl start openvswitch-switch"
            )
        
        if not link.is_switched:
            raise ValueError(
                f"OVSBridgeBackend 需要交换链路，"
                f"链路 {link.name} 不是交换链路"
            )
        
        switch = link.switch
        if not switch.is_ovs:
            raise ValueError(
                f"OVSBridgeBackend 需要 OVS 交换机，"
                f"但 {switch.name} 是 {switch.node_type}"
            )
        
        bridge_name = self.get_bridge_name(switch)
        ovs_config: OVSBridgeConfig = switch.config.backend
        
        logger.info(f"创建 OVS bridge 链路: {link.name}")
        logger.info(f"  Bridge: {bridge_name}")
        logger.info(f"  连接节点: {[iface.node.name for iface in link.interfaces]}")
        
        try:
            # 1. 创建 OVS bridge（如果还不存在）
            if bridge_name not in self._created_bridges:
                self._create_ovs_bridge(ovs_config, bridge_name, link.name)
                self._created_bridges.add(bridge_name)
            
            # 2. 为每个接口创建 veth pair 并连接到 bridge
            for interface in link.interfaces:
                # 跳过交换机节点本身
                if interface.node == switch:
                    continue
                
                container = containers.get(interface.node.name)
                if container is None:
                    logger.warning(f"找不到容器: {interface.node.name}")
                    continue
                
                self._connect_to_bridge(
                    interface, bridge_name, container, link
                )
            
            logger.info(f"✓ OVS bridge 链路创建成功: {link.name}")
            
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            logger.error(f"创建 OVS bridge 失败: {error_msg}")
            raise RuntimeError(f"创建链路 {link.name} 失败: {error_msg}")
        except Exception as e:
            logger.error(f"创建链路失败: {e}")
            raise
    
    def _create_ovs_bridge(
        self,
        config: OVSBridgeConfig,
        bridge_name: str,
        link_name: str = "unknown"
    ) -> None:
        """创建 OVS bridge
        
        Args:
            config: OVS 配置对象
            bridge_name: 实际使用的网桥名称（可能包含会话前缀）
            link_name: 链路名称（用于标签）
        """
        logger.debug(f"  创建 OVS bridge: {bridge_name}")
        
        # 使用 --may-exist 避免竞态条件
        subprocess.run(
            ["ovs-vsctl", "--may-exist", "add-br", bridge_name],
            check=True,
            capture_output=True
        )
        logger.debug(f"    ✓ Bridge 创建成功 (或已存在)")
        
        # 设置资源标签（使用 external-ids）
        if self._resource_tracker:
            external_ids = self._resource_tracker.get_ovs_bridge_tags(
                bridge_name, link_name
            )
            
            for key, value in external_ids.items():
                subprocess.run([
                    "ovs-vsctl", "set", "bridge", bridge_name,
                    f"external-ids:{key}={value}"
                ], check=True, capture_output=True)
            
            logger.debug(f"    ✓ 资源标签已设置")
        
        # 设置 OpenFlow 版本
        subprocess.run([
            "ovs-vsctl", "set", "bridge", bridge_name,
            f"protocols={config.openflow_version}"
        ], check=True, capture_output=True)
        logger.debug(f"    ✓ OpenFlow 版本: {config.openflow_version}")
        
        # 设置失败模式
        subprocess.run([
            "ovs-vsctl", "set-fail-mode", bridge_name, config.fail_mode
        ], check=True, capture_output=True)
        logger.debug(f"    ✓ 失败模式: {config.fail_mode}")
        
        # 连接 OpenFlow 控制器（如果配置了）
        if config.controller:
            subprocess.run([
                "ovs-vsctl", "set-controller", bridge_name, config.controller
            ], check=True, capture_output=True)
            logger.debug(f"    ✓ 控制器: {config.controller}")
        
        # 启动 bridge
        subprocess.run(
            ["ip", "link", "set", bridge_name, "up"],
            check=True,
            capture_output=True
        )
    
    def _connect_to_bridge(
        self,
        interface: "Interface",
        bridge_name: str,
        container: Any,
        link: "Link"
    ) -> None:
        """将容器接口连接到 OVS bridge
        
        Args:
            interface: 接口对象
            bridge_name: Bridge 名称
            container: Docker 容器对象
            link: 链路对象
        """
        node_name = interface.node.name
        target_name = interface.name
        
        logger.debug(f"  连接 {node_name}:{target_name} 到 {bridge_name}")
        
        try:
            # 刷新容器状态以获取最新的 PID
            container.reload()
            
            # 获取容器 PID
            pid = container.attrs['State']['Pid']
            
            if pid == 0:
                raise RuntimeError(f"容器 {node_name} PID 为 0，可能未正确启动")
            
            # 生成 veth pair 名称
            veth_host = f"{node_name}-{target_name}"
            veth_container = f"tmp-{veth_host}"
            
            # 截断名称
            veth_host = self._truncate_ifname(veth_host)
            veth_container = self._truncate_ifname(veth_container)
            
            # 1. 创建 veth pair
            logger.debug(f"    创建 veth pair: {veth_host} <-> {veth_container}")
            subprocess.run([
                "ip", "link", "add", veth_host, "type", "veth",
                "peer", "name", veth_container
            ], check=True, capture_output=True)
            
            # 2. 主机端连接到 OVS
            logger.debug(f"    添加 {veth_host} 到 {bridge_name}")
            
            # 检查是否设置了 VLAN
            vlan_id = link.get_vlan(interface)
            if vlan_id:
                # 添加端口并设置 VLAN tag
                subprocess.run([
                    "ovs-vsctl", "add-port", bridge_name, veth_host,
                    f"tag={vlan_id}"
                ], check=True, capture_output=True)
                logger.debug(f"    VLAN: {vlan_id}")
            else:
                # 添加端口（access 模式）
                subprocess.run([
                    "ovs-vsctl", "add-port", bridge_name, veth_host
                ], check=True, capture_output=True)
            
            # 启动主机端接口
            subprocess.run([
                "ip", "link", "set", veth_host, "up"
            ], check=True, capture_output=True)
            
            # 3. 容器端移入容器 netns
            logger.debug(f"    移动 {veth_container} 到容器 (PID {pid})")
            subprocess.run([
                "ip", "link", "set", veth_container, "netns", str(pid)
            ], check=True, capture_output=True)
            
            # 4. 在容器中配置接口
            self._setup_interface_in_container(
                container, veth_container, interface, link
            )
            
            logger.debug(f"    ✓ 连接成功")
            
        except Exception as e:
            logger.error(f"连接到 bridge 失败: {e}")
            raise
    
    def _setup_interface_in_container(
        self,
        container: Any,
        veth_name: str,
        interface: "Interface",
        link: "Link"
    ) -> None:
        """在容器中配置接口"""
        target_name = interface.name
        
        try:
            # 1. 重命名
            result = container.exec_run(
                f"ip link set {veth_name} name {target_name}",
                privileged=True
            )
            if result.exit_code != 0:
                raise RuntimeError(f"重命名失败: {result.output.decode()}")
            
            # 2. 设置 MAC
            mac = self._generate_mac(interface)
            result = container.exec_run(
                f"ip link set {target_name} address {mac}",
                privileged=True
            )
            if result.exit_code != 0:
                raise RuntimeError(f"设置 MAC 失败: {result.output.decode()}")
            
            # 3. 配置 IP
            if interface.has_ip:
                subnet = link.subnet
                ip_with_prefix = f"{interface.ip_address}/{subnet.prefixlen}"
                result = container.exec_run(
                    f"ip addr add {ip_with_prefix} dev {target_name}",
                    privileged=True
                )
                if result.exit_code != 0:
                    raise RuntimeError(f"设置 IP 失败: {result.output.decode()}")
            
            # 4. 配置 MTU 和状态
            mtu = link.config.mtu
            state = "up" if link.config.enabled else "down"
            
            # 设置 MTU
            result = container.exec_run(
                f"ip link set {target_name} mtu {mtu}",
                privileged=True
            )
            if result.exit_code != 0:
                raise RuntimeError(f"设置 MTU 失败: {result.output.decode()}")
            
            # 设置状态
            result = container.exec_run(
                f"ip link set {target_name} {state}",
                privileged=True
            )
            if result.exit_code != 0:
                raise RuntimeError(f"设置接口状态失败: {result.output.decode()}")
            
            # 5. 应用流量控制规则
            if link.config.enabled and link.config.traffic_control and link.config.traffic_control.has_any_rule():
                self._apply_tc(container, target_name, link)
            
        except Exception as e:
            logger.error(f"配置接口失败: {e}")
            raise
    
    def _apply_tc(self, container: Any, iface_name: str, link: "Link") -> None:
        """应用流量控制规则
        
        Args:
            container: Docker 容器对象
            iface_name: 接口名称
            link: 链路对象
        """
        tc_config = link.config.traffic_control
        if not tc_config or not tc_config.has_any_rule():
            return
        
        logger.debug(f"  应用 TC 规则到 {iface_name}")
        
        try:
            # 删除现有 qdisc（如果存在）
            container.exec_run(
                f"tc qdisc del dev {iface_name} root",
                privileged=True
            )
            
            # 添加 netem qdisc
            tc_args = tc_config.to_tc_command_args()
            cmd = f"tc qdisc add dev {iface_name} root netem {tc_args}"
            result = container.exec_run(cmd, privileged=True)
            
            if result.exit_code != 0:
                logger.warning(f"应用 TC 规则失败: {result.output.decode()}")
            else:
                logger.debug(f"    TC: {tc_args}")
                
        except Exception as e:
            logger.warning(f"应用 TC 规则时出错: {e}")
    
    def _generate_mac(self, interface: "Interface") -> str:
        """生成 MAC 地址（与 DirectVethBackend 相同）"""
        h = hashlib.md5(
            f"{interface.node.name}:{interface.name}".encode()
        )
        mac_bytes = h.digest()[:6]
        mac_bytes = bytes([0x02, 0x42]) + mac_bytes[2:]
        return ":".join(f"{b:02x}" for b in mac_bytes)
    
    def _truncate_ifname(self, name: str, max_len: int = 15) -> str:
        """截断接口名称"""
        if len(name) <= max_len:
            return name
        h = hashlib.md5(name.encode()).hexdigest()[:4]
        prefix_len = max_len - len(h) - 1
        return name[:prefix_len] + "-" + h
    
    def cleanup_link(self, link: "Link") -> None:
        """清理 OVS bridge
        
        Args:
            link: 链路对象
        """
        if not link.is_switched or not link.switch.is_ovs:
            return
        
        bridge_name = self.get_bridge_name(link.switch)
        
        if bridge_name in self._created_bridges:
            try:
                logger.debug(f"删除 OVS bridge: {bridge_name}")
                subprocess.run(
                    ["ovs-vsctl", "del-br", bridge_name],
                    check=False,
                    capture_output=True
                )
                self._created_bridges.discard(bridge_name)
            except Exception as e:
                logger.warning(f"删除 OVS bridge 失败: {e}")

"""
Direct veth pair 网络后端

用于点对点连接，直接创建 veth pair 连接两个容器。
"""

import subprocess
import logging
import hashlib
from typing import Dict, Any, TYPE_CHECKING

from .network_backend import NetworkBackend

if TYPE_CHECKING:
    from vortinet.models import Link, Interface

logger = logging.getLogger(__name__)


class DirectVethBackend(NetworkBackend):
    """Direct veth pair 后端实现
    
    创建 veth pair 直接连接两个容器，不经过任何网桥或交换机。
    这是最简单、最高效的连接方式，适用于点对点链路。
    """
    
    def get_backend_name(self) -> str:
        return "direct_veth"
    
    def create_link(self, link: "Link", containers: Dict[str, Any]) -> None:
        """创建 veth pair 直连两个容器
        
        Args:
            link: 必须是点对点链路（2个接口）
            containers: 节点名称 -> Docker 容器对象
            
        Raises:
            ValueError: 如果不是点对点链路
            RuntimeError: 如果创建失败
        """
        if not link.is_point_to_point:
            raise ValueError(
                f"DirectVethBackend 只支持点对点链路，"
                f"链路 {link.name} 有 {link.interface_count} 个接口"
            )
        
        interfaces = link.interfaces
        iface1, iface2 = interfaces[0], interfaces[1]
        
        logger.info(f"创建 direct veth 链路: {link.name}")
        logger.info(f"  连接: {iface1.node.name}:{iface1.name} <-> {iface2.node.name}:{iface2.name}")
        
        try:
            # 获取容器
            container1 = containers[iface1.node.name]
            container2 = containers[iface2.node.name]
            
            # 刷新容器状态以获取最新的 PID
            container1.reload()
            container2.reload()
            
            # 获取容器 PID
            pid1 = container1.attrs['State']['Pid']
            pid2 = container2.attrs['State']['Pid']
            
            if pid1 == 0 or pid2 == 0:
                raise RuntimeError(
                    f"容器 PID 无效: {iface1.node.name}={pid1}, {iface2.node.name}={pid2}"
                )
            
            # 生成 veth 名称
            veth1_temp = f"veth-{iface1.node.name}-{iface1.name}"
            veth2_temp = f"veth-{iface2.node.name}-{iface2.name}"
            
            # 限制名称长度（Linux 接口名最多15字符）
            veth1_temp = self._truncate_ifname(veth1_temp)
            veth2_temp = self._truncate_ifname(veth2_temp)
            
            # 1. 在主机上创建 veth pair
            logger.debug(f"  创建 veth pair: {veth1_temp} <-> {veth2_temp}")
            subprocess.run([
                "ip", "link", "add", veth1_temp, "type", "veth",
                "peer", "name", veth2_temp
            ], check=True, capture_output=True)
            
            # 2. 将 veth 端移动到容器 netns
            logger.debug(f"  移动 {veth1_temp} 到容器 {iface1.node.name} (PID {pid1})")
            subprocess.run([
                "ip", "link", "set", veth1_temp, "netns", str(pid1)
            ], check=True, capture_output=True)
            
            logger.debug(f"  移动 {veth2_temp} 到容器 {iface2.node.name} (PID {pid2})")
            subprocess.run([
                "ip", "link", "set", veth2_temp, "netns", str(pid2)
            ], check=True, capture_output=True)
            
            # 3. 在容器中配置接口
            self._setup_interface_in_container(container1, veth1_temp, iface1, link)
            self._setup_interface_in_container(container2, veth2_temp, iface2, link)
            
            logger.info(f"✓ Direct veth 链路创建成功: {link.name}")
            
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            logger.error(f"创建 veth pair 失败: {error_msg}")
            raise RuntimeError(f"创建链路 {link.name} 失败: {error_msg}")
        except Exception as e:
            logger.error(f"创建链路失败: {e}")
            raise
    
    def _setup_interface_in_container(
        self,
        container: Any,
        veth_name: str,
        interface: "Interface",
        link: "Link"
    ) -> None:
        """在容器中配置接口
        
        Args:
            container: Docker 容器对象
            veth_name: veth 接口名称（临时名称）
            interface: 接口对象
            link: 链路对象
        """
        node_name = interface.node.name
        target_name = interface.name
        
        logger.debug(f"  配置容器 {node_name} 中的接口 {target_name}")
        
        try:
            # 1. 重命名接口
            result = container.exec_run(
                f"ip link set {veth_name} name {target_name}",
                privileged=True
            )
            if result.exit_code != 0:
                raise RuntimeError(f"重命名接口失败: {result.output.decode()}")
            
            # 2. 设置 MAC 地址
            mac = self._generate_mac(interface)
            result = container.exec_run(
                f"ip link set {target_name} address {mac}",
                privileged=True
            )
            if result.exit_code != 0:
                raise RuntimeError(f"设置 MAC 地址失败: {result.output.decode()}")
            
            logger.debug(f"    MAC: {mac}")
            
            # 3. 配置 IP 地址
            if interface.has_ip:
                subnet = link.subnet
                ip_with_prefix = f"{interface.ip_address}/{subnet.prefixlen}"
                result = container.exec_run(
                    f"ip addr add {ip_with_prefix} dev {target_name}",
                    privileged=True
                )
                if result.exit_code != 0:
                    raise RuntimeError(f"设置 IP 失败: {result.output.decode()}")
                
                logger.debug(f"    IP: {ip_with_prefix}")
            
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
            
            logger.debug(f"  ✓ 接口 {target_name} 配置完成")
            
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
        """生成确定性 MAC 地址
        
        基于节点名和接口名生成唯一的 MAC 地址。
        使用 02:42 前缀（Docker 风格）以避免与真实网卡冲突。
        
        Args:
            interface: 接口对象
            
        Returns:
            MAC 地址字符串（格式：xx:xx:xx:xx:xx:xx）
        """
        # 基于节点名和接口名生成哈希
        h = hashlib.md5(
            f"{interface.node.name}:{interface.name}".encode()
        )
        mac_bytes = h.digest()[:6]
        
        # 设置本地管理位（bit 1 of byte 0）并清除组播位（bit 0）
        # 使用 0x02 确保是本地管理的单播地址
        mac_bytes = bytes([0x02, 0x42]) + mac_bytes[2:]
        
        return ":".join(f"{b:02x}" for b in mac_bytes)
    
    def _truncate_ifname(self, name: str, max_len: int = 15) -> str:
        """截断接口名称到允许的最大长度
        
        Linux 接口名最多 15 个字符。
        
        Args:
            name: 原始名称
            max_len: 最大长度
            
        Returns:
            截断后的名称
        """
        if len(name) <= max_len:
            return name
        
        # 使用哈希后缀保证唯一性
        h = hashlib.md5(name.encode()).hexdigest()[:4]
        prefix_len = max_len - len(h) - 1
        return name[:prefix_len] + "-" + h
    
    def cleanup_link(self, link: "Link") -> None:
        """清理 veth pair
        
        由于 veth 在容器的 netns 中，容器删除时会自动清理，
        因此这里不需要手动清理。
        
        Args:
            link: 链路对象
        """
        logger.debug(f"清理 direct veth 链路: {link.name} (自动清理)")

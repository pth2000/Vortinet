"""
网络管理器

统一管理所有网络后端，自动选择合适的后端创建网络连接。
"""

import logging
from typing import Dict, Any, List, Tuple, Optional, TYPE_CHECKING

from .network_backend import NetworkBackend
from .direct_veth_backend import DirectVethBackend
from .ovs_bridge_backend import OVSBridgeBackend
from .linux_bridge_backend import LinuxBridgeBackend

if TYPE_CHECKING:
    from vortinet.models import Topology, Link
    from vortinet.utils import ResourceTracker

logger = logging.getLogger(__name__)


class NetworkManager:
    """网络管理器
    
    负责：
    1. 根据链路类型自动选择网络后端
    2. 协调网络连接的创建
    3. 管理网络连接的生命周期
    """
    
    def __init__(self, resource_tracker: Optional["ResourceTracker"] = None):
        """初始化网络管理器
        
        Args:
            resource_tracker: 资源跟踪器（用于标记创建的资源）
        """
        self.backends: Dict[str, NetworkBackend] = {
            "direct_veth": DirectVethBackend(),
            "ovs_bridge": OVSBridgeBackend(resource_tracker),
            "linux_bridge": LinuxBridgeBackend(),
        }
        
        self._resource_tracker = resource_tracker
        self._created_links: List[Tuple["Link", NetworkBackend]] = []
    
    def set_resource_tracker(self, tracker: "ResourceTracker") -> None:
        """设置资源跟踪器
        
        Args:
            tracker: ResourceTracker 实例
        """
        self._resource_tracker = tracker
        
        # 更新所有后端的跟踪器
        if hasattr(self.backends["ovs_bridge"], "set_resource_tracker"):
            self.backends["ovs_bridge"].set_resource_tracker(tracker)
    
    def setup_network(
        self,
        topology: "Topology",
        containers: Dict[str, Any]
    ) -> None:
        """为拓扑创建所有网络连接
        
        Args:
            topology: 拓扑对象
            containers: 节点名称 -> Docker 容器对象的映射
            
        Raises:
            RuntimeError: 如果创建网络失败
        """
        logger.info("=" * 60)
        logger.info("开始创建网络连接")
        logger.info("=" * 60)
        
        links = topology.links
        total = len(links)
        
        logger.info(f"拓扑包含 {total} 个链路")
        
        failed_links = []
        
        for idx, (link_name, link) in enumerate(links.items(), 1):
            logger.info(f"\n[{idx}/{total}] 处理链路: {link_name}")
            
            try:
                # 选择后端
                backend = self._select_backend(link)
                logger.info(f"  使用后端: {backend.get_backend_name()}")
                
                # 创建链路
                backend.create_link(link, containers)
                
                # 记录已创建的链路
                self._created_links.append((link, backend))
                
            except Exception as e:
                logger.error(f"  ✗ 创建链路失败: {e}")
                failed_links.append((link_name, str(e)))
                # 继续处理其他链路，但记录失败
        
        logger.info("")
        logger.info("=" * 60)
        
        if failed_links:
            logger.error(f"✗ 网络创建部分失败: {len(self._created_links)}/{total} 链路成功, {len(failed_links)} 失败")
            for link_name, error in failed_links:
                logger.error(f"  - {link_name}: {error}")
            
            # 自动回滚清理
            logger.info("正在回滚已创建的网络资源...")
            self.cleanup()
            
            # 抛出异常，但包含已成功的链路数
            raise RuntimeError(
                f"创建网络失败: {len(failed_links)}/{total} 个链路创建失败。"
                f"已自动回滚清理。"
                f"第一个错误: {failed_links[0][1] if failed_links else 'Unknown'}"
            )
        else:
            logger.info(f"✓ 网络创建完成: {len(self._created_links)}/{total} 链路成功")
        
        logger.info("=" * 60)
    
    def _select_backend(self, link: "Link") -> NetworkBackend:
        """根据链路类型选择合适的网络后端
        
        Args:
            link: 链路对象
            
        Returns:
            选择的网络后端
            
        Raises:
            ValueError: 如果无法选择合适的后端
        """
        # 1. 交换链路
        if link.is_switched:
            switch = link.switch
            
            # 动态获取后端类型
            if hasattr(switch.config, 'backend'):
                backend_type = switch.config.backend.get_backend_type()
                if backend_type in self.backends:
                    return self.backends[backend_type]
            
            raise ValueError(
                f"无法为交换机 {switch.name} (类型: {switch.node_type}) 确定网络后端。"
                f"后端配置类型: {type(switch.config.backend).__name__}"
            )
        
        # 2. 点对点链路
        elif link.is_point_to_point:
            return self.backends["direct_veth"]
        
        # 3. 多接口但无交换机（不推荐，但提供降级方案）
        else:
            logger.warning(
                f"链路 {link.name} 有 {link.interface_count} 个接口但无交换机，"
                f"建议使用交换机节点"
            )
            # 降级到 OVS bridge（自动创建）
            return self.backends["ovs_bridge"]
    
    def cleanup(self) -> None:
        """清理所有已创建的网络连接"""
        logger.info("清理网络连接...")
        
        # 逆序清理
        for link, backend in reversed(self._created_links):
            try:
                backend.cleanup_link(link)
            except Exception as e:
                logger.warning(f"清理链路 {link.name} 失败: {e}")
        
        self._created_links.clear()
        logger.info("✓ 网络清理完成")

"""
Linux Bridge 网络后端

用于通过 Linux Bridge 连接多个容器（暂未完全实现）。
"""

import logging
from typing import Dict, Any, TYPE_CHECKING

from .network_backend import NetworkBackend

if TYPE_CHECKING:
    from vortinet.models import Link

logger = logging.getLogger(__name__)


class LinuxBridgeBackend(NetworkBackend):
    """Linux Bridge 后端实现（占位符）
    
    TODO: 实现 Linux Bridge 创建和管理逻辑
    """
    
    def get_backend_name(self) -> str:
        return "linux_bridge"
    
    def create_link(self, link: "Link", containers: Dict[str, Any]) -> None:
        """创建 Linux bridge 并连接容器
        
        Args:
            link: 交换链路
            containers: 容器字典
        """
        raise NotImplementedError(
            "Linux Bridge 后端尚未实现，请使用 OVS Bridge"
        )
    
    def cleanup_link(self, link: "Link") -> None:
        """清理 Linux bridge"""
        pass

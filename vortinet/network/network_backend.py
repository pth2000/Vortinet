"""
网络后端抽象接口

定义所有网络后端必须实现的接口。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from vortinet.models import Link


class NetworkBackend(ABC):
    """网络后端抽象基类
    
    所有网络后端（Direct veth, OVS, Linux Bridge等）都必须实现此接口。
    """
    
    @abstractmethod
    def create_link(self, link: "Link", containers: Dict[str, Any]) -> None:
        """创建网络连接
        
        Args:
            link: 链路对象
            containers: 节点名称 -> Docker 容器对象的映射
            
        Raises:
            ValueError: 如果链路类型不支持
            RuntimeError: 如果创建网络失败
        """
        pass
    
    @abstractmethod
    def cleanup_link(self, link: "Link") -> None:
        """清理网络连接
        
        Args:
            link: 链路对象
        """
        pass
    
    @abstractmethod
    def get_backend_name(self) -> str:
        """返回后端名称
        
        Returns:
            后端标识字符串
        """
        pass

"""
服务注册中心

用于管理不同节点类型的服务处理器。
实现了节点类型与具体服务逻辑的解耦。
"""

from typing import Dict, List, Protocol, Optional
from ..models.node import Node

class NodeService(Protocol):
    """节点服务接口"""
    
    def prepare(self, node: Node, session_id: str) -> List[str]:
        """
        准备节点资源
        
        Args:
            node: 节点对象
            session_id: 会话 ID
            
        Returns:
            需要挂载的 volume 列表 (host_path:container_path:mode)
        """
        ...

class ServiceRegistry:
    """服务注册表"""
    
    _services: Dict[str, NodeService] = {}
    
    @classmethod
    def register(cls, node_type: str, service: NodeService) -> None:
        """注册服务"""
        cls._services[node_type] = service
        
    @classmethod
    def get(cls, node_type: str) -> Optional[NodeService]:
        """获取服务"""
        return cls._services.get(node_type)

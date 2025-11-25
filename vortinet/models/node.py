"""
节点模型

职责：
1. 管理节点的身份信息（名称、类型）
2. 管理节点的接口集合
3. 持有节点的配置（不再是字典）
"""

from typing import Dict, Optional, TYPE_CHECKING
from ..config import NodeConfig

if TYPE_CHECKING:
    from .interface import Interface


class Node:
    """网络节点的抽象表示
    
    设计原则：
    - 单一职责：只管理节点本身的状态和接口
    - 不再使用 attributes 字典，改用强类型的 NodeConfig
    - 节点的行为通过 NodeConfig 和 BackendConfig 配置
    """
    
    def __init__(self, name: str, config: NodeConfig):
        """
        Args:
            name: 节点名称，必须在拓扑中唯一
            config: 节点配置对象（强类型）
        """
        if not name:
            raise ValueError("节点名称不能为空")
        
        config.validate()
        
        self._name = name
        self._config = config
        self._interfaces: Dict[str, "Interface"] = {}
    
    @property
    def name(self) -> str:
        """节点名称（只读）"""
        return self._name
    
    @property
    def config(self) -> NodeConfig:
        """节点配置（只读）"""
        return self._config
    
    @property
    def node_type(self) -> str:
        """节点类型"""
        return self._config.node_type
    
    @property
    def is_switch(self) -> bool:
        """是否为交换机节点"""
        return self._config.is_switch

    @property
    def is_router(self) -> bool:
        """是否为路由器节点"""
        return self._config.is_router

    @property
    def is_host(self) -> bool:
        """是否为主机节点"""
        return self._config.is_host

    @property
    def is_ovs(self) -> bool:
        """是否为 OVS 交换机"""
        return self._config.is_ovs

    @property
    def is_linux_bridge(self) -> bool:
        """是否为 Linux Bridge 交换机"""
        return self._config.is_linux_bridge
    
    @property
    def interfaces(self) -> Dict[str, "Interface"]:
        """接口字典（只读视图）"""
        return self._interfaces.copy()
    
    def add_interface(self, interface: "Interface") -> None:
        """添加接口
        
        Args:
            interface: 已创建的接口对象
            
        Raises:
            ValueError: 如果接口名称已存在
        """
        if interface.name in self._interfaces:
            raise ValueError(
                f"接口 {interface.name} 已存在于节点 {self.name}"
            )
        
        if interface.node is not self:
            raise ValueError(
                f"接口 {interface.name} 不属于节点 {self.name}"
            )
        
        self._interfaces[interface.name] = interface
    
    def get_interface(self, name: str) -> Optional["Interface"]:
        """获取指定名称的接口"""
        return self._interfaces.get(name)
    
    def __repr__(self) -> str:
        return (
            f"Node(name={self.name!r}, "
            f"type={self.node_type!r}, "
            f"interfaces={len(self._interfaces)})"
        )
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, Node):
            return False
        return self.name == other.name
    
    def __hash__(self) -> int:
        return hash(self.name)

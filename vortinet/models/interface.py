"""
接口模型

职责：
1. 表示节点的一个网络接口
2. 持有 IP 地址
3. 维护与链路的关联
"""

from typing import TYPE_CHECKING, Optional
from ipaddress import IPv4Address

if TYPE_CHECKING:
    from .node import Node
    from .link import Link


class Interface:
    """网络接口的抽象表示
    
    设计原则：
    - 明确的所有权：一个接口属于一个节点
    - 明确的连接状态：connected/disconnected
    - 不可变的关键属性（节点引用）
    """
    
    def __init__(self, name: str, node: "Node"):
        """
        Args:
            name: 接口名称（如 eth0, eth1）
            node: 所属节点
        """
        if not name:
            raise ValueError("接口名称不能为空")
            
        # 安全性验证：防止命令注入
        # 只允许字母、数字、下划线、短横线和点号
        import re
        if not re.match(r'^[a-zA-Z0-9_.-]+$', name):
            raise ValueError(f"接口名称包含非法字符: {name} (只允许 a-z, A-Z, 0-9, _, ., -)")
        
        if not node:
            raise ValueError("接口必须属于一个节点")
        
        self._name = name
        self._node = node
        self._link: Optional["Link"] = None
        self._ip_address: Optional[IPv4Address] = None
    
    @property
    def name(self) -> str:
        """接口名称（只读）"""
        return self._name
    
    @property
    def node(self) -> "Node":
        """所属节点（只读）"""
        return self._node
    
    @property
    def link(self) -> Optional["Link"]:
        """连接的链路（只读）"""
        return self._link
    
    @property
    def ip_address(self) -> Optional[IPv4Address]:
        """IP 地址（只读）"""
        return self._ip_address
    
    @property
    def is_connected(self) -> bool:
        """是否已连接到链路"""
        return self._link is not None
    
    @property
    def has_ip(self) -> bool:
        """是否已分配 IP 地址"""
        return self._ip_address is not None
    
    def assign_ip(self, ip_address: IPv4Address) -> None:
        """分配 IP 地址
        
        Args:
            ip_address: IPv4 地址对象
            
        Raises:
            ValueError: 如果 IP 已被分配
        """
        if self._ip_address is not None:
            raise ValueError(
                f"接口 {self.name} 已有 IP 地址: {self._ip_address}"
            )
        
        self._ip_address = ip_address
    
    def connect_to(self, link: "Link") -> None:
        """连接到链路
        
        Args:
            link: 链路对象
            
        Raises:
            ConnectionError: 如果接口已连接到其他链路
        """
        if self._link is not None:
            raise ConnectionError(
                f"接口 {self.name} 已连接到链路 {self._link.name}"
            )
        
        self._link = link
    
    def disconnect(self) -> None:
        """从链路断开"""
        self._link = None
    
    def __repr__(self) -> str:
        status = []
        if self.is_connected:
            status.append(f"link={self._link.name}")
        if self.has_ip:
            status.append(f"ip={self._ip_address}")
        
        status_str = ", ".join(status) if status else "disconnected"
        return f"Interface(name={self.name!r}, node={self.node.name!r}, {status_str})"
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, Interface):
            return False
        return self.name == other.name and self.node == other.node
    
    def __hash__(self) -> int:
        return hash((self.name, self.node))

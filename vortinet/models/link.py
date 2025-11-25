"""
链路模型

职责：
1. 连接多个接口
2. 持有子网信息
3. 持有链路配置（流量控制等）
4. 支持交换链路（通过 switch 属性）
"""

from typing import List, Optional, TYPE_CHECKING, Dict
from ipaddress import IPv4Network
import logging

from ..config import LinkConfig

if TYPE_CHECKING:
    from .interface import Interface
    from .node import Node

logger = logging.getLogger(__name__)


class Link:
    """网络链路的抽象表示
    
    设计原则：
    - 支持点对点和交换两种模式
    - 配置与状态分离
    - 明确的连接管理
    """
    
    def __init__(
        self, 
        name: str, 
        subnet: Optional[IPv4Network], 
        config: LinkConfig,
        switch: Optional["Node"] = None
    ):
        """
        Args:
            name: 链路名称
            subnet: 子网（可选，L2 链路或 Trunk 链路可为 None）
            config: 链路配置对象
            switch: 可选的交换机节点（如果通过交换机连接）
        """
        if not name:
            raise ValueError("链路名称不能为空")
        
        config.validate()
        
        self._name = name
        self._subnet = subnet
        self._config = config
        self._switch = switch
        self._interfaces: List["Interface"] = []
        self._vlan_map: Dict["Interface", int] = {}  # 接口 -> VLAN ID
        
        # 验证交换机类型
        if switch is not None:
            if switch.node_type not in ["ovs_switch", "linux_bridge_switch"]:
                raise ValueError(
                    f"Switch node must be of type 'ovs_switch' or 'linux_bridge_switch', "
                    f"got: {switch.node_type}"
                )
    
    @property
    def name(self) -> str:
        """链路名称（只读）"""
        return self._name
    
    @property
    def subnet(self) -> Optional[IPv4Network]:
        """子网（只读，可能为 None）"""
        return self._subnet
    
    @property
    def config(self) -> LinkConfig:
        """链路配置（只读）"""
        return self._config
    
    @property
    def switch(self) -> Optional["Node"]:
        """关联的交换机节点（只读）"""
        return self._switch
    
    @property
    def interfaces(self) -> List["Interface"]:
        """连接的接口列表（只读副本）"""
        return self._interfaces.copy()
    
    @property
    def interface_count(self) -> int:
        """连接的接口数量"""
        return len(self._interfaces)
    
    @property
    def is_point_to_point(self) -> bool:
        """是否为点对点链路（无交换机且恰好2个接口）"""
        return self._switch is None and self.interface_count == 2
    
    @property
    def is_switched(self) -> bool:
        """是否为交换链路（通过交换机连接）"""
        return self._switch is not None
    
    def attach(self, interface: "Interface") -> None:
        """将接口连接到此链路
        
        Args:
            interface: 接口对象
            
        Raises:
            ValueError: 如果接口已在链路中
        """
        if interface in self._interfaces:
            raise ValueError(
                f"接口 {interface.name} 已连接到链路 {self.name}"
            )
        
        # 对于点对点链路，警告多于2个接口
        if not self.is_switched and self.interface_count >= 2:
            logger.warning(
                f"链路 {self.name} 连接了 {self.interface_count + 1} 个接口，"
                f"但没有配置交换机。这可能不是预期的拓扑结构。"
            )
        
        # 建立双向关联
        interface.connect_to(self)
        self._interfaces.append(interface)
    
    def set_vlan(self, interface: "Interface", vlan_id: int) -> None:
        """为接口设置 VLAN（仅用于交换链路）
        
        Args:
            interface: 接口对象
            vlan_id: VLAN ID (1-4094)
            
        Raises:
            ValueError: 如果接口不在链路中或 VLAN ID 无效
            RuntimeError: 如果链路不是交换链路
        """
        if not self.is_switched:
            raise RuntimeError(
                f"只有交换链路才能设置 VLAN，链路 {self.name} 不是交换链路"
            )
        
        if interface not in self._interfaces:
            raise ValueError(
                f"接口 {interface.name} 不在链路 {self.name} 中"
            )
        
        if not (1 <= vlan_id <= 4094):
            raise ValueError(
                f"无效的 VLAN ID: {vlan_id}。有效范围: 1-4094"
            )
        
        self._vlan_map[interface] = vlan_id
        logger.info(
            f"为接口 {interface.node.name}:{interface.name} "
            f"设置 VLAN {vlan_id}"
        )
    
    def get_vlan(self, interface: "Interface") -> Optional[int]:
        """获取接口的 VLAN ID
        
        Args:
            interface: 接口对象
            
        Returns:
            VLAN ID，如果未设置则返回 None
        """
        return self._vlan_map.get(interface)
    
    def detach(self, interface: "Interface") -> None:
        """将接口从链路断开
        
        Args:
            interface: 接口对象
        """
        if interface in self._interfaces:
            self._interfaces.remove(interface)
            interface.disconnect()
    
    def get_peer_interface(self, interface: "Interface") -> "Interface":
        """获取点对点链路中的对端接口
        
        Args:
            interface: 本端接口
            
        Returns:
            对端接口
            
        Raises:
            ValueError: 如果不是点对点链路或接口不在链路中
        """
        if not self.is_point_to_point:
            raise ValueError(
                f"链路 {self.name} 不是点对点链路 "
                f"(接口数: {self.interface_count})"
            )
        
        if interface not in self._interfaces:
            raise ValueError(
                f"接口 {interface.name} 不在链路 {self.name} 中"
            )
        
        return next(iface for iface in self._interfaces if iface != interface)
    
    def __repr__(self) -> str:
        node_names = [iface.node.name for iface in self._interfaces]
        if self.is_switched:
            connections = f"[{', '.join(node_names)}] via {self._switch.name}"
        else:
            connections = " <-> ".join(node_names) if node_names else "empty"
        
        return (
            f"Link(name={self.name!r}, "
            f"subnet={self.subnet}, "
            f"switched={self.is_switched}, "
            f"connections={connections})"
        )
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, Link):
            return False
        return self.name == other.name
    
    def __hash__(self) -> int:
        return hash(self.name)

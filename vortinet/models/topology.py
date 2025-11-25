"""
拓扑模型

职责：
1. 管理节点和链路的集合
2. 协调 IP 地址分配
3. 提供拓扑构建的 API
"""

from typing import Dict, Optional, Union
from ipaddress import IPv4Network
import logging

from .node import Node
from .interface import Interface
from .link import Link
from ..config import NodeConfig, LinkConfig, TopologyConfig
from ..utils import IPAddressAllocator
from ..utils.ip_strategy import IPAllocationStrategy

logger = logging.getLogger(__name__)


class Topology:
    """网络拓扑容器
    
    设计原则：
    - 提供声明式 API
    - 自动化 IP 分配和接口管理
    - 保持拓扑结构的一致性
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        config: Optional[TopologyConfig] = None,
        ip_strategy: Optional[IPAllocationStrategy] = None
    ):
        """
        Args:
            name: 拓扑名称（可选）
            config: 拓扑配置，None 则使用默认配置
            ip_strategy: IP 分配策略，None 则使用默认策略（顺序分配）
        """
        self._name = name or "topology"
        self._config = config or TopologyConfig()
        self._config.validate()
        
        self._nodes: Dict[str, Node] = {}
        self._links: Dict[str, Link] = {}
        self._gateways: Dict[str, str] = {}  # node_name -> gateway_node_name
        self._ip_allocator = IPAddressAllocator(strategy=ip_strategy)
        
        # 子网分配
        self._subnet_iterator = self._config.base_network.subnets(
            new_prefix=self._config.subnet_prefix_length
        )
        self._link_counter = 0
        
        # 交换机子网缓存: switch_name -> subnet
        # 用于确保同一交换机的所有连接使用相同子网
        self._switch_subnets: Dict[str, IPv4Network] = {}
    
    @property
    def name(self) -> str:
        """拓扑名称（只读）"""
        return self._name
    
    @property
    def config(self) -> TopologyConfig:
        """拓扑配置（只读）"""
        return self._config
    
    @property
    def nodes(self) -> Dict[str, Node]:
        """节点字典（只读副本）"""
        return self._nodes.copy()
    
    @property
    def links(self) -> Dict[str, Link]:
        """链路字典（只读副本）"""
        return self._links.copy()
    
    @property
    def node_count(self) -> int:
        """节点数量"""
        return len(self._nodes)
    
    @property
    def link_count(self) -> int:
        """链路数量"""
        return len(self._links)
    
    @property
    def gateways(self) -> Dict[str, str]:
        """网关映射（只读副本）"""
        return self._gateways.copy()
    
    @property
    def ip_allocator(self) -> IPAddressAllocator:
        """IP 分配器（只读）"""
        return self._ip_allocator
    
    def set_ip_strategy(self, strategy: IPAllocationStrategy) -> None:
        """切换 IP 分配策略
        
        Args:
            strategy: 新的 IP 分配策略
            
        Warning:
            切换策略会重置之前的 IP 分配状态
            
        Example:
            from vortinet.utils import GatewayReservedStrategy
            topo.set_ip_strategy(GatewayReservedStrategy())
        """
        self._ip_allocator.set_strategy(strategy)
        logger.info(f"拓扑 {self._name} 切换 IP 分配策略")
    
    def reserve_ip(
        self,
        node_or_name: Union[str, Node],
        ip_address: str,
        subnet: Optional[IPv4Network] = None
    ) -> None:
        """为节点预留 IP 地址
        
        Args:
            node_or_name: 节点名称或对象
            ip_address: IP 地址字符串 (e.g. "192.168.1.10")
            subnet: 所在的子网 (可选)。如果未提供，将尝试从 IP 地址推断或需要后续 add_link 时指定。
                    注意：如果这里不提供 subnet，而 add_link 时使用了自动分配的子网，
                    可能会导致预留不生效（因为不知道是哪个子网）。
                    建议显式提供 subnet。
        """
        if isinstance(node_or_name, Node):
            node_name = node_or_name.name
        else:
            node_name = node_or_name
            
        from ipaddress import IPv4Address
        ip = IPv4Address(ip_address)
        
        if subnet is None:
            # 尝试推断：如果 IP 是私有地址，可能属于某个标准子网？
            # 不，这太危险。必须提供 subnet。
            raise ValueError("reserve_ip 必须提供 subnet 参数")
            
        self._ip_allocator.reserve_ip(subnet, node_name, ip)
        logger.info(f"预留 IP: {node_name} -> {ip} ({subnet})")

    def add_node(
        self,
        node: Node
    ) -> Node:
        """添加节点
        
        Args:
            node: 节点对象
            
        Returns:
            添加的节点对象
        """
        if isinstance(node, Node):
            if node.name in self._nodes:
                raise ValueError(f"节点 {node.name} 已存在")
            self._nodes[node.name] = node
            logger.info(f"添加节点: {node}")
            return node
            
        else:
            raise TypeError(f"无效的参数类型: {type(node)}")

    def add_nodes(self, *nodes: Node) -> None:
        """批量添加节点
        
        Example:
            topo.add_nodes(h1, h2, sw1)
        """
        for node in nodes:
            self.add_node(node)
    
    def get_node(self, node_or_name: Union[str, Node]) -> Node:
        """获取节点
        
        Args:
            node_or_name: 节点名称或节点对象
            
        Returns:
            节点对象
            
        Raises:
            KeyError: 如果节点不存在
        """
        if isinstance(node_or_name, Node):
            name = node_or_name.name
        else:
            name = node_or_name
            
        if name not in self._nodes:
            raise KeyError(f"节点 {name} 不存在")
        return self._nodes[name]
    
    def remove_node(self, node_or_name: Union[str, Node]) -> None:
        """移除节点
        
        Args:
            node_or_name: 节点名称或节点对象
            
        Raises:
            KeyError: 如果节点不存在
            RuntimeError: 如果节点还有连接的接口
        """
        node = self.get_node(node_or_name)
        name = node.name
        
        if node.interfaces:
            raise RuntimeError(
                f"节点 {name} 还有 {len(node.interfaces)} 个连接的接口，"
                f"请先移除相关链路"
            )
        
        del self._nodes[name]
        logger.info(f"移除节点: {name}")
    
    def add_link(
        self,
        node1_or_name: Union[str, Node],
        node2_or_name: Union[str, Node],
        config: Optional[LinkConfig] = None,
        link_name: Optional[str] = None,
        subnet: Optional[IPv4Network] = None
    ) -> Link:
        """在两个节点之间添加链路
        
        支持多种链路类型：
        1. 点对点链路：add_link("H1", "H2") - 每个链路独立子网
        2. 主机-交换机：add_link("H1", "SW1") - 同一交换机共享子网
        3. 主机-路由器：add_link("H1", "R1") - 每个链路独立子网
        4. 交换机-交换机：add_link("SW1", "SW2") - trunk 链路,不分配 IP
        5. 交换机-路由器：add_link("SW1", "R1") - 路由器端分配 IP
        
        子网分配策略：
        - 交换机场景：同一交换机的所有主机连接共享一个子网
        - 路由器场景：路由器的每个接口使用独立子网
        - 交换机互联：不分配子网(trunk 链路)
        
        自动处理：
        - 子网分配
        - 接口创建和命名
        - IP 地址分配
        - 链路连接
        
        Args:
            node1_or_name: 节点1（名称或对象）
            node2_or_name: 节点2（名称或对象）
            config: 链路配置，None 则使用默认配置
            link_name: 链路名称，None 则自动生成
            subnet: 指定链路使用的子网（可选）。如果提供，将使用此子网而不是自动分配。
            
        Returns:
            创建的链路对象
            
        Raises:
            KeyError: 如果节点不存在
            ValueError: 如果指定的子网与交换机现有子网冲突
        """
        node1 = self.get_node(node1_or_name)
        node2 = self.get_node(node2_or_name)
        
        # 检测链路类型
        switch = None
        is_switched = False
        is_inter_switch_link = False
        is_router_link = False
        
        # 1. 交换机间链路 (SW1 - SW2)
        if node1.is_switch and node2.is_switch:
            is_inter_switch_link = True
            logger.debug(f"检测到交换机间链路: {node1.name} <-> {node2.name}")
            
        # 2. 路由器-交换机链路 (R1 - SW1)
        elif (node1.is_router and node2.is_switch) or (node2.is_router and node1.is_switch):
            # 确保 node1 是路由器，node2 是交换机
            if node1.is_switch:
                node1, node2 = node2, node1
            
            switch = node2
            is_switched = True
            is_router_link = True
            logger.debug(f"检测到路由器-交换机链路: {node1.name} <-> {node2.name}")

        # 3. 其他路由器链路 (R1 - R2, R1 - H1)
        elif node1.is_router or node2.is_router:
            is_router_link = True
            # 确保路由器在 node1 位置（如果是 R-H）
            # 如果是 R-R，顺序不重要
            if node2.is_router and not node1.is_router:
                node1, node2 = node2, node1
            logger.debug(f"检测到路由器直连链路: {node1.name} <-> {node2.name}")

        # 4. 主机-交换机链路 (H1 - SW1)
        elif node2.is_switch:
            switch = node2
            is_switched = True
        elif node1.is_switch:
            switch = node1
            # 交换节点顺序，确保交换机始终是 node2
            node1, node2 = node2, node1
            is_switched = True
        
        # 对于交换链路，不再复用 Link 对象
        # 每个主机-交换机连接都创建独立的 Link，这样可以有独立的配置（包括 TC）
        # 在网络层面，OVSBridgeBackend 会将同一交换机的链路合并到一个 bridge
        
        # 创建新链路
        # 分配子网（根据链路类型）
        assigned_subnet: Optional[IPv4Network] = None
        
        if is_inter_switch_link:
            # 交换机间链路：不需要子网（trunk 链路，不分配 IP）
            assigned_subnet = None
            if subnet:
                logger.warning("交换机间链路不需要子网，忽略提供的 subnet 参数")
            logger.debug(f"交换机间链路不分配子网 (Trunk)")
        elif is_switched:
            # 主机-交换机链路：同一交换机使用同一子网
            switch_name = switch.name
            if switch_name not in self._switch_subnets:
                # 首次连接该交换机，分配新子网
                if subnet:
                    assigned_subnet = subnet
                else:
                    assigned_subnet = next(self._subnet_iterator)
                
                self._switch_subnets[switch_name] = assigned_subnet
                self._ip_allocator.add_network(assigned_subnet)
                logger.debug(f"交换机 {switch_name} 分配子网: {assigned_subnet}")
            else:
                # 复用该交换机的子网
                existing_subnet = self._switch_subnets[switch_name]
                if subnet and subnet != existing_subnet:
                    raise ValueError(
                        f"交换机 {switch_name} 已绑定子网 {existing_subnet}，"
                        f"无法将新链路绑定到不同的子网 {subnet}"
                    )
                assigned_subnet = existing_subnet
                logger.debug(f"交换机 {switch_name} 复用子网: {assigned_subnet}")
        else:
            # 点对点链路（主机-主机、路由器-X）：每个链路独立子网
            if subnet:
                assigned_subnet = subnet
            else:
                assigned_subnet = next(self._subnet_iterator)
            
            self._ip_allocator.add_network(assigned_subnet)
            logger.debug(f"点对点链路分配独立子网: {assigned_subnet}")
        
        # 创建链路
        self._link_counter += 1
        name = link_name or f"link-{self._link_counter}"
        link_config = config or LinkConfig.create_default()
        link = Link(name, assigned_subnet, link_config, switch=switch)
        self._links[name] = link
        
        # 为节点创建接口
        if is_inter_switch_link:
            # 交换机间链路：两端都不分配 IP（trunk 链路）
            self._create_interface_for_link(node1, link, assign_ip=False)
            self._create_interface_for_link(node2, link, assign_ip=False)
            logger.debug(f"交换机间链路不分配 IP")
        elif is_switched:
            # 交换链路（主机-交换机 或 路由器-交换机）
            # node1 (主机/路由器) 分配 IP
            # node2 (交换机) 不分配 IP
            self._create_interface_for_link(node1, link, assign_ip=True)
            self._create_interface_for_link(node2, link, assign_ip=False)
        elif is_router_link:
            # 路由器直连链路 (R-R, R-H)：两端都分配 IP
            # 注意：R-SW 已经被上面的 is_switched 处理了
            self._create_interface_for_link(node1, link, assign_ip=True)
            self._create_interface_for_link(node2, link, assign_ip=True)
        else:
            # 点对点链路（主机-主机）：两端都分配IP
            self._create_interface_for_link(node1, link)
            self._create_interface_for_link(node2, link)
        
        logger.info(f"添加链路: {link}")
        return link
    
    def _create_interface_for_link(self, node: Node, link: Link, assign_ip: bool = True) -> Interface:
        """为节点创建接口并连接到链路
        
        Args:
            node: 节点对象
            link: 链路对象
            assign_ip: 是否分配 IP 地址（交换机节点不需要）
            
        Returns:
            创建的接口对象
        """
        # 自动生成接口名称
        iface_name = f"eth{len(node.interfaces)}"
        
        # 创建接口
        interface = Interface(iface_name, node)
        node.add_interface(interface)
        
        # 连接到链路
        link.attach(interface)
        
        # 为非交换机节点分配 IP
        if assign_ip:
            if link.subnet is None:
                raise ValueError(
                    f"无法为节点 {node.name} 分配 IP：链路 {link.name} 没有关联子网"
                )
            
            # 传递节点名作为 hint，供策略使用
            ip_address = self._ip_allocator.allocate_ip(link.subnet, hint=node.name)
            interface.assign_ip(ip_address)
            logger.debug(
                f"为节点 {node.name} 创建接口 {iface_name}，"
                f"IP: {ip_address}/{link.subnet.prefixlen}"
            )
        else:
            logger.debug(
                f"为节点 {node.name} 创建接口 {iface_name}（无IP）"
            )
        
        return interface
    
    def remove_link(self, link_name: str) -> None:
        """移除链路
        
        Args:
            link_name: 链路名称
            
        Raises:
            KeyError: 如果链路不存在
        """
        if link_name not in self._links:
            raise KeyError(f"链路 {link_name} 不存在")
        
        link = self._links[link_name]
        
        # 断开所有接口
        for interface in link.interfaces:
            link.detach(interface)
            # 注意：这里不删除接口对象，只是断开连接
        
        del self._links[link_name]
        logger.info(f"移除链路: {link_name}")
    
    def set_default_gateway(
        self,
        client_node_or_name: Union[str, Node],
        gateway_node_or_name: Union[str, Node]
    ) -> None:
        """为节点设置默认网关
        
        记录网关节点名称，实际的 IP 配置在运行时由控制器处理。
        
        Args:
            client_node_or_name: 客户端节点（名称或对象，必须是 host 类型）
            gateway_node_or_name: 网关节点（名称或对象）
            
        Raises:
            KeyError: 如果节点不存在
            ValueError: 如果节点类型不适合配置网关或两节点间没有直接链路
        """
        client_node = self.get_node(client_node_or_name)
        gateway_node = self.get_node(gateway_node_or_name)
        
        client_node_name = client_node.name
        gateway_node_name = gateway_node.name
        
        # 验证客户端节点类型（只有主机需要配置网关）
        if not client_node.is_host:
            raise ValueError(
                f"{client_node.node_type} 类型的节点不应配置默认网关。"
                f"只有 host 节点需要默认网关。"
            )
        
        # 验证两节点是否在同一个子网内（L2 可达）
        # 支持两种情况：
        # 1. 直接连接：H1 <-> R1 (共享同一个 Link 对象)
        # 2. 通过交换机连接：H1 <-> SW1 <-> R1 (共享同一个子网)
        gateway_interface = None
        
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
                
                # 检查是否在同一子网
                if gw_iface.link.subnet == client_subnet:
                    gateway_interface = gw_iface
                    break
            
            if gateway_interface:
                break
        
        if not gateway_interface:
            raise ValueError(
                f"无法找到节点 {client_node_name} 和 {gateway_node_name} "
                f"之间的直接链路或共享子网"
            )
        
        if not gateway_interface.has_ip:
            # 理论上上面的检查已经涵盖了，但为了保险
            raise ValueError(
                f"网关接口 {gateway_node_name}[{gateway_interface.name}] "
                f"没有分配 IP 地址"
            )
        
        # 保存网关映射（在拓扑层，而非节点层）
        self._gateways[client_node_name] = gateway_node_name
        
        logger.info(
            f"设置节点 {client_node_name} 的默认网关: {gateway_node_name} "
            f"({gateway_interface.ip_address})"
        )
    
    def clear(self) -> None:
        """清空拓扑"""
        self._nodes.clear()
        self._links.clear()
        self._gateways.clear()
        self._ip_allocator.reset()
        self._link_counter = 0
        logger.info("拓扑已清空")
    
    def __repr__(self) -> str:
        return (
            f"Topology(nodes={self.node_count}, "
            f"links={self.link_count})"
        )

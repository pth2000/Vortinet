"""
此模块定义了网络拓扑的容器模型。
"""
from ipaddress import IPv4Network
from typing import overload, TypeVar
from .ip_tools import IPAddressAllocator
from .abstractions import Node, Link

# 创建一个类型变量，它可以是Node或其任何子类
TNode = TypeVar('TNode', bound=Node)


class Topology:
    """网络拓扑的容器，管理节点、链路和IP地址分配。"""

    def __init__(self, base_network_cidr: str = "10.10.0.0/16", subnet_prefixlen: int = 24):
        self.nodes: dict[str, Node] = {}  # key: 节点名称, value: Node对象
        self.links: dict[str, Link] = {}  # key: 链路名称, value: Link对象
        self.ip_allocator = IPAddressAllocator()
        self._base_network = IPv4Network(base_network_cidr)
        self._subnet_prefixlen = subnet_prefixlen
        self._subnet_iterator = self._base_network.subnets(new_prefix=self._subnet_prefixlen)
        self._link_counter = 0

    @overload
    def add_node(self, name: str, **kwargs) -> Node:
        ...

    @overload
    def add_node(self, node: TNode) -> TNode:
        ...

    def add_node(self, name_or_node, **kwargs):
        """
        向拓扑中添加一个新节点。
        此方法支持两种重载：
        1. add_node(name: str, **kwargs): 通过名称和属性创建一个标准Node。
        2. add_node(node: Node): 直接添加一个Node对象或其子类的实例。
        """
        if isinstance(name_or_node, Node):
            node = name_or_node
            if node.name in self.nodes:
                raise ValueError(f"节点 {node.name} 已存在。")
            self.nodes[node.name] = node
            return node

        if isinstance(name_or_node, str):
            name = name_or_node
            if name in self.nodes:
                raise ValueError(f"节点 {name} 已存在。")
            node = Node(name, **kwargs)
            self.nodes[name] = node
            return node

        raise TypeError("add_node() 参数必须是 str 或 Node 的实例")

    def get_node(self, name: str) -> Node:
        """通过名称获取一个节点对象。"""
        node = self.nodes.get(name)
        if not node:
            raise KeyError(f"节点 {name} 未找到。")
        return node

    def add_link(self, node1_name: str, node2_name: str, **kwargs) -> Link:
        """在两个节点之间添加一条链路，并自动处理接口和IP。"""
        node1 = self.get_node(node1_name)
        node2 = self.get_node(node2_name)

        # 1. 创建链路并分配子网
        self._link_counter += 1
        link_name = f"link-{self._link_counter}"
        subnet = next(self._subnet_iterator)
        self.ip_allocator.add_network(subnet)
        link = Link(name=link_name, subnet=subnet, **kwargs)
        self.links[link_name] = link

        # 2. 为每个节点创建和配置接口
        iface1_name = f"eth{len(node1.interfaces)}"
        iface1 = node1.add_interface(iface1_name)
        link.attach(iface1)
        ip1 = self.ip_allocator.allocate_ip(subnet)
        iface1.assign_ip(ip1)

        iface2_name = f"eth{len(node2.interfaces)}"
        iface2 = node2.add_interface(iface2_name)
        link.attach(iface2)
        ip2 = self.ip_allocator.allocate_ip(subnet)
        iface2.assign_ip(ip2)

        return link

    def set_default_gateway(self, client_node_name: str, gateway_node_name: str):
        """
        为一个节点设置默认网关。
        网关IP是根据两个节点之间的共享链路上的 gateway_node_name 的IP地址自动确定的。
        """
        client_node = self.get_node(client_node_name)
        gateway_node = self.get_node(gateway_node_name)

        # 查找两个节点之间的共同链路
        common_link = None
        for iface in client_node.interfaces.values():
            if iface.link:
                # 检查网关节点是否也在此链路上
                for gw_iface in iface.link.interfaces:
                    if gw_iface.node == gateway_node:
                        common_link = iface.link
                        break
            if common_link:
                break

        if not common_link:
            raise ValueError(f"无法找到节点 {client_node_name} 和 {gateway_node_name} 之间的直接链路。")

        # 在该链路上找到网关的接口以获取其IP
        gateway_ip = None
        for iface in common_link.interfaces:
            if iface.node == gateway_node:
                if not iface.ip_address:
                    raise ValueError(f"网关接口 {gateway_node_name}[{iface.name}] 没有分配IP地址。")
                gateway_ip = str(iface.ip_address)
                break

        if not gateway_ip:
            # This should be unreachable if common_link is found, but for safety
            raise ValueError(f"无法在共享链路上找到网关节点 {gateway_node_name} 的IP地址。")

        client_node.attributes['default_gateway'] = gateway_ip

    def __str__(self) -> str:
        """返回拓扑结构的文本表示。"""
        output = []
        output.append("="*20 + " Topology Summary " + "="*20)

        output.append(f"Nodes ({len(self.nodes)}):")
        sorted_nodes = sorted(self.nodes.items())
        for name, node in sorted_nodes:
            output.append(f"  - Node: {name} (Type: {node.node_type}, Image: {node.attributes.get('image', 'N/A')})")
            sorted_interfaces = sorted(node.interfaces.items())
            for iface_name, iface in sorted_interfaces:
                if iface.link and iface.ip_address:
                    output.append(f"    - {iface_name}: {iface.ip_address}/{iface.link.subnet.prefixlen} -> connects to {iface.link.name}")
                else:
                    output.append(f"    - {iface_name}: (Not connected or no IP)")

        output.append(f"\nLinks ({len(self.links)}):")
        sorted_links = sorted(self.links.items())
        for name, link in sorted_links:
            connected_nodes = " <--> ".join(sorted([iface.node.name for iface in link.interfaces]))
            output.append(f"  - Link: {name} (Subnet: {link.subnet})")
            output.append(f"    - Connects: {connected_nodes}")

        output.append("="*58)
        return "\n".join(output)

    def display(self):
        """
        使用 rich 在终端上以“仪表盘”风格进行格式化打印。
        """
        from rich.console import Console, Group
        from rich.panel import Panel
        from rich.table import Table
        from rich.tree import Tree
        from rich.layout import Layout
        from rich.columns import Columns
        from rich.box import ROUNDED
        console = Console(width=120)

        # --- 1. 构建各个组件 (Components) ---

        # 面板 (Panel): 精简信息，作为总览
        summary_panel = Panel(
            f"[bold]Nodes:[/] [bold yellow]{len(self.nodes)}[/]\n"
            f"[bold]Links:[/] [bold yellow]{len(self.links)}[/]",
            title="[bold #8FBCBB]📊 Topology Summary[/]",
            border_style="#4C566A",
            padding=(1, 2)
        )

        # 节点树 (Tree): 优化图标和颜色
        node_tree = Tree("💻 [bold #81A1C1]Nodes[/]", guide_style="#616E88")
        sorted_nodes = sorted(self.nodes.items())
        for name, node in sorted_nodes:
            image = node.attributes.get('image', '[dim]N/A[/dim]')
            node_branch = node_tree.add(
                f"[#D08770]{name}[/] [dim](Type: {node.node_type}, Image: {image})[/dim]"
            )
            for iface_name, iface in sorted(node.interfaces.items()):
                # 使用 Emoji 🔌 作为图标，兼容性极佳
                icon = "🔌"
                if iface.link and iface.ip_address:
                    ip_info = f"[#A3BE8C]{iface.ip_address}/{iface.link.subnet.prefixlen}[/]"
                    conn_info = f"-> [bold #88C0D0]{iface.link.name}[/]"
                    node_branch.add(f"{icon} {iface_name}: {ip_info} {conn_info}")
                else:
                    node_branch.add(f"{icon} {iface_name}: [red](Not connected)[/red]")

        # 链接表格 (Table): 优化样式和颜色
        link_table = Table(
            title="🔗 [bold #81A1C1]Links[/]",
            box=ROUNDED,  # 使用圆角边框
            border_style="#4C566A",
            header_style="bold #8FBCBB",
            padding=(0, 1)
        )
        link_table.add_column("Link Name", style="#B48EAD")
        link_table.add_column("Subnet", style="#EBCB8B")
        link_table.add_column("Connections", style="white")  # 连接信息用白色，避免歧义

        for name, link in sorted(self.links.items()):
            parts = [f"[#D08770]{iface.node.name}[/]([#A3BE8C]{iface.name}[/])"
                     for iface in sorted(link.interfaces, key=lambda x: x.node.name)]
            connected_str = " [dim]<-->[/dim] ".join(parts)
            link_table.add_row(name, str(link.subnet), connected_str)

        # --- 2. 组合布局 (Layout) ---

        # 将节点树和链接表格放入一个 Columns 对象中，实现并排布局
        # renderable_map 将组件映射到名称，方便在 Layout 中引用
        layout = Layout()
        layout.split(
            Layout(summary_panel, name="header", size=5),
            Layout(ratio=1, name="main"),
        )
        # 仅当终端宽度足够时才并排，否则垂直排列
        if console.width > 110:
            layout["main"].split_row(Layout(node_tree), Layout(link_table))
        else:
            layout["main"].split_column(Layout(node_tree), Layout(link_table))

        # --- 3. 打印最终布局 ---
        console.print(layout)


class TopologyFactory:
    """
    一个用于创建预设拓扑结构的工厂类。
    所有方法都是静态的，可以直接调用，无需实例化该类。
    """

    @staticmethod
    def create_circle_topology(node_count: int, node_prefix: str = "R", **node_kwargs) -> Topology:
        """
        创建一个环形拓扑。

        :param node_count: 节点数量。
        :param node_prefix: 节点名称前缀。
        :param node_kwargs: 创建节点时要传递的其他属性（例如 image, command）。
        :return: 一个配置好的 Topology 对象。
        """
        if node_count < 1:
            raise ValueError("节点数量必须大于等于1")

        topo = Topology()
        nodes = [f"{node_prefix}{i+1}" for i in range(node_count)]

        # 添加节点
        for name in nodes:
            topo.add_node(name, **node_kwargs)

        if node_count > 1:
            # 添加环形链路
            for i in range(node_count):
                node1_name = nodes[i]
                node2_name = nodes[(i + 1) % node_count]
                topo.add_link(node1_name, node2_name)

        return topo

    @staticmethod
    def create_grid_topology(rows: int, cols: int, node_prefix: str = "R", **node_kwargs) -> Topology:
        """
        创建一个网格形拓扑。

        :param rows: 网格的行数。
        :param cols: 网格的列数。
        :param node_prefix: 节点名称前缀。
        :param node_kwargs: 创建节点时要传递的其他属性（例如 image, command）。
        :return: 一个配置好的 Topology 对象。
        """
        if rows < 1 or cols < 1:
            raise ValueError("行数和列数必须大于等于1")

        topo = Topology()
        node_names = [[f"{node_prefix}-{i+1}-{j+1}" for j in range(cols)] for i in range(rows)]

        # 添加节点
        for i in range(rows):
            for j in range(cols):
                topo.add_node(node_names[i][j], **node_kwargs)

        # 添加水平链路
        for i in range(rows):
            for j in range(cols - 1):
                topo.add_link(node_names[i][j], node_names[i][j+1])

        # 添加竖直链路
        for i in range(rows - 1):
            for j in range(cols):
                topo.add_link(node_names[i][j], node_names[i+1][j])

        return topo

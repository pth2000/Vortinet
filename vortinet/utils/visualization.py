"""
拓扑可视化工具

提供拓扑的终端展示和图形化导出功能。
"""

from typing import Optional, Dict, List, TYPE_CHECKING
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich import box

if TYPE_CHECKING:
    from ..models.topology import Topology
    from ..models.node import Node
    from ..models.link import Link

class TopologyVisualizer:
    """拓扑可视化器"""
    
    def __init__(self, topology: "Topology"):
        self.topology = topology
        self.console = Console()

    def show(self):
        """在终端显示拓扑概览"""
        self._print_node_summary()
        self._print_link_summary()
        self._print_structure_tree()

    def _print_node_summary(self):
        """打印节点摘要表"""
        table = Table(title=f"拓扑节点概览 ({self.topology.node_count} 个)", box=box.ROUNDED)
        table.add_column("节点名称", style="cyan", no_wrap=True)
        table.add_column("类型", style="magenta")
        table.add_column("接口", style="green")
        table.add_column("配置摘要", style="yellow")

        for node in self.topology.nodes.values():
            # 收集接口信息
            ifaces = []
            for iface in node.interfaces.values():
                ip = str(iface.ip_address) if iface.ip_address else "No IP"
                ifaces.append(f"{iface.name}: {ip}")
            
            iface_str = "\n".join(ifaces) if ifaces else "-"
            
            # 收集配置摘要
            config_summary = []
            if node.node_type == "frr_router":
                frr_conf = node.config.services.get('frr')
                if frr_conf:
                    daemons = ",".join(frr_conf.daemons)
                    config_summary.append(f"Daemons: {daemons}")
                    if frr_conf.auto_ospf:
                        config_summary.append("Auto-OSPF: On")
            
            table.add_row(
                node.name,
                node.node_type,
                iface_str,
                "\n".join(config_summary) or "-"
            )

        self.console.print(table)

    def _print_link_summary(self):
        """打印链路摘要表"""
        table = Table(title=f"链路概览 ({self.topology.link_count} 条)", box=box.ROUNDED)
        table.add_column("链路名称", style="blue")
        table.add_column("连接", style="white")
        table.add_column("子网", style="green")
        table.add_column("类型", style="yellow")

        for link in self.topology.links.values():
            # 构建连接描述
            connections = []
            for iface in link.interfaces:
                connections.append(f"{iface.node.name}:{iface.name}")
            
            conn_str = " <--> ".join(connections)
            subnet_str = str(link.subnet) if link.subnet else "Trunk/None"
            
            link_type = "P2P"
            if link.switch:
                link_type = f"Switched ({link.switch.name})"
            
            table.add_row(link.name, conn_str, subnet_str, link_type)

        self.console.print(table)

    def _print_structure_tree(self):
        """打印结构树（以路由器/交换机为核心）"""
        # 简单的树形展示，尝试找到核心节点
        # 这里简单地列出所有网络设备及其连接的主机
        
        root = Tree("🕸️ 拓扑结构视图")
        
        # 分类节点
        network_devices = []
        hosts = []
        
        for node in self.topology.nodes.values():
            if node.is_router or node.is_switch:
                network_devices.append(node)
            else:
                hosts.append(node)
        
        # 网络设备子树
        if network_devices:
            net_tree = root.add("网络设备 (Routers & Switches)")
            for dev in network_devices:
                dev_node = net_tree.add(f"[{'magenta' if dev.is_router else 'blue'}]{dev.name}[/] ({dev.node_type})")
                # 列出连接的邻居
                for iface in dev.interfaces.values():
                    if iface.link:
                        for remote_iface in iface.link.interfaces:
                            if remote_iface.node != dev:
                                link_info = f"-- {iface.link.subnet} --" if iface.link.subnet else "--"
                                dev_node.add(f"{link_info} {remote_iface.node.name}")

        # 如果没有网络设备，或者有孤立主机，也应该显示
        # 这里简单处理：如果没有网络设备，则显示所有主机及其连接
        if not network_devices and hosts:
            host_tree = root.add("主机 (Hosts)")
            for host in hosts:
                host_node = host_tree.add(f"[green]{host.name}[/] ({host.node_type})")
                # Show connections
                for iface in host.interfaces.values():
                    if iface.link:
                        for remote_iface in iface.link.interfaces:
                            if remote_iface.node != host:
                                link_info = f"-- {iface.link.subnet} --" if iface.link.subnet else "--"
                                host_node.add(f"{link_info} {remote_iface.node.name}")
        
        self.console.print(root)

    def generate_mermaid(self) -> str:
        """生成 Mermaid 流程图代码"""
        lines = ["graph TD"]
        
        # 定义样式
        lines.append("    classDef router fill:#f9f,stroke:#333,stroke-width:2px;")
        lines.append("    classDef switch fill:#9cf,stroke:#333,stroke-width:2px;")
        lines.append("    classDef host fill:#dfd,stroke:#333,stroke-width:2px;")
        
        # 添加节点
        for node in self.topology.nodes.values():
            style_class = "host"
            shape_start, shape_end = "[", "]"
            
            if node.is_router:
                style_class = "router"
                shape_start, shape_end = "(", ")"
            elif node.is_switch:
                style_class = "switch"
                shape_start, shape_end = "{", "}"
                
            # 节点定义: Name(Name<br/>IPs)
            ips = [str(i.ip_address) for i in node.interfaces.values() if i.ip_address]
            label = f"{node.name}"
            if ips:
                label += f"<br/>{', '.join(ips)}"
            
            lines.append(f"    {node.name}{shape_start}\"{label}\"{shape_end}:::{style_class}")

        # 添加链路
        # 为了避免重复连线，我们需要跟踪已处理的连接
        processed_links = set()
        
        for link in self.topology.links.values():
            if link.name in processed_links:
                continue
            
            if len(link.interfaces) >= 2:
                # 简单的两点连接
                # 对于多点连接（如通过交换机），在 Vortinet 模型中，
                # 主机-交换机是单独的 Link 对象，所以这里处理的是每一段物理/逻辑链路
                
                n1 = link.interfaces[0].node.name
                n2 = link.interfaces[1].node.name
                
                # 标签：子网
                text = str(link.subnet) if link.subnet else ""
                
                lines.append(f"    {n1} -- \"{text}\" --- {n2}")
            
            processed_links.add(link.name)
            
        return "\n".join(lines)

    def save_mermaid(self, filepath: str):
        """保存 Mermaid 文件"""
        content = self.generate_mermaid()
        with open(filepath, 'w') as f:
            f.write(content)
        self.console.print(f"[green]Mermaid 拓扑图已保存至: {filepath}[/green]")

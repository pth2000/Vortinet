"""
此模块定义了构成网络拓扑的基础抽象组件。
"""
from __future__ import annotations
from ipaddress import IPv4Address, IPv4Network

class Node:
    """网络节点的抽象表示。"""

    def __init__(self, name: str, **kwargs):
        # 为基础节点设置默认属性
        defaults = {
            'node_type': 'base',
            'image': 'vortinet_base:latest', # 镜像标签由目录名决定
            'build': {
                'path': './dockerfile/vortinet_base',
                'dockerfile': 'Dockerfile'
            }
        }
        # 用户传入的kwargs可以覆盖默认值
        defaults.update(kwargs)

        self.name = name
        self.node_type = defaults.pop('node_type')
        self.interfaces: dict[str, Interface] = {}  # key: 接口名称, value: Interface对象
        self.attributes = defaults  # 存储节点的其他属性，如镜像、启动命令、构建信息等

    def add_interface(self, interface_name: str) -> Interface:
        """为节点添加一个网络接口。"""
        if interface_name in self.interfaces:
            raise ValueError(f"接口 {interface_name} 已存在于节点 {self.name}")
        interface = Interface(name=interface_name, node=self)
        self.interfaces[interface_name] = interface
        return interface

class Interface:
    """网络接口的抽象表示。"""

    def __init__(self, name: str, node: Node):
        self.name = name
        self.node = node
        self.link: Link | None = None
        self.ip_address: IPv4Address | None = None

    def assign_ip(self, ip_address: IPv4Address):
        """为接口分配IP地址。"""
        self.ip_address = ip_address

    def connect_to(self, link: Link):
        """将此接口连接到一个链路上。"""
        if self.link:
            raise ConnectionError(f"接口 {self.name} 已连接到 {self.link.name}")
        self.link = link

class Link:
    """网络链路的抽象表示，连接多个接口。"""

    def __init__(self, name: str, subnet: IPv4Network, **kwargs):
        self.name = name
        self.subnet = subnet
        self.interfaces: list[Interface] = []  # 连接到此链路的接口列表

        # Traffic Control (TC) parameters
        self.delay: str | None = kwargs.get('delay')
        self.loss: float | None = kwargs.get('loss')
        self.bandwidth: int | None = kwargs.get('bandwidth')  # in kbit/s
        self.attributes = kwargs  # 存储链路的其他属性

    def attach(self, interface: Interface):
        """将一个接口连接到此链路上。"""
        if len(self.interfaces) >= 2:
            # 通常一个点对点链路只连接两个接口
            print(f"警告: 链路 {self.name} 已连接了 {len(self.interfaces)} 个接口。")
        interface.connect_to(self)
        self.interfaces.append(interface)

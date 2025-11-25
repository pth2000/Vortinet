#!/usr/bin/env python3
"""
示例 02: OVS 交换机网络

展示如何使用 Open vSwitch (OVS) 连接多个主机，形成一个局域网。

拓扑结构:
       H1
       |
       SW1 -- H2
       |
       H3

    所有主机在同一子网 (例如 10.10.0.0/24)

关键概念:
1. 创建 OVS 交换机 (create_ovs_switch)
2. 共享子网机制 (Access Link)
3. 二层交换验证
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from vortinet import Topology, create_host_node, create_ovs_switch
from vortinet.deployment import DeploymentController

def main():
    print("="*60)
    print("示例 02: OVS 交换机网络")
    print("="*60)

    topo = Topology("ovs_demo")

    # 1. 创建节点
    h1 = create_host_node("H1")
    h2 = create_host_node("H2")
    h3 = create_host_node("H3")
    sw1 = create_ovs_switch("SW1")

    topo.add_nodes(h1, h2, h3, sw1)

    # 2. 创建链路
    # 所有主机连接到同一个交换机
    # 系统会自动检测到这是交换网络，并让所有主机共享同一个子网
    topo.add_link("H1", "SW1")
    topo.add_link("H2", "SW1")
    topo.add_link("H3", "SW1")

    with DeploymentController("ovs_demo") as controller:
        controller.deploy(topo)
        
        print("\n[验证网络信息]")
        # 从拓扑对象获取 IP 信息
        for node_name in ["H1", "H2", "H3"]:
            node = topo.get_node(node_name)
            ip = node.get_interface("eth0").ip_address
            print(f"{node_name}: {ip}")

        print("\n[验证连通性]")
        # 使用 ping_all 测试全网连通性
        if controller.ping_all():
            print("✓ 二层交换正常")
        else:
            print("✗ 二层交换异常")
        
        input("\n按 Enter 键清理资源并退出...")

if __name__ == "__main__":
    main()

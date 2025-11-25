#!/usr/bin/env python3
"""
示例 04: 路由器与网关

展示如何使用路由器连接两个不同的子网，并配置默认网关。

拓扑结构:
    H1 <----> R1 <----> H2
    (.1.2)   (.1.1)    (.2.1)   (.2.2)
    Subnet A           Subnet B

关键概念:
1. create_router_node (启用 IP 转发)
2. 自动子网分配 (AutoSubnetStrategy)
3. 设置默认网关 (topo.set_default_gateway)
4. 跨网段通信
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from vortinet import Topology, create_host_node, create_router_node
from vortinet.deployment import DeploymentController

def main():
    print("="*60)
    print("示例 04: 路由器与网关")
    print("="*60)

    topo = Topology("router_demo")

    # 1. 创建节点
    # 路由器节点默认开启 ip_forward
    r1 = create_router_node("R1")
    h1 = create_host_node("H1")
    h2 = create_host_node("H2")

    topo.add_nodes(r1, h1, h2)

    # 2. 创建链路
    # H1 - R1: 系统分配子网 A
    topo.add_link("H1", "R1")
    
    # H2 - R1: 系统分配子网 B
    topo.add_link("H2", "R1")

    # 3. 设置默认网关
    # 告诉系统 H1 的网关是 R1，H2 的网关也是 R1
    # 系统会自动查找它们之间的直连链路 IP
    topo.set_default_gateway("H1", "R1")
    topo.set_default_gateway("H2", "R1")

    with DeploymentController("router_demo") as controller:
        controller.deploy(topo)
        
        print("\n[验证路由表]")
        # 查看 H1 的路由表，确认默认网关
        print("H1 路由表:")
        _, out = controller.exec_in_node("H1", "ip route show")
        print(out.decode().strip())

        print("\n[验证跨网段通信]")
        # 使用 ping 方法测试跨网段通信
        if controller.ping("H1", "H2"):
            print("✓ 路由转发成功")
        else:
            print("✗ 路由转发失败")
            
        input("\n按 Enter 键清理资源并退出...")

if __name__ == "__main__":
    main()

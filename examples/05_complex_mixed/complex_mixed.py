#!/usr/bin/env python3
"""
示例 05: 混合复杂拓扑

展示路由器、交换机、手动 IP 分配的综合应用。

拓扑结构:
    Subnet 192.168.1.0/24
    H1 (.10) --+
               |
              SW1 ---- R1 (.254) ---- H3 (自动分配)
               |
    H2 (.20) --+

关键概念:
1. IP 预留 (reserve_ip)
2. 混合拓扑 (Router + Switch)
3. 显式子网指定 (subnet parameter)
"""

import sys
from pathlib import Path
from ipaddress import IPv4Network

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from vortinet import Topology, create_host_node, create_router_node, create_ovs_switch
from vortinet.deployment import DeploymentController

def main():
    print("="*60)
    print("示例 05: 混合复杂拓扑")
    print("="*60)

    # 1. 使用默认策略 (AutoSubnetStrategy)
    # 默认策略支持预留 IP
    topo = Topology("complex_demo")

    # 2. 定义子网
    subnet1 = IPv4Network("192.168.1.0/24")
    
    # 3. 预留 IP
    # 直接在 Topology 上预留
    topo.reserve_ip("H1", "192.168.1.10", subnet=subnet1)
    topo.reserve_ip("H2", "192.168.1.20", subnet=subnet1)
    topo.reserve_ip("R1", "192.168.1.254", subnet=subnet1)

    # 4. 创建节点
    h1 = create_host_node("H1")
    h2 = create_host_node("H2")
    sw1 = create_ovs_switch("SW1")
    r1 = create_router_node("R1")
    h3 = create_host_node("H3") # 连接在路由器另一端

    topo.add_nodes(h1, h2, sw1, r1, h3)

    # 5. 创建链路
    # SW1 区域：H1, H2, R1
    # 使用 subnet 参数显式指定子网
    topo.add_link("H1", "SW1", subnet=subnet1)
    topo.add_link("H2", "SW1", subnet=subnet1)
    topo.add_link("R1", "SW1", subnet=subnet1)
    
    # R1 - H3 (另一个子网，自动分配)
    # 这里没有预留，将自动分配 (e.g. 10.10.0.1, 10.10.0.2)
    topo.add_link("R1", "H3")
    
    # 设置网关
    topo.set_default_gateway("H1", "R1")
    topo.set_default_gateway("H2", "R1")
    topo.set_default_gateway("H3", "R1")

    with DeploymentController("mixed_demo") as controller:
        controller.deploy(topo, save_topology="mixed_demo.mmd")
        
        print("\n[验证 IP 分配]")
        for node_name in ["H1", "H2", "R1"]:
            node = topo.get_node(node_name)
            # 注意：R1 可能有多个接口，这里我们打印所有接口
            ips = []
            for iface in node.interfaces.values():
                if iface.has_ip:
                    ips.append(f"{iface.name}:{iface.ip_address}")
            print(f"{node_name}: {', '.join(ips)}")
            
        print("\n[验证连通性]")
        # H1 -> H2 (同子网)
        if controller.ping("H1", "H2"):
            print("✓ H1 -> H2 连通")
        else:
            print("✗ H1 -> H2 失败")
        
        # H1 -> H3 (跨子网)
        if controller.ping("H1", "H3"):
            print("✓ H1 -> H3 连通")
        else:
            print("✗ H1 -> H3 失败")
        
        input("\n按 Enter 键清理资源并退出...")

if __name__ == "__main__":
    main()

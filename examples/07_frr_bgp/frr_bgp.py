"""
示例 07: FRR BGP 路由配置
============================================================
本示例演示如何使用 FRR 节点运行 BGP 协议，展示了高级配置功能。

拓扑结构:
    R1 (AS 65001) [10.0.0.1/30]
          |
          | (BGP Peering)
          |
    R2 (AS 65002) [10.0.0.2/30]

功能点:
1. 使用 FrrConfig 对象进行高级配置
2. 自定义 BGP 配置 (AS号, Router ID, Neighbor)
3. 关闭自动 OSPF 配置
4. 验证 BGP 邻居建立和路由交换
"""

import sys
import time
from pathlib import Path
from ipaddress import IPv4Network

# 添加项目根目录到 python path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from vortinet import (
    Topology, 
    create_frr_router,
    DeploymentController,
    FrrConfig
)
# from vortinet.services.frr import FrrConfig

def main():
    # 1. 创建拓扑
    topo = Topology("frr_bgp_demo")
    
    # 2. 定义 FRR 配置 (BGP)
    # R1: AS 65001, Router ID 1.1.1.1
    r1_config = FrrConfig(
        daemons=["zebra", "bgpd"],
        auto_ospf=False,
        extra_config=[
            "router bgp 65001",
            " bgp router-id 1.1.1.1",
            " no bgp ebgp-requires-policy",
            " no bgp network import-check",
            " neighbor 10.0.0.2 remote-as 65002",
            " network 10.0.0.0/30",
            " network 1.1.1.1/32",
            "!"
        ]
    )
    
    # R2: AS 65002, Router ID 2.2.2.2
    r2_config = FrrConfig(
        daemons=["zebra", "bgpd"],
        auto_ospf=False,
        extra_config=[
            "router bgp 65002",
            " bgp router-id 2.2.2.2",
            " no bgp ebgp-requires-policy",
            " no bgp network import-check",
            " neighbor 10.0.0.1 remote-as 65001",
            " network 10.0.0.0/30",
            " network 2.2.2.2/32",
            "!"
        ]
    )

    # 3. 创建节点
    r1 = create_frr_router("R1", frr_config=r1_config)
    r2 = create_frr_router("R2", frr_config=r2_config)
    
    topo.add_nodes(r1, r2)
    
    # 4. 创建链路
    # R1 <-> R2 (10.0.0.0/30)
    topo.add_link(r1, r2, subnet=IPv4Network("10.0.0.0/30"))
    
    # 5. 部署
    with DeploymentController("frr_bgp_demo") as controller:
        controller.deploy(topo)
        
        print("\n[等待 BGP 收敛]")
        for i in range(10):
            print(f"等待中... {10-i}s")
            time.sleep(1)
            
        # 6. 验证 BGP 状态
        print("\n[验证 BGP 邻居]")
        print("R1 BGP Summary:")
        _, output = controller.exec_in_node("R1", "vtysh -c 'show ip bgp summary'")
        print(output.decode())
        
        print("\nR2 BGP Summary:")
        _, output = controller.exec_in_node("R2", "vtysh -c 'show ip bgp summary'")
        print(output.decode())
        
        # 7. 验证路由表
        print("\n[验证路由表]")
        print("R1 路由表 (应包含 2.2.2.2/32):")
        _, output = controller.exec_in_node("R1", "vtysh -c 'show ip route'")
        print(output.decode())
        
        input("\n按 Enter 键清理资源并退出...")

if __name__ == "__main__":
    main()

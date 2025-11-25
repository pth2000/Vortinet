"""
示例 06: FRR OSPF 动态路由
============================================================
本示例演示如何使用 FRR (Free Range Routing) 节点运行 OSPF 协议。

拓扑结构:
    H1 [192.168.1.10/24]
     |
    R1 (FRR) [192.168.1.1/24, 10.0.0.1/30]
     |
    R2 (FRR) [10.0.0.2/30, 192.168.2.1/24]
     |
    H2 [192.168.2.10/24]

功能点:
1. 使用 create_frr_router 创建 FRR 节点
2. 自动生成 FRR 配置文件 (daemons, vtysh.conf, frr.conf)
3. 自动宣告 OSPF 网络
4. 验证跨网段连通性
"""

import sys
from pathlib import Path
import time
from ipaddress import IPv4Network

# 添加项目根目录到 python path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from vortinet import (
    Topology, 
    create_host_node, 
    create_frr_router,
    DeploymentController,
    FrrConfig
)

def main():
    # 1. 创建拓扑
    topo = Topology()
    
    # 2. 创建节点
    # 主机
    h1 = create_host_node("H1")
    h2 = create_host_node("H2")
    
    # FRR 路由器配置
    # 显式启用 OSPF 守护进程和自动配置
    ospf_config = FrrConfig(
        daemons=["zebra", "ospfd"],
        auto_ospf=True
    )
    
    # FRR 路由器
    # 注意：首次运行会自动构建 vortinet_frr 镜像
    r1 = create_frr_router("R1", frr_config=ospf_config)
    r2 = create_frr_router("R2", frr_config=ospf_config)
    
    topo.add_node(h1)
    topo.add_node(h2)
    topo.add_node(r1)
    topo.add_node(r2)
    
    # 3. 创建链路
    # H1 -> R1 (192.168.1.0/24)
    topo.add_link(h1, r1, subnet=IPv4Network("192.168.1.0/24"))
    
    # R1 -> R2 (10.0.0.0/30)
    topo.add_link(r1, r2, subnet=IPv4Network("10.0.0.0/30"))
    
    # R2 -> H2 (192.168.2.0/24)
    topo.add_link(r2, h2, subnet=IPv4Network("192.168.2.0/24"))
    
    # 4. 设置默认网关
    # 主机指向直连的路由器接口
    topo.set_default_gateway(h1, r1)
    topo.set_default_gateway(h2, r2)
    
    # 5. 部署
    with DeploymentController("frr_ospf_demo") as controller:
        controller.deploy(topo)
        
        print("\n[等待 OSPF 收敛]")
        # OSPF 需要一些时间来建立邻居和交换路由
        for i in range(10):
            print(f"等待中... {10-i}s")
            time.sleep(1)
            
        print("\n[验证路由表]")
        # 检查 R1 是否学到了 192.168.2.0/24
        print("R1 OSPF Neighbors:")
        _, output = controller.exec_in_node("R1", "vtysh -c 'show ip ospf neighbor'")
        print(output.decode())

        print("R1 路由表:")
        _, output = controller.exec_in_node("R1", "vtysh -c 'show ip route'")
        print(output.decode())
        
        print("\nR2 OSPF Neighbors:")
        _, output = controller.exec_in_node("R2", "vtysh -c 'show ip ospf neighbor'")
        print(output.decode())

        print("\nR2 路由表:")
        _, output = controller.exec_in_node("R2", "vtysh -c 'show ip route'")
        print(output.decode())
        
        print("\n[验证连通性]")
        # H1 -> H2
        controller.ping("H1", "H2")
        
        input("\n按 Enter 键清理资源并退出...")

if __name__ == "__main__":
    main()

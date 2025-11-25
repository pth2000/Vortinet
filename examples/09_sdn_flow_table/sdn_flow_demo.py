#!/usr/bin/env python3
"""
示例 09: SDN 流表控制
============================================================
本示例演示如何手动管理 Open vSwitch 的流表。

拓扑结构:
    h1 [10.0.0.1] <----> sw1 (OVS) <----> h2 [10.0.0.2]

关键概念:
1. 创建 OVS 交换机节点
2. 使用 run_ovs_ofctl 执行 OpenFlow 命令
3. 动态下发流表控制流量 (Drop/Accept)
"""

import sys
import logging
from pathlib import Path
from ipaddress import IPv4Network

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from vortinet import Topology, create_host_node, create_ovs_switch
from vortinet.deployment import DeploymentController

def main():
    print("="*60)
    print("示例 09: SDN 流表控制")
    print("="*60)

    # 1. 定义拓扑
    topo = Topology("sdn_demo")
    
    # 创建节点
    h1 = create_host_node("h1")
    h2 = create_host_node("h2")
    # 创建 OVS 交换机，默认 fail_mode="standalone" (表现像普通交换机)
    sw1 = create_ovs_switch("sw1", openflow_version="OpenFlow13")
    
    topo.add_nodes(h1, h2, sw1)
    
    # 连接节点
    subnet = IPv4Network("10.0.0.0/24")
    topo.reserve_ip(h1, "10.0.0.1", subnet)
    topo.reserve_ip(h2, "10.0.0.2", subnet)
    
    # h1 <-> sw1
    topo.add_link(h1, sw1, subnet=subnet)
    # h2 <-> sw1
    topo.add_link(h2, sw1, subnet=subnet)
    
    # 2. 部署
    with DeploymentController(topo.name) as controller:
        print("Deploying topology...")
        controller.deploy(topo, visualize=True)
        
        print("\n[Step 1] 测试初始连通性 (默认 Standalone 模式)...")
        if controller.ping(h1, h2):
            print("✓ Initial Ping Passed")
        else:
            print("✗ Initial Ping Failed")
            # 如果初始 ping 失败，可能是环境问题，但我们继续演示流表
        
        print("\n[Step 2] 查看当前流表...")
        # dump-flows 输出可能包含默认规则
        flows = controller.run_ovs_ofctl(sw1, ["dump-flows"])
        print(f"Current flows:\n{flows.strip()}")
        
        print("\n[Step 3] 添加流表规则: 丢弃 h1 -> h2 的 ICMP 包...")
        # 匹配: dl_type=0x0800(IP), nw_proto=1(ICMP), nw_src=10.0.0.1, nw_dst=10.0.0.2
        # 动作: drop
        # 注意：OpenFlow 1.3 需要指定协议 ip 或 dl_type=0x0800
        controller.run_ovs_ofctl(sw1, [
            "add-flow", 
            "priority=100,ip,nw_proto=1,nw_src=10.0.0.1,nw_dst=10.0.0.2,actions=drop"
        ])
        
        print("Verifying flows...")
        flows = controller.run_ovs_ofctl(sw1, ["dump-flows"])
        print(f"Current flows:\n{flows.strip()}")
        
        print("\n[Step 4] 测试连通性 (应该失败)...")
        # 期望 ping 失败
        if not controller.ping(h1, h2, count=2, timeout=1):
            print("✓ Ping Blocked as expected")
        else:
            print("✗ Ping Succeeded (Unexpected)")
            
        print("\n[Step 5] 删除流表规则...")
        # 删除刚才添加的规则
        controller.run_ovs_ofctl(sw1, [
            "del-flows", 
            "ip,nw_proto=1,nw_src=10.0.0.1,nw_dst=10.0.0.2"
        ])
        
        print("\n[Step 6] 再次测试连通性 (应该恢复)...")
        if controller.ping(h1, h2):
            print("✓ Ping Restored")
        else:
            print("✗ Ping Failed")

        input("\n按 Enter 键清理资源并退出...")

if __name__ == "__main__":
    main()

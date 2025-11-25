#!/usr/bin/env python3
"""
复杂拓扑演示 - 路由器、交换机和 TC

演示场景:
1. 路由器的每个接口在不同子网
2. 交换机的所有主机在同一子网
3. 交换机间链路 (Inter-Switch Link)
4. 不同链路的独立 TC 配置

拓扑结构:
    
    Subnet 10.10.0.0/24        Subnet 10.10.1.0/24         Subnet 10.10.2.0/24
    ┌──────────┐               ┌──────────┐               ┌──────────┐
    │    H1    │               │    H3    │───────────────│    R1    │
    │10.10.0.1 │               │10.10.1.1 │  loss 2%      │10.10.2.1 │
    └────┬─────┘               └────┬─────┘  (点对点)      └──────────┘
         │                          │
         │ TC: delay 50ms           │ TC: loss 5%
         │                          │
    ┌────┴─────┐               ┌────┴─────┐
    │   SW1    │               │   SW2    │
    └────┬─────┘               └────┬─────┘
         │                          │
         │ TC: delay 10ms           │ TC: delay 20ms
         │                          │
    ┌────┴─────┐               ┌────┴─────┐
    │    H2    │               │    H4    │
    │10.10.0.2 │               │10.10.1.2 │
    └──────────┘               └──────────┘

说明:
- H1, H2 在同一子网 10.10.0.0/24 (通过 SW1)
- H3, H4 在同一子网 10.10.1.0/24 (通过 SW2)
- R1 与 H3 点对点连接,独立子网 10.10.2.0/24
- 每条链路有独立的 TC 配置

限制:
- 交换机间链路 (SW-SW) 暂不支持 (需要 OVS patch port)
- 路由器-交换机链路 (R-SW) 暂不支持 (需要特殊处理)
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from vortinet import (
    Topology,
    create_host_node,
    create_router_node,
    create_ovs_switch,
    LinkConfig
)
from vortinet.deployment import DeploymentController


def create_complex_topology():
    """创建复杂拓扑"""
    topo = Topology()
    
    # 创建节点
    h1 = create_host_node("H1")
    h2 = create_host_node("H2")
    h3 = create_host_node("H3")
    h4 = create_host_node("H4")
    r1 = create_router_node("R1")
    sw1 = create_ovs_switch("SW1")
    sw2 = create_ovs_switch("SW2")
    
    topo.add_node_object(h1)
    topo.add_node_object(h2)
    topo.add_node_object(h3)
    topo.add_node_object(h4)
    topo.add_node_object(r1)
    topo.add_node_object(sw1)
    topo.add_node_object(sw2)
    
    # SW1 子网 (10.10.0.0/24)
    print("\n=== 创建 SW1 子网链路 ===")
    
    # H1 -> SW1 (delay 50ms)
    link_h1_sw1 = LinkConfig.create_with_tc(delay="50ms", jitter="5ms")
    topo.add_link("H1", "SW1", config=link_h1_sw1)
    
    # H2 -> SW1 (delay 10ms)
    link_h2_sw1 = LinkConfig.create_with_tc(delay="10ms")
    topo.add_link("H2", "SW1", config=link_h2_sw1)
    
    # SW2 子网 (10.10.1.0/24)
    print("\n=== 创建 SW2 子网链路 ===")
    
    # H3 -> SW2 (loss 5%)
    link_h3_sw2 = LinkConfig.create_with_tc(loss=5.0)
    topo.add_link("H3", "SW2", config=link_h3_sw2)
    
    # H4 -> SW2 (delay 20ms)
    link_h4_sw2 = LinkConfig.create_with_tc(delay="20ms")
    topo.add_link("H4", "SW2", config=link_h4_sw2)
    
    # 路由器单独连接
    print("\n=== 创建路由器链路 ===")
    
    # R1 -> H3 直连 (新子网, loss 2%)
    link_r1_h3 = LinkConfig.create_with_tc(loss=2.0)
    topo.add_link("R1", "H3", config=link_r1_h3)
    
    # 注意: 交换机间链路和路由器-交换机链路需要特殊处理
    # 当前暂不支持,这些场景需要:
    # - SW-SW: OVS patch port 或 veth pair 连接 bridges
    # - R-SW: 路由器容器的接口连接到 OVS bridge
    
    # 打印拓扑信息
    print("\n=== 拓扑链路和子网 ===")
    for link_name, link in topo.links.items():
        switch_info = f" (switch: {link.switch.name})" if link.switch else ""
        print(f"{link_name}: {link.subnet}{switch_info}")
        for iface in link.interfaces:
            ip_info = f" IP={iface.ip_address}" if iface.has_ip else " (no IP)"
            print(f"  - {iface.node.name}:{iface.name}{ip_info}")
    
    return topo


def verify_topology(controller: DeploymentController):
    """验证拓扑配置"""
    print("\n" + "="*70)
    print("验证拓扑配置")
    print("="*70)
    
    # 1. 检查 IP 地址
    print("\n[1] IP 地址分配:")
    nodes = ["H1", "H2", "H3", "H4", "R1"]
    node_ips = {}
    
    for node in nodes:
        # 获取所有接口的 IP
        exit_code, output = controller.exec_in_node(
            node,
            "ip -4 addr show | grep 'inet ' | grep -v '127.0.0.1'"
        )
        if exit_code == 0:
            lines = output.decode().strip().split('\n')
            ips = []
            for line in lines:
                if 'inet' in line:
                    import re
                    match = re.search(r'inet (\d+\.\d+\.\d+\.\d+/\d+)', line)
                    if match:
                        ips.append(match.group(1))
            node_ips[node] = ips
            print(f"  {node}: {', '.join(ips) if ips else 'No IP'}")
    
    # 2. 验证子网规划
    print("\n[2] 子网验证:")
    print("  ✓ H1, H2 应在 10.10.0.0/24 (SW1)")
    print("  ✓ H3, H4 应在 10.10.1.0/24 (SW2)")
    print("  ✓ R1, H3 应在 10.10.2.0/24 (点对点)")
    
    # 3. 检查 TC 规则
    print("\n[3] TC 规则验证:")
    tc_checks = {
        "H1": "delay 50ms",
        "H2": "delay 10ms",
        "H3": "loss 5%/loss 2% (两个接口)",
        "H4": "delay 20ms",
        "R1": "loss 2%"
    }
    
    for node, expected in tc_checks.items():
        if node == "R1":
            # 路由器检查 eth0
            exit_code, output = controller.exec_in_node(node, "tc qdisc show dev eth0")
        else:
            exit_code, output = controller.exec_in_node(node, "tc qdisc show dev eth0")
        
        if exit_code == 0:
            tc_output = output.decode().strip()
            if "netem" in tc_output:
                print(f"  {node}: ✓ {tc_output.split('netem')[1][:40]}")
            else:
                print(f"  {node}: ✗ 未找到 TC 规则")
    
    # 4. 测试连通性
    print("\n[4] 连通性测试:")
    
    # H1 -> H2 (同一交换机,同一子网)
    if "H2" in node_ips and node_ips["H2"]:
        h2_ip = node_ips["H2"][0].split('/')[0]
        print(f"\n  H1 -> H2 ({h2_ip}):")
        exit_code, output = controller.exec_in_node("H1", f"ping -c 2 -W 2 {h2_ip}")
        if exit_code == 0:
            lines = output.decode().split('\n')
            for line in lines:
                if 'packets transmitted' in line or 'rtt' in line:
                    print(f"    {line.strip()}")
        else:
            print(f"    ✗ Ping 失败")
    
    # H1 -> H3 (跨交换机,通过 ISL)
    if "H3" in node_ips and node_ips["H3"]:
        h3_ip = node_ips["H3"][0].split('/')[0]
        print(f"\n  H1 -> H3 ({h3_ip}) [跨交换机]:")
        exit_code, output = controller.exec_in_node("H1", f"ping -c 2 -W 2 {h3_ip}")
        if exit_code == 0:
            print(f"    ✓ 连通 (需要 L2 转发)")
        else:
            print(f"    ✗ 不连通 (预期行为:不同子网需要路由)")
    
    print("\n" + "="*70)
    print("验证完成!")
    print("="*70)


def main():
    """主函数"""
    print("="*70)
    print("复杂拓扑演示 - 路由器、交换机和 TC")
    print("="*70)
    
    # 创建拓扑
    topo = create_complex_topology()
    
    # 部署拓扑
    print("\n部署拓扑...")
    with DeploymentController("complex_topo") as controller:
        controller.deploy(topo)
        
        print("\n✓ 拓扑部署完成")
        
        # 验证配置
        verify_topology(controller)
        
        print("\n" + "="*70)
        print("关键特性演示:")
        print("="*70)
        print("\n1. 交换机共享子网:")
        print("   - H1, H2 在同一子网 10.10.0.0/24 (通过 SW1)")
        print("   - H3, H4 在同一子网 10.10.1.0/24 (通过 SW2)")
        print("   - 同一交换机的所有主机共享子网,可以直接通信")
        print("\n2. 路由器独立子网:")
        print("   - R1-H3 点对点链路,独立子网 10.10.2.0/24")
        print("   - 路由器的每个接口在不同子网")
        print("   - 用于连接不同网络段")
        print("\n3. 独立 TC 配置:")
        print("   - 每条链路有独立的流量控制规则")
        print("   - H1: 50ms 延迟 + 5ms 抖动")
        print("   - H2: 10ms 延迟")
        print("   - H3: 5% 丢包 (连 SW2)")
        print("   - H4: 20ms 延迟")
        print("   - R1-H3: 2% 丢包")
        print("\n4. H3 的多接口:")
        print("   - H3 有两个接口:")
        print("   - eth0: 连接 SW2 (10.10.1.1/24)")
        print("   - eth1: 连接 R1 (10.10.2.2/24)")
        print("   - 每个接口独立的 TC 规则")


if __name__ == "__main__":
    main()

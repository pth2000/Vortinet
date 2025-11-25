#!/usr/bin/env python3
"""
OVS 交换机 + 流量控制演示

演示如何在 OVS 交换机拓扑中使用流量控制 (TC) 功能,
包括延迟、丢包和带宽限制。
"""

import sys
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from vortinet import (
    Topology,
    create_host_node,
    create_ovs_switch,
    LinkConfig
)
from vortinet.deployment import DeploymentController


def create_tc_topology():
    """创建带流量控制的 OVS 拓扑
    
    拓扑结构:
        H1 ---+
              |
        H2 ---+--- SW1 (with different TC per host)
              |
        H3 ---+
    
    TC 规则 (每个主机独立配置):
    - H1: 延迟 100ms, 抖动 10ms, 丢包 1%
    - H2: 带宽限制 1Mbps, 丢包 5%
    - H3: 丢包 10%, 重复包 2%
    
    重要:
    现在每个 add_link 调用都会创建独立的 Link 对象,
    因此每个主机-交换机连接可以有不同的 TC 配置。
    """
    topo = Topology()
    
    # 创建节点
    h1 = create_host_node("H1")
    h2 = create_host_node("H2")
    h3 = create_host_node("H3")
    sw1 = create_ovs_switch("SW1")
    
    topo.add_node_object(h1)
    topo.add_node_object(h2)
    topo.add_node_object(h3)
    topo.add_node_object(sw1)
    
    # 为每个主机创建独立的 TC 配置
    # H1: 高延迟
    link_config_h1 = LinkConfig.create_with_tc(
        delay="100ms",
        jitter="10ms",
        loss=1.0
    )
    
    # H2: 低带宽 + 丢包
    link_config_h2 = LinkConfig.create_with_tc(
        bandwidth=1024,  # 1 Mbps
        loss=5.0
    )
    
    # H3: 高丢包 + 重复包
    link_config_h3 = LinkConfig.create_with_tc(
        loss=10.0,
        duplicate=2.0
    )
    
    # 每个主机到交换机的连接使用不同的配置
    topo.add_link("H1", "SW1", config=link_config_h1)
    topo.add_link("H2", "SW1", config=link_config_h2)
    topo.add_link("H3", "SW1", config=link_config_h3)
    
    return topo


def verify_tc_rules(controller: DeploymentController):
    """验证 TC 规则是否正确应用"""
    print("\n" + "="*60)
    print("验证 TC 规则配置")
    print("="*60)
    
    hosts_tc_config = {
        "H1": "delay 100.0ms, loss 1%",
        "H2": "bandwidth 1Mbps, loss 5%",
        "H3": "loss 10%, duplicate 2%"
    }
    
    for host, expected in hosts_tc_config.items():
        print(f"\n[{host}] TC 配置 (期望: {expected}):")
        exit_code, output = controller.exec_in_node(host, "tc qdisc show dev eth0")
        
        if exit_code == 0:
            tc_output = output.decode().strip()
            if "netem" in tc_output:
                print(f"  ✓ TC 规则已应用:")
                for line in tc_output.split('\n'):
                    if 'netem' in line:
                        print(f"    {line}")
            else:
                print(f"  ✗ 未找到 netem 规则")
        else:
            print(f"  ✗ 查询失败")


def test_connectivity(controller: DeploymentController):
    """测试连通性和延迟"""
    print("\n" + "="*60)
    print("测试连通性和网络延迟")
    print("="*60)
    
    # 获取 IP 地址
    hosts_ips = {}
    for host in ["H1", "H2", "H3"]:
        exit_code, output = controller.exec_in_node(
            host, 
            "ip -4 addr show eth0 | grep inet | awk '{print $2}' | cut -d/ -f1"
        )
        if exit_code == 0:
            hosts_ips[host] = output.decode().strip()
    
    print("\nIP 地址:")
    for host, ip in hosts_ips.items():
        print(f"  {host}: {ip}")
    
    # 从 H1 ping H2 (H1 有 100ms 延迟)
    print("\n从 H1 ping H2 (H1 有 100ms 出站延迟):")
    target_ip = hosts_ips.get("H2")
    if target_ip:
        print(f"  预期: H1->H2 有 100ms 延迟, H2->H1 正常")
        print(f"  RTT: 约 100ms (只有 H1 出站有延迟)")
        exit_code, output = controller.exec_in_node(
            "H1",
            f"ping -c 3 {target_ip}"
        )
        
        if exit_code == 0:
            lines = output.decode().split('\n')
            for line in lines:
                if 'rtt min/avg/max' in line or '3 packets' in line:
                    print(f"  {line.strip()}")
    
    # 从 H2 ping H1 (观察不同方向的效果)
    print("\n从 H2 ping H1 (H2 有低带宽 + 5% 丢包):")
    target_ip = hosts_ips.get("H1")
    if target_ip:
        print(f"  预期: 可能有丢包,但延迟正常")
        exit_code, output = controller.exec_in_node(
            "H2",
            f"ping -c 5 {target_ip}"
        )
        
        if exit_code == 0:
            lines = output.decode().split('\n')
            for line in lines:
                if 'rtt min/avg/max' in line or 'packets' in line:
                    print(f"  {line.strip()}")


def test_bandwidth(controller: DeploymentController):
    """测试带宽限制"""
    print("\n" + "="*60)
    print("测试带宽限制 (所有主机应该有 10Mbps 限制)")
    print("="*60)
    
    # 在 H3 上启动 iperf3 服务器
    print("\n启动 iperf3 服务器在 H3...")
    exit_code, _ = controller.exec_in_node(
        "H3",
        "which iperf3 > /dev/null 2>&1 || (apt-get update > /dev/null 2>&1 && apt-get install -y iperf3 > /dev/null 2>&1)"
    )
    
    # 后台启动服务器
    controller.exec_in_node(
        "H3",
        "pkill iperf3 2>/dev/null; iperf3 -s -D"
    )
    
    time.sleep(2)
    
    # 获取 H3 的 IP
    exit_code, output = controller.exec_in_node(
        "H3",
        "ip -4 addr show eth0 | grep inet | awk '{print $2}' | cut -d/ -f1"
    )
    h3_ip = output.decode().strip()
    
    # 从 H1 测试到 H3 (应该受到 10Mbps 限制)
    print(f"\nH1 -> H3 带宽测试 (期望: ~10 Mbps):")
    exit_code, output = controller.exec_in_node(
        "H1",
        f"iperf3 -c {h3_ip} -t 5 2>/dev/null || echo 'iperf3 未安装'"
    )
    
    if exit_code == 0 and 'iperf3 未安装' not in output.decode():
        lines = output.decode().split('\n')
        for line in lines:
            if 'sender' in line or 'receiver' in line:
                print(f"  {line.strip()}")
    else:
        print("  需要安装 iperf3 (apt-get install iperf3)")
    
    # 清理
    controller.exec_in_node("H3", "pkill iperf3 2>/dev/null")


def main():
    """主函数"""
    print("="*60)
    print("OVS 交换机 + 流量控制演示")
    print("="*60)
    
    # 创建拓扑
    topo = create_tc_topology()
    
    # 部署拓扑
    print("\n部署拓扑...")
    with DeploymentController("tc_ovs_demo", auto_cleanup=False) as controller:
        controller.deploy(topo)
        
        print("\n✓ 拓扑部署完成")
        
        # 验证 TC 规则
        verify_tc_rules(controller)
        
        # 测试连通性和延迟
        test_connectivity(controller)
        
        print("\n" + "="*60)
        print("演示完成!")
        print("="*60)
        print("\n重要说明:")
        print("  ✓ OVS backend 现在支持独立的 TC 配置")
        print("  ✓ 每个 add_link 调用创建独立的 Link 对象")
        print("  ✓ 不同主机可以有不同的 TC 规则")
        print("\n本例中的配置:")
        print("  • H1: 延迟 100ms, 抖动 10ms, 丢包 1%")
        print("  • H2: 带宽 1Mbps, 丢包 5%")
        print("  • H3: 丢包 10%, 重复包 2%")
        print("\n提示:")
        print("  - 使用 'vortinet_cli.py topology tc_ovs_demo' 查看拓扑")
        print("  - 使用 'vortinet_cli.py exec tc_ovs_demo H1 tc qdisc show' 查看 TC 规则")


if __name__ == "__main__":
    main()

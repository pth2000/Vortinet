#!/usr/bin/env python3
"""
示例 03: 流量控制 (Traffic Control)

展示如何模拟网络损伤，如延迟、丢包、抖动等。

拓扑结构:
    H1 <-----> H2
      (delay 100ms)
      (loss 10%)

关键概念:
1. LinkConfig 配置
2. create_with_tc 工厂方法
3. 验证网络性能
"""

import sys
from pathlib import Path
import re

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from vortinet import Topology, create_host_node, LinkConfig
from vortinet.deployment import DeploymentController

def main():
    print("="*60)
    print("示例 03: 流量控制 (Traffic Control)")
    print("="*60)

    topo = Topology("tc_demo")
    h1 = create_host_node("H1")
    h2 = create_host_node("H2")
    topo.add_nodes(h1, h2)

    # 创建带有 TC 配置的链路
    # 延迟 100ms，丢包 10%
    tc_config = LinkConfig.create_with_tc(
        delay="100ms",
        loss=10.0,
        jitter="10ms"
    )
    
    topo.add_link("H1", "H2", config=tc_config)

    with DeploymentController("tc_demo") as controller:
        controller.deploy(topo)
        
        # 获取 H2 IP
        h2_node = topo.get_node("H2")
        h2_ip = str(h2_node.get_interface("eth0").ip_address)

        print(f"\n[验证延迟] Ping H2 ({h2_ip})...")
        print("预期延迟: ~200ms (往返 100ms * 2)")
        
        # 发送 10 个包以观察丢包
        # 使用 env LANG=C 确保输出为英文，以便解析
        exit_code, output = controller.exec_in_node("H1", f"env LANG=C ping -c 10 -i 0.2 {h2_ip}")
        output_str = output.decode()
        print(output_str)

        # 解析结果
        if "rtt min/avg/max" in output_str:
            # 提取平均延迟
            avg_rtt = re.search(r"rtt.*?/([\d.]+)/", output_str).group(1)
            print(f"实际平均延迟: {avg_rtt} ms")
            
            if float(avg_rtt) > 150:
                print("✓ 延迟模拟生效")
            else:
                print("✗ 延迟模拟未生效")
        
        if "packet loss" in output_str:
            loss_rate = re.search(r"(\d+)% packet loss", output_str).group(1)
            print(f"实际丢包率: {loss_rate}%")
            
            if int(loss_rate) > 0:
                print("✓ 丢包模拟生效")
        
        input("\n按 Enter 键清理资源并退出...")

if __name__ == "__main__":
    main()

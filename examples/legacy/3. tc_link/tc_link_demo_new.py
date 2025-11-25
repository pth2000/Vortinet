#!/usr/bin/env python3
"""
流量控制（TC）示例 - 新架构版本

展示如何使用新架构配置链路质量参数：
- 延迟（delay）
- 丢包率（loss）
- 带宽限制（bandwidth）

新架构特点：
1. 使用 TrafficControlConfig 配置 TC 参数
2. 类型安全的配置验证
3. 自动应用 TC 规则到 veth 接口
"""

import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from vortinet.models.topology import Topology
from vortinet.nodes import create_host_node
from vortinet.config import LinkConfig, TrafficControlConfig
from vortinet.deployment import DeploymentController


def main():
    print("=" * 60)
    print("流量控制（TC）示例（新架构）")
    print("=" * 60)
    
    # 1. 创建拓扑
    print("\n1. 创建拓扑...")
    topo = Topology()
    
    # 创建两个主机
    h1 = create_host_node("H1")
    h2 = create_host_node("H2")
    
    topo.add_node_object(h1)
    topo.add_node_object(h2)
    
    # 创建流量控制配置
    tc_config = TrafficControlConfig(
        delay="100ms",      # 延迟 100ms
        loss=5.0,           # 丢包率 5%
        bandwidth="1mbit"   # 带宽限制 1 Mbit/s
    )
    
    # 创建链路配置
    link_config = LinkConfig(
        traffic_control=tc_config
    )
    
    # 添加链路（带 TC 参数）
    topo.add_link("H1", "H2", config=link_config)
    
    print(f"   节点数: {len(topo.nodes)}")
    print(f"   链路配置:")
    print(f"     - 延迟: 100ms")
    print(f"     - 丢包率: 5%")
    print(f"     - 带宽: 1 Mbit/s")
    
    # 2. 部署拓扑
    print("\n2. 部署拓扑...")
    
    with DeploymentController("tc_link_demo") as controller:
        controller.deploy(topo, default_image="vortinet_base:latest")
        
        session_id = controller.resource_tracker.session_id
        print(f"\n✓ 部署成功!")
        print(f"  会话 ID: {session_id[:16]}...")
        
        # 获取 IP 地址
        print("\n3. 网络配置:")
        exit_code, output = controller.exec_in_node("H1", "hostname -I")
        h1_ip = output.decode().strip().split()[0] if output else ""
        
        exit_code, output = controller.exec_in_node("H2", "hostname -I")
        h2_ip = output.decode().strip().split()[0] if output else ""
        
        print(f"   H1: {h1_ip}")
        print(f"   H2: {h2_ip}")
        
        # 检查 TC 规则
        print("\n4. 验证 TC 规则:")
        for node in ["H1", "H2"]:
            print(f"\n   {node} eth0:")
            exit_code, output = controller.exec_in_node(
                node,
                "tc qdisc show dev eth0"
            )
            if exit_code == 0:
                print(f"     {output.decode().strip()}")
        
        # 测试延迟
        print("\n5. 测试延迟:")
        if h2_ip:
            print(f"   H1 -> H2 ({h2_ip}):")
            exit_code, output = controller.exec_in_node(
                "H1",
                f"ping -c 5 -W 3 {h2_ip}"
            )
            if exit_code == 0:
                lines = output.decode().split('\n')
                for line in lines:
                    if 'rtt' in line:
                        print(f"     {line.strip()}")
                        # 应该看到 RTT > 200ms (往返 = 100ms * 2)
                print("     预期: RTT 约 200ms（往返延迟）")
            else:
                print("     ✗ ping 失败")
        
        # 测试丢包
        print("\n6. 测试丢包率:")
        if h2_ip:
            print(f"   发送 20 个包...")
            exit_code, output = controller.exec_in_node(
                "H1",
                f"ping -c 20 -W 3 {h2_ip}"
            )
            lines = output.decode().split('\n')
            for line in lines:
                if 'packets' in line:
                    print(f"     {line.strip()}")
                    # 应该看到约 5% 丢包
            print("     预期: 约 5% 丢包率")
        
        # 测试带宽
        print("\n7. 测试带宽限制:")
        print("   (需要 iperf3 工具，镜像中可能未包含)")
        print("   跳过带宽测试")
        
        print("\n8. 拓扑运行中...")
        print("   - 使用 'docker exec -it H1 sh' 进入容器")
        print("   - 手动测试: ping, traceroute, etc.")
        print("   - 按 Ctrl+C 停止并清理")
        
        # 保持运行
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n用户中断，开始清理...")
    
    print("✓ 清理完成")
    print("\n" + "=" * 60)
    print("示例结束")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

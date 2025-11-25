#!/usr/bin/env python3
r"""
CLI 集成示例

演示如何在部署后自动进入 CLI 进行交互式操作。
展示 auto_cleanup=False 的用法，允许部署保持运行。

运行方式:
    sudo -E .venv/bin/python "examples/6. cli_integration/cli_demo.py"
    sudo -E .venv/bin/python "examples/6. cli_integration/cli_demo.py" --no-cli  # 不进入 CLI
    sudo -E .venv/bin/python "examples/6. cli_integration/cli_demo.py" --cleanup # 仅清理
"""

import sys
import argparse
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from vortinet import Topology, create_host_node, create_ovs_switch
from vortinet.deployment import DeploymentController
from vortinet.utils import cleanup_all
from vortinet_cli import VortinetCLI


def create_topology():
    """创建一个简单的 4 主机拓扑"""
    topo = Topology(name="cli_demo")
    
    # 添加 4 个主机
    hosts = []
    for i in range(1, 5):
        host = create_host_node(f"H{i}")
        hosts.append(host)
        topo.add_node_object(host)
    
    # 添加交换机
    sw1 = create_ovs_switch(
        name="SW1",
        controller=None,
        openflow_version="OpenFlow13"
    )
    topo.add_node_object(sw1)
    
    # 连接主机到交换机
    for i in range(1, 5):
        topo.add_link(f"H{i}", "SW1")
    
    return topo


def main():
    parser = argparse.ArgumentParser(description='CLI 集成示例')
    parser.add_argument('--no-cli', action='store_true', help='不进入 CLI')
    parser.add_argument('--cleanup', action='store_true', help='仅清理资源')
    
    args = parser.parse_args()
    
    # 仅清理
    if args.cleanup:
        print("清理所有 Vortinet 资源...")
        cleanup_all(verbose=False)
        return
    
    print("=" * 60)
    print("CLI 集成示例")
    print("=" * 60)
    print()
    print("此示例展示:")
    print("  1. 使用 auto_cleanup=False 保持部署运行")
    print("  2. 部署完成后自动进入 CLI")
    print("  3. 在 CLI 中交互式操作网络")
    print()
    
    # 创建拓扑
    topo = create_topology()
    
    # 部署 - 注意 auto_cleanup=False
    print("部署拓扑...")
    with DeploymentController("cli_demo", verbose=True, auto_cleanup=False) as controller:
        controller.deploy(topo)
        
        print()
        print("=" * 60)
        print("部署完成! 网络拓扑:")
        print("=" * 60)
        print()
        print("  H1 (10.10.0.2)")
        print("   |")
        print("  SW1 (OVS Bridge)")
        print("   |\\")
        print("   | \\")
        print("  H2  H3 (10.10.0.3, 10.10.0.4)")
        print("   |")
        print("  H4 (10.10.0.5)")
        print()
        print("会话 ID:", controller.resource_tracker.session_id)
        print()
        
        if not args.no_cli:
            print("=" * 60)
            print("进入 CLI 模式")
            print("=" * 60)
            print()
            print("提示:")
            print("  - 输入 'help' 查看可用命令")
            print("  - 输入 'shell H1' 进入 H1 终端")
            print("  - 输入 'ping H1 10.10.0.5' 测试连通性")
            print("  - 输入 'quit' 退出 (资源将保留)")
            print()
            
            # 创建 CLI 并绑定到当前 controller
            cli = VortinetCLI(controller)
            cli.interactive_mode()
            
            print()
            print("=" * 60)
            print("退出 CLI")
            print("=" * 60)
            print()
            print("网络拓扑仍在运行!")
            print(f"会话 ID: {controller.resource_tracker.session_id}")
            print()
            print("你可以:")
            print(f"  1. 重新连接: sudo -E .venv/bin/python vortinet_cli.py")
            print("  2. 手动清理: sudo -E .venv/bin/python vortinet_cli.py cleanup")
            print("  3. 在脚本中清理: python examples/6.\\ cli_integration/cli_demo.py --cleanup")
            print()
        else:
            print("跳过 CLI (--no-cli)")
            print()
            print("部署已完成并保持运行 (auto_cleanup=False)")
            print(f"会话 ID: {controller.resource_tracker.session_id}")
            print()
            print("你可以:")
            print("  1. 进入 CLI: sudo -E .venv/bin/python vortinet_cli.py")
            print("  2. 清理资源: python examples/6.\\ cli_integration/cli_demo.py --cleanup")
            print()


if __name__ == '__main__':
    main()

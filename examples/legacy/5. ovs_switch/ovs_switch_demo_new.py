#!/usr/bin/env python3
"""
OVS 交换机示例（新架构）

演示如何使用 Open vSwitch 作为虚拟交换机连接多个主机。

拓扑结构：
    H1 ----\
    H2 ---- [OVS-SW1] ---- H4
    H3 ----/

功能展示：
1. 使用 OVS 交换机连接多个主机
2. 验证二层交换功能
3. 演示 VLAN 隔离（可选）

运行方式：
    sudo -E .venv/bin/python examples/5.\ ovs_switch/ovs_switch_demo_new.py

依赖：
    - Open vSwitch 必须已安装并运行
    - 需要 root 权限
"""

import sys
import time
import argparse
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from vortinet import Topology, create_host_node, create_ovs_switch
from vortinet.deployment import DeploymentController
from vortinet.utils import cleanup_all


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="OVS 交换机示例")
    parser.add_argument(
        "--no-cleanup", 
        action="store_true", 
        help="退出时不自动清理资源（用于调试或后续手动清理）"
    )
    parser.add_argument(
        "--no-block", 
        action="store_true", 
        help="部署完成后不阻塞，直接退出（配合 --no-cleanup 使用）"
    )
    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()
    auto_cleanup = not args.no_cleanup
    
    print("=" * 60)
    print("OVS 交换机示例（新架构）")
    print(f"自动清理: {auto_cleanup}")
    print(f"阻塞运行: {not args.no_block}")
    print("=" * 60)
    
    # 运行前自动清理（使用清理插件）
    print("\n检查并清理残留资源...", end="", flush=True)
    stats = cleanup_all(verbose=False)
    if stats['containers'] > 0 or stats['ovs_bridges'] > 0:
        print(f" 完成 (容器={stats['containers']}, OVS={stats['ovs_bridges']})")
    else:
        print(" 无需清理")
    
    # 第一步：创建拓扑
    print("\n第一步：创建拓扑")
    print("  拓扑: H1, H2, H3, H4 通过 OVS 交换机连接\n")
    
    topo = Topology(name="ovs_demo")
    
    # 创建 4 个主机节点
    h1 = create_host_node("H1")
    h2 = create_host_node("H2")
    h3 = create_host_node("H3")
    h4 = create_host_node("H4")
    
    # 创建 OVS 交换机节点
    sw1 = create_ovs_switch(
        "SW1",
        controller=None,  # 使用本地交换模式（无控制器）
        openflow_version="OpenFlow13"
    )
    
    # 添加所有节点到拓扑
    topo.add_node_object(h1)
    topo.add_node_object(h2)
    topo.add_node_object(h3)
    topo.add_node_object(h4)
    topo.add_node_object(sw1)
    
    # 连接主机到交换机（每个主机一条链路）
    # 新API更清晰：每个连接都是独立的，符合实际网络拓扑
    topo.add_link("H1", "SW1")
    topo.add_link("H2", "SW1")
    topo.add_link("H3", "SW1")
    topo.add_link("H4", "SW1")
    
    # 打印拓扑结构
    print("拓扑结构:")
    print(f"  节点数: {len(topo.nodes)}")
    print(f"  链路数: {len(topo.links)}")
    print("\n  节点:")
    for name, node in topo.nodes.items():
        print(f"    - {name} ({node.node_type})")
        for iface_name, iface in node.interfaces.items():
            if iface.has_ip:
                print(f"      {iface_name}: {iface.ip_address}/{iface.link.subnet.prefixlen}")
    
    print("\n  链路:")
    for name, link in topo.links.items():
        if link.is_switched:
            endpoints = [iface.node.name for iface in link.interfaces if iface.node != link.switch]
            switch_name = link.switch.name
            print(f"    - {name}: {', '.join(endpoints)} <-> [{switch_name}] (交换链路)")
        else:
            nodes = [iface.node.name for iface in link.interfaces]
            print(f"    - {name}: {' <-> '.join(nodes)} ({link.subnet})")
    
    # 第二步：部署和运行
    print("\n第二步：部署和运行")
    if not args.no_block:
        print("  按 Ctrl+C 可以停止仿真\n")
    
    try:
        # 使用上下文管理器，自动清理
        with DeploymentController("ovs_demo", auto_cleanup=auto_cleanup) as controller:
            controller.deploy(topo)
            
            print("\n✓ 部署成功!")
            print(f"  会话 ID: {controller.resource_tracker.session_id[:16]}...\n")
            
            # 显示运行中的容器
            containers = [name for name, node in topo.nodes.items() 
                         if not node.is_switch]
            print(f"运行中的容器 ({len(containers)}):")
            for name in containers:
                print(f"  - {name}")
            
            # 检查 OVS 网桥
            print("\nOVS 网桥信息:")
            try:
                import subprocess
                result = subprocess.run(
                    ["ovs-vsctl", "show"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    # 只显示我们创建的网桥
                    for line in result.stdout.split('\n'):
                        if 'ovs-SW1' in line or 'Bridge' in line or 'Port' in line:
                            print(f"  {line}")
                else:
                    print("  (无法获取 OVS 信息)")
            except Exception as e:
                print(f"  (OVS 命令失败: {e})")
            
            # 验证网络连通性
            print("\n验证网络连通性（二层交换）:")
            
            # 获取各主机的 IP
            h1_ip = str(topo.nodes["H1"].interfaces["eth0"].ip_address)
            h2_ip = str(topo.nodes["H2"].interfaces["eth0"].ip_address)
            h3_ip = str(topo.nodes["H3"].interfaces["eth0"].ip_address)
            h4_ip = str(topo.nodes["H4"].interfaces["eth0"].ip_address)
            
            # H1 -> H2
            print(f"  H1 -> H2 ({h2_ip})")
            exit_code, _ = controller.exec_in_node("H1", f"ping -c 2 -W 1 {h2_ip}")
            print("    ✓ 连通成功" if exit_code == 0 else "    ✗ 连通失败")
            
            # H3 -> H4
            print(f"  H3 -> H4 ({h4_ip})")
            exit_code, _ = controller.exec_in_node("H3", f"ping -c 2 -W 1 {h4_ip}")
            print("    ✓ 连通成功" if exit_code == 0 else "    ✗ 连通失败")
            
            # H1 -> H4 (跨所有主机)
            print(f"  H1 -> H4 ({h4_ip})")
            exit_code, _ = controller.exec_in_node("H1", f"ping -c 2 -W 1 {h4_ip}")
            print("    ✓ 连通成功" if exit_code == 0 else "    ✗ 连通失败")
            
            print("\n拓扑运行中...")
            print("  提示:")
            print("    - 使用 'docker exec -it <容器名> sh' 进入容器")
            print("    - 使用 'ovs-vsctl show' 查看 OVS 网桥")
            print("    - 使用 'ovs-ofctl dump-flows ovs-SW1' 查看流表")
            print("    - 使用 './vortinet_cleanup.py list' 查看会话")
            if not args.no_block:
                print("    - 按 Ctrl+C 停止并自动清理")
            
            # 保持运行
            if not args.no_block:
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    print("\n\n用户中断")
            else:
                print("\n非阻塞模式：脚本退出，资源保留。")
                print(f"请手动清理会话: {controller.resource_tracker.session_id}")
    
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if auto_cleanup:
            print("正在清理资源...")
        else:
            print("跳过自动清理（--no-cleanup）")
    
    if auto_cleanup:
        print("✓ 清理完成\n")
    print("=" * 60)
    print("仿真结束")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
基础拓扑示例 - 新架构版本

功能等同于原 basic_topo.py：
- R1: 路由器节点（启用IP转发）
- H1, H2: 主机节点
- 自动IP分配
- 设置默认网关
- 显示拓扑信息

新架构特点：
1. 使用强类型配置（NodeConfig）
2. 使用 DeploymentController 部署
3. 自动清理（崩溃安全）
4. 保持与旧 API 相似的使用方式
"""

import sys
import argparse
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from vortinet.models.topology import Topology
from vortinet.nodes import create_host_node, create_router_node
from vortinet.deployment import DeploymentController
from vortinet.utils import cleanup_all


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="基础拓扑示例")
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
    """主函数，演示如何使用新架构运行仿真"""
    args = parse_args()
    auto_cleanup = not args.no_cleanup
    
    print("=" * 60)
    print("基础拓扑示例（新架构）")
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
    
    # 1. 创建拓扑
    # 这个部分是用户唯一需要关心的：定义网络的结构
    print("\n第一步：创建拓扑")
    topo = Topology()
    
    # 添加节点（使用工厂函数，等价于旧 API 的 add_node）
    r1 = create_router_node("R1", enable_ip_forward=True)
    h1 = create_host_node("H1")
    h2 = create_host_node("H2")
    
    topo.add_node_object(r1)
    topo.add_node_object(h1)
    topo.add_node_object(h2)
    
    # 添加链路（自动分配IP）
    link1 = topo.add_link("H1", "R1")
    link2 = topo.add_link("H2", "R1")
    
    # 设置默认网关（通过设置路由）
    topo.set_default_gateway("H1", "R1")
    topo.set_default_gateway("H2", "R1")
    
    # 打印拓扑结构（等价于旧 API 的 display）
    print("\n拓扑结构:")
    print(f"  节点数: {len(topo.nodes)}")
    print(f"  链路数: {len(topo.links)}")
    print("\n  节点:")
    for name, node in topo.nodes.items():
        print(f"    - {name} ({node.node_type})")
        for iface_name, iface in node.interfaces.items():
            if iface.has_ip:
                print(f"      {iface_name}: {iface.ip_address}/{iface.link.subnet.prefixlen}")
    
    print("\n  链路:")
    for link_name, link in topo.links.items():
        nodes = [iface.node.name for iface in link.interfaces]
        print(f"    - {link_name}: {' <-> '.join(nodes)} ({link.subnet})")
    
    # 2. 创建并运行仿真
    # 所有繁琐的流程（日志、清理、启动、停止）都由 DeploymentController 处理
    print("\n第二步：部署和运行")
    if not args.no_block:
        print("  按 Ctrl+C 可以停止仿真")
    
    try:
        # 使用上下文管理器，自动清理（等价于旧 API 的 SimulationRunner）
        with DeploymentController("basic_topo", auto_cleanup=auto_cleanup) as controller:
            # 部署拓扑
            controller.deploy(topo, default_image="vortinet_base:latest")
            
            print("\n✓ 部署成功!")
            print(f"  会话 ID: {controller.resource_tracker.session_id[:16]}...")
            
            # 显示运行中的容器
            info = controller.get_session_info()
            containers = info.get('containers', [])
            print(f"\n运行中的容器 ({len(containers)}):")
            for c in containers:
                print(f"  - {c['name']}")
            
            # 验证网络连通性
            print("\n验证网络连通性:")
            
            # 获取 R1 的IP（从 H1 的角度）
            h1_iface = topo.nodes["H1"].interfaces.get("eth0")
            if h1_iface and h1_iface.link:
                # 找到同一链路上 R1 的接口
                r1_ip = None
                for iface in h1_iface.link.interfaces:
                    if iface.node.name == "R1" and iface.has_ip:
                        r1_ip = str(iface.ip_address)
                        break
                
                if r1_ip:
                    print(f"  H1 -> R1 ({r1_ip})")
                    exit_code, output = controller.exec_in_node(
                        "H1",
                        f"ping -c 3 -W 2 {r1_ip}"
                    )
                    if exit_code == 0:
                        print(f"    ✓ 连通成功")
                    else:
                        print(f"    ✗ 连通失败")
            
            # 获取 R1 的另一个接口IP（从 H2 的角度）
            h2_iface = topo.nodes["H2"].interfaces.get("eth0")
            if h2_iface and h2_iface.link:
                r1_ip = None
                for iface in h2_iface.link.interfaces:
                    if iface.node.name == "R1" and iface.has_ip:
                        r1_ip = str(iface.ip_address)
                        break
                
                if r1_ip:
                    print(f"  H2 -> R1 ({r1_ip})")
                    exit_code, output = controller.exec_in_node(
                        "H2",
                        f"ping -c 3 -W 2 {r1_ip}"
                    )
                    if exit_code == 0:
                        print(f"    ✓ 连通成功")
                    else:
                        print(f"    ✗ 连通失败")
            
            # 测试跨子网连通性（H1 -> H2 通过 R1）
            h2_ip = None
            h2_iface = topo.nodes["H2"].interfaces.get("eth0")
            if h2_iface and h2_iface.has_ip:
                h2_ip = str(h2_iface.ip_address)
            
            if h2_ip:
                print(f"  H1 -> H2 ({h2_ip}) [通过R1路由]")
                exit_code, output = controller.exec_in_node(
                    "H1",
                    f"ping -c 3 -W 2 {h2_ip}"
                )
                if exit_code == 0:
                    print(f"    ✓ 路由成功")
                else:
                    print(f"    ✗ 路由失败（R1 需要启用IP转发）")
            
            print("\n拓扑运行中...")
            print("  提示:")
            print("    - 使用 'docker exec -it <容器名> sh' 进入容器")
            print("    - 使用 './vortinet_cleanup.py list' 查看会话")
            if not args.no_block:
                print("    - 按 Ctrl+C 停止并自动清理")
            
            # 保持运行（等价于旧 API 的 auto_cleanup_after=0）
            if not args.no_block:
                import time
                while True:
                    time.sleep(1)
            else:
                print("\n非阻塞模式：脚本退出，资源保留。")
                print(f"请手动清理会话: {controller.resource_tracker.session_id}")
                
    except KeyboardInterrupt:
        print("\n\n用户中断")
    
    # 退出上下文管理器后自动清理
    if auto_cleanup:
        print("正在清理资源...")
        print("✓ 清理完成")
    else:
        print("跳过自动清理（--no-cleanup）")
    
    print("\n" + "=" * 60)
    print("仿真结束")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

#!/usr/bin/env python3
"""
示例 10: Ryu 控制器集成
============================================================
本示例演示如何将 Ryu 控制器作为容器运行，并控制 OVS 交换机。

拓扑结构:
    h1 [10.0.0.1] <----> sw1 (OVS) <----> h2 [10.0.0.2]
                           ^
                           |
                      c0 (Ryu) [10.0.0.3]

关键概念:
1. 构建并运行 Ryu 容器
2. 配置 OVS 使用带内控制 (In-Band Control) 连接到 Ryu
3. 在宿主机网桥上配置 IP 以便 OVS 能够连接到容器内的控制器
"""

import sys
import time
import logging
import subprocess
from pathlib import Path
from ipaddress import IPv4Network

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from vortinet import Topology, Node, create_host_node, create_ovs_switch
from vortinet.config import NodeConfig, ContainerConfig, BuildConfig
from vortinet.deployment import DeploymentController

def create_ryu_node(name: str, app_script: str, volumes: list) -> Node:
    """创建 Ryu 控制器节点"""
    dockerfile_path = project_root / "dockerfile" / "vortinet_ryu"
    
    config = NodeConfig(
        node_type="ryu_controller",
        backend=ContainerConfig(
            image="vortinet_ryu:latest",
            # 启动 ryu-manager 并加载应用
            command=f"ryu-manager --verbose {app_script}",
            volumes=volumes,
            build=BuildConfig(
                context_path=dockerfile_path,
                dockerfile="Dockerfile"
            ) if dockerfile_path.exists() else None,
            # 暴露端口 (仅用于文档，实际通信通过 veth)
            environment={"PYTHONUNBUFFERED": "1"}
        )
    )
    return Node(name, config)

def main():
    print("="*60)
    print("示例 10: Ryu 控制器集成")
    print("="*60)

    # 1. 定义拓扑
    topo = Topology("ryu_demo")
    
    # 获取当前目录路径
    current_dir = Path(__file__).parent.absolute()
    
    # 创建节点
    h1 = create_host_node("h1")
    h2 = create_host_node("h2")
    
    # 创建 Ryu 节点
    # 挂载当前目录到 /app，以便访问 simple_switch_13.py
    c0 = create_ryu_node(
        "c0", 
        app_script="/app/simple_switch_13.py",
        volumes=[f"{current_dir}:/app"]
    )
    
    # 创建 OVS 交换机
    # 指定控制器为 Ryu 容器的 IP (10.0.0.3)
    # 注意：此时 IP 尚未分配，但 OVS 会不断重试连接
    sw1 = create_ovs_switch(
        "sw1", 
        controller="tcp:10.0.0.3:6653",
        openflow_version="OpenFlow13"
    )
    
    topo.add_nodes(h1, h2, c0, sw1)
    
    # 连接节点
    subnet = IPv4Network("10.0.0.0/24")
    topo.reserve_ip(h1, "10.0.0.1", subnet)
    topo.reserve_ip(h2, "10.0.0.2", subnet)
    topo.reserve_ip(c0, "10.0.0.3", subnet)
    
    # h1 <-> sw1
    topo.add_link(h1, sw1, subnet=subnet)
    # h2 <-> sw1
    topo.add_link(h2, sw1, subnet=subnet)
    # c0 <-> sw1 (控制器连接到交换机，实现带内控制)
    topo.add_link(c0, sw1, subnet=subnet)
    
    # 2. 部署
    with DeploymentController(topo.name, log_level=logging.INFO) as controller:
        print("Deploying topology...")
        controller.deploy(topo, visualize=True)
        
        # 关键步骤：为宿主机上的 OVS 网桥分配 IP
        # 这样宿主机上的 OVS 进程才能通过 TCP 连接到容器内的 Ryu (10.0.0.3)
        bridge_name = controller.get_ovs_bridge_name("sw1")
        host_ip = "10.0.0.254/24"
        print(f"\nConfiguring host bridge {bridge_name} with IP {host_ip}...")
        subprocess.run(["sudo", "ip", "addr", "add", host_ip, "dev", bridge_name], check=False)
        
        print("Waiting for Ryu to start and OVS to connect (10s)...")
        time.sleep(10)
        
        # 检查 OVS 连接状态
        print("\nChecking OVS controller status...")
        status = controller.run_ovs_ofctl("sw1", ["show"])
        print(status)
        
        print("\n[Step 1] 测试连通性 (Ryu SimpleSwitch 应自动下发流表)...")
        # 第一次 ping 可能会丢包（ARP + 流表学习），所以多试几次
        if controller.ping("h1", "h2", count=5):
            print("✓ Ping Passed")
        else:
            print("✗ Ping Failed")
            
        print("\n[Step 2] 查看流表...")
        flows = controller.run_ovs_ofctl("sw1", ["dump-flows"])
        print(f"Current flows:\n{flows.strip()}")
        
        input("\n按 Enter 键清理资源并退出...")

if __name__ == "__main__":
    main()

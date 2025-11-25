#!/usr/bin/env python3
"""
示例 08: 自定义服务与文件挂载
============================================================
本示例演示如何将自定义脚本挂载到节点中并作为服务运行。

拓扑结构:
    Server [10.0.0.1] <-----> Client [10.0.0.2]

关键概念:
1. 使用 volumes 参数挂载本地目录到容器
2. 使用 command 参数覆盖容器启动命令
3. 在节点中运行自定义 Python 服务
"""

import sys
import logging
from pathlib import Path
from ipaddress import IPv4Network

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from vortinet import Topology, create_host_node
from vortinet.deployment import DeploymentController

def main():
    print("="*60)
    print("示例 08: 自定义服务与文件挂载")
    print("="*60)

    # 1. 定义拓扑
    topo = Topology("custom_service_demo")
    
    # 获取当前目录路径，用于挂载
    current_dir = Path(__file__).parent.absolute()
    
    # 2. 添加服务器节点
    # 挂载当前目录到 /app，并启动 server.py
    # 注意：使用 nohup 在后台启动服务，或者直接作为主进程运行
    # 这里我们让它作为主进程运行，因为 create_host_node 默认是 tail -f /dev/null
    # 我们覆盖 command 来运行服务
    server = create_host_node(
        "server",
        command="python3 /app/server.py",
        volumes=[f"{current_dir}:/app"]
    )
    topo.add_node(server)
    
    # 3. 添加客户端节点
    # 同样挂载目录，但保持默认 command (tail -f /dev/null)，以便我们手动执行脚本
    client = create_host_node(
        "client",
        volumes=[f"{current_dir}:/app"]
    )
    topo.add_node(client)
    
    # 4. 连接节点
    # 预留 IP 并连接
    subnet = IPv4Network("10.0.0.0/24")
    
    topo.reserve_ip(server, "10.0.0.1", subnet)
    topo.reserve_ip(client, "10.0.0.2", subnet)
    
    topo.add_link(server, client, subnet=subnet)
    
    # 5. 部署
    # 使用 with 语句确保资源在使用后自动清理
    with DeploymentController(topo.name) as controller:
        print("Deploying topology...")
        controller.deploy(topo, visualize=True)
        
        print("\nRunning client script...")
        # 在客户端节点执行脚本
        exit_code, output = controller.exec_in_node("client", "python3 /app/client.py")
        print(f"Client Output:\n{output.decode()}")
        
        if exit_code == 0:
            print("\n✓ Test Passed!")
        else:
            print("\n✗ Test Failed!")
            
        input("\n按 Enter 键清理资源并退出...")

if __name__ == "__main__":
    main()

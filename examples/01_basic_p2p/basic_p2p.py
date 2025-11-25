#!/usr/bin/env python3
"""
示例 01: 基础点对点连接

这是最简单的拓扑结构，展示了两个主机通过虚拟网线（veth pair）直接连接。

拓扑结构:
    H1 <-----> H2
    (10.10.0.1)  (10.10.0.2)

关键概念:
1. 创建主机节点 (create_host_node)
2. 添加节点到拓扑 (topo.add_nodes)
3. 创建链路 (topo.add_link)
4. 部署和验证 (DeploymentController)
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from vortinet import Topology, create_host_node
from vortinet.deployment import DeploymentController

def main():
    print("="*60)
    print("示例 01: 基础点对点连接")
    print("="*60)

    # 1. 创建拓扑对象
    topo = Topology("basic_p2p")

    # 2. 创建节点
    # 使用工厂函数创建标准主机节点
    h1 = create_host_node("H1")
    h2 = create_host_node("H2")

    # 3. 添加节点到拓扑
    topo.add_nodes(h1, h2)

    # 4. 创建链路
    # 直接连接 H1 和 H2，系统会自动分配一个 /24 子网
    # 支持直接传入节点对象
    topo.add_link(h1, h2)

    # 5. 部署拓扑
    # 使用 with 语句确保资源在使用后自动清理
    with DeploymentController("p2p_demo") as controller:
        # 部署并保存拓扑图
        controller.deploy(topo)
        
        print("\n[验证连通性]")
        if controller.ping("H1", "H2"):
            print("✓ 测试通过")
        else:
            print("✗ 测试失败")
        
        input("\n按 Enter 键清理资源并退出...")

if __name__ == "__main__":
    main()

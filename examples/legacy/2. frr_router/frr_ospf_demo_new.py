#!/usr/bin/env python3
"""
FRR OSPF 路由示例 - 新架构版本

展示如何使用新架构创建 OSPF 动态路由拓扑：
- R1, R2, R3: FRR 路由器（环形拓扑）
- H1, H2: 主机节点
- OSPF 自动路由发现

新架构特点：
1. 使用 FRR 专用工厂函数
2. 自动配置生成和挂载
3. 支持 OSPF 动态路由
"""

import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from vortinet.models.topology import Topology
from vortinet.nodes import create_host_node, create_frr_node
from vortinet.deployment import DeploymentController


def main():
    print("=" * 60)
    print("FRR OSPF 路由示例（新架构）")
    print("=" * 60)
    
    # 1. 创建拓扑
    print("\n1. 创建拓扑...")
    topo = Topology()
    
    # 创建 FRR 路由器节点
    r1 = create_frr_node("R1", routing_protocols=["ospf"])
    r2 = create_frr_node("R2", routing_protocols=["ospf"])
    r3 = create_frr_node("R3", routing_protocols=["ospf"])
    
    # 创建主机节点
    h1 = create_host_node("H1")
    h2 = create_host_node("H2")
    
    # 添加所有节点
    for node in [r1, r2, r3, h1, h2]:
        topo.add_node_object(node)
    
    # 创建环形链路
    topo.add_link("R1", "R2")
    topo.add_link("R2", "R3")
    topo.add_link("R3", "R1")
    
    # 主机连接到路由器
    topo.add_link("H1", "R1")
    topo.add_link("H2", "R2")
    
    print(f"   节点数: {len(topo.nodes)} (3 路由器 + 2 主机)")
    print(f"   链路数: {len(topo.links)}")
    print("   拓扑:")
    print("     H1 --- R1 --- R2 --- H2")
    print("              \\   /")
    print("               R3")
    
    # 2. 部署拓扑
    print("\n2. 部署拓扑...")
    print("   注意: FRR 需要 vortinet_frr 镜像")
    
    with DeploymentController("frr_ospf_demo") as controller:
        # 使用 FRR 镜像部署
        controller.deploy(topo, default_image="vortinet_frr:latest")
        
        session_id = controller.resource_tracker.session_id
        print(f"\n✓ 部署成功!")
        print(f"  会话 ID: {session_id[:16]}...")
        
        # 获取容器信息
        info = controller.get_session_info()
        containers = info.get('containers', [])
        print(f"  运行容器: {len(containers)}")
        
        # 等待 OSPF 收敛
        print("\n3. 等待 OSPF 协议收敛...")
        import time
        for i in range(10, 0, -1):
            print(f"   {i} 秒...", end="\r")
            time.sleep(1)
        print("   ✓ OSPF 应已收敛           ")
        
        # 显示路由表
        print("\n4. 查看路由表:")
        for router in ["R1", "R2", "R3"]:
            print(f"\n   {router}:")
            exit_code, output = controller.exec_in_node(
                router,
                "vtysh -c 'show ip route'"
            )
            if exit_code == 0:
                lines = output.decode().split('\n')
                # 只显示前10行
                for line in lines[:10]:
                    if line.strip():
                        print(f"     {line}")
            else:
                print("     ✗ 无法获取路由表")
        
        # 显示 OSPF 邻居
        print("\n5. 查看 OSPF 邻居:")
        for router in ["R1", "R2", "R3"]:
            print(f"\n   {router}:")
            exit_code, output = controller.exec_in_node(
                router,
                "vtysh -c 'show ip ospf neighbor'"
            )
            if exit_code == 0:
                lines = output.decode().split('\n')
                for line in lines[:8]:
                    if line.strip():
                        print(f"     {line}")
        
        # 测试连通性
        print("\n6. 测试连通性:")
        print("   H1 -> H2 (通过 OSPF 路由):")
        
        exit_code, _ = controller.exec_in_node("H2", "hostname -I")
        h2_ip = _.decode().strip().split()[0] if _ else ""
        
        if h2_ip:
            exit_code, output = controller.exec_in_node(
                "H1",
                f"ping -c 3 -W 2 {h2_ip}"
            )
            if exit_code == 0:
                print(f"     ✓ H1 -> H2 ({h2_ip}): 成功")
                # 显示 RTT
                lines = output.decode().split('\n')
                for line in lines:
                    if 'rtt' in line or 'packets' in line:
                        print(f"       {line.strip()}")
            else:
                print(f"     ✗ ping 失败")
                print("     提示: OSPF 可能需要更长时间收敛")
        
        print("\n7. 拓扑运行中...")
        print("   - 使用 'docker exec -it R1 vtysh' 进入 FRR CLI")
        print("   - 按 Ctrl+C 停止并清理")
        
        # 保持运行
        try:
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

import sys
from pathlib import Path

# 将项目根目录添加到Python的模块搜索路径中
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from core.topology import Topology
from core.simulation_runner import SimulationRunner
from core.node_types import FrrOspfNode


def main():
    """主函数，演示如何运行一个包含FRR OSPF节点的仿真。"""

    # 1. 创建拓扑
    topo = Topology()

    # 创建三个FRR OSPF路由器节点
    # 注意：我们现在使用的是 FrrOspfNode，而不是通用的 Node
    # 将节点添加到拓扑中
    topo.add_node(FrrOspfNode(name="R1"))
    topo.add_node(FrrOspfNode(name="R2"))
    topo.add_node(FrrOspfNode(name="R3"))
    topo.add_node('H1', node_type='client')
    topo.add_node('H2', node_type='client')

    # 创建一个环形链路
    topo.add_link("R1", "R2")
    topo.add_link("R2", "R3")
    topo.add_link("R3", "R1")
    topo.add_link("H1", "R1")
    topo.add_link("H2", "R2")

    # 为客户端节点设置默认网关
    topo.set_default_gateway("H1", "R1")
    topo.set_default_gateway("H2", "R2")

    # 打印拓扑结构以供验证
    topo.display()

    # 2. 创建并运行仿真
    # SimulationRunner 会自动处理配置生成、挂载和启动后命令的执行
    runner = SimulationRunner()

    # 运行仿真，启动后不自动清理，直到手动按 Ctrl+C
    runner.run(topo, auto_cleanup_after=0)


if __name__ == "__main__":
    main()

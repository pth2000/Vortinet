import sys
from pathlib import Path

# 将项目根目录添加到Python的模块搜索路径中
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from core.topology import Topology
from core.simulation_runner import SimulationRunner

def main():
    """主函数，演示如何使用新的 SimulationRunner 运行仿真。"""

    # 1. 创建拓扑
    # 这个部分是用户唯一需要关心的：定义网络的结构。
    topo = Topology()

    # 添加节点，可以指定属性，如Docker镜像，未指定则使用默认值。
    topo.add_node("R1", node_type="router")
    topo.add_node("H1", node_type="client", command="sleep 3600")
    topo.add_node("H2", node_type="client", command="sleep 3600")

    # 添加链路
    topo.add_link("H1", "R1")
    topo.add_link("H2", "R1")

    # 打印拓扑结构
    topo.display()

    # 2. 创建并运行仿真
    # 所有繁琐的流程（日志、清理、启动、停止）都由 SimulationRunner 处理。
    runner = SimulationRunner()

    # run() 方法会处理所有事情。
    # auto_cleanup_after=60 表示仿真启动60秒后会自动停止并清理。
    # 如果设置为 0，它会一直运行，直到您按下 Ctrl+C。
    runner.run(topo, auto_cleanup_after=0)


if __name__ == "__main__":
    main()

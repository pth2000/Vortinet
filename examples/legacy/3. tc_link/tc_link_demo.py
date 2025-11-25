import sys
from pathlib import Path

# 将项目根目录添加到Python的模块搜索路径中
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from core.topology import Topology
from core.simulation_runner import SimulationRunner


def main():
    """
    演示如何使用TC（Traffic Control）来模拟网络链路质量。
    """

    # 1. 创建拓扑
    topo = Topology()

    # 添加两个主机
    topo.add_node("H1")
    topo.add_node("H2")

    # 添加一条链路，并指定网络质量参数
    # - delay: 延迟 100ms
    # - loss: 丢包率 5%
    # - bandwidth: 带宽 1024 kbit/s (1 mbit/s)
    topo.add_link("H1", "H2", delay="100ms", loss=5, bandwidth=1024)

    # 打印拓扑结构
    topo.display()

    # 2. 创建并运行仿真
    # SimulationRunner 会自动读取链路参数并应用TC规则
    runner = SimulationRunner()
    runner.run(topo, auto_cleanup_after=0)


if __name__ == "__main__":
    main()

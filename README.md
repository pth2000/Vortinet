<div align="center">
<!-- Title: -->
  <h1>Vortinet</h1>
</div>


Vortinet 是一个基于 Python 和 Docker 的轻量级网络仿真平台。它允许用户通过简单的 Python API 来定义复杂的网络拓扑，并将其在 Docker 容器中具现化，从而实现高度隔离和可复现的网络实验环境。

> [!IMPORTANT]  
> 该项目还在积极开发中。

## ✨ 核心功能

- **声明式拓扑定义**: 使用直观的 Python API 来添加节点（如路由器、主机）和链路，构建您的网络。
- **基于 Docker**: 每个网络节点都运行在独立的 Docker 容器中，确保了环境的纯净和隔离。
- **自动化管理**:
    - **镜像构建**: 自动检测并构建所需的 Docker 镜像（如 `vortinet_base`, `vortinet_frr`）。
    - **网络配置**: 自动为链路创建 Docker 网络，并为节点接口分配 IP 地址。
    - **生命周期管理**: `SimulationRunner` 类一键处理仿真的启动、资源配置、监控和清理。
- **高度可扩展**:
    - **自定义节点**: 方便地扩展支持新的节点类型（例如，交换机、特定应用服务器）。
    - **配置文件挂载**: 支持将本地配置文件（如 FRR 的 `daemons`, `vtysh.conf`）动态挂载到容器中。
- **开箱即用的示例**: 提供多个示例（如基础拓扑、FRR OSPF 动态路由）帮助您快速上手。

## 📂 项目结构

```
.
├── core/                 # 仿真核心逻辑
│   ├── topology.py         # 拓扑定义（Topology类）
│   ├── docker_controller.py  # Docker交互与控制
│   ├── simulation_runner.py  # 仿真运行器
│   └── ...
├── dockerfile/           # 项目使用的Dockerfile
│   ├── vortinet_base/      # 基础镜像，提供基本网络工具
│   └── vortinet_frr/       # FRR镜像，用于路由实验
├── examples/             # 示例代码
│   ├── 1. basic_topo/      # 基础拓扑示例
│   └── 2. frr_router/      # FRR OSPF路由示例
├── README.md             # 本文档
└── ...
```

## 🚀 快速开始

### 1. 环境准备

- Python 3.10+
- Docker Desktop 或 Docker Engine

### 2. 定义并运行一个简单的网络

以下示例将创建一个包含一个路由器（R1）和两个主机（H1, H2）的网络，并将主机连接到路由器。

1.  **创建示例文件**

    在 `examples/1. basic_topo/basic_topo.py` 中，代码如下：

    ```python
    from core.topology import Topology
    from core.simulation_runner import SimulationRunner

    def main():
        """主函数，演示如何使用 SimulationRunner 运行仿真。"""

        # 1. 创建拓扑
        topo = Topology()

        # 添加节点，可以指定节点类型
        topo.add_node("R1", node_type="router")
        topo.add_node("H1", node_type="client")
        topo.add_node("H2", node_type="client")

        # 添加链路，连接节点
        topo.add_link("H1", "R1")
        topo.add_link("H2", "R1")

        # 打印拓扑结构到控制台
        topo.display()

        # 2. 创建并运行仿真
        # SimulationRunner 会处理所有繁琐的流程
        runner = SimulationRunner(topo)
        runner.run()

    if __name__ == "__main__":
        main()
    ```

2.  **运行仿真**

    在项目根目录打开终端，执行：

    ```bash
    python examples/1. basic_topo/basic_topo.py
    ```

    程序将会：
    - 检查并构建缺失的 Docker 镜像 (`vortinet_base`)。
    - 根据拓扑创建名为 `vortinet_R1`, `vortinet_H1`, `vortinet_H2` 的容器。
    - 创建 Docker 网络来模拟 `H1-R1` 和 `H2-R1` 之间的链路。
    - 启动所有容器，仿真开始。
    - 按 `Ctrl+C` 即可自动停止并清理所有创建的容器和网络。

## 🔧 工作原理

Vortinet 的工作流程分为两个核心阶段：

1.  **定义阶段 (Topology)**:
    - 用户实例化一个 `Topology` 对象。
    - 通过 `add_node()` 和 `add_link()` 方法描述网络。`Topology` 对象会存储这些信息，并自动处理 IP 地址的规划。

2.  **运行阶段 (SimulationRunner & DockerController)**:
    - `SimulationRunner` 接收 `Topology` 对象。
    - `DockerController` 开始工作，它会读取拓扑信息并将其转化为具体的 Docker 操作：
        - **检查镜像**: 遍历拓扑中所有节点使用的镜像，如果本地不存在，则根据 `dockerfile/` 目录中的定义进行构建。
        - **创建网络**: 为每条链路创建一个 `bridge` 类型的 Docker 网络。
        - **创建容器**: 为每个节点创建一个容器，并根据链路信息将其连接到对应的 Docker 网络。
        - **启动容器**: 启动所有容器，网络仿真正式运行。
    - 当仿真结束时，`DockerController` 会负责停止并移除所有相关的容器和网络，保持系统干净。


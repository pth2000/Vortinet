<div align="center">
<!-- Title: -->
  <h1>Vortinet</h1>
</div>


Vortinet 是一个基于 Python 和 Docker 的轻量级、可扩展的网络仿真平台。它允许用户通过简单的 Python API 来定义复杂的网络拓扑，并将其在 Docker 容器中具现化，从而实现高度隔离和可复现的网络实验环境。

> [!IMPORTANT]  
> 该项目还在积极开发中。

## ✨ 核心功能

- **声明式拓扑定义**: 使用直观的 Python API 来添加节点（如路由器、主机、交换机）和链路，构建您的网络。
- **基于 Docker**: 每个网络节点都运行在独立的 Docker 容器中，确保了环境的纯净和隔离。
- **混合网络架构**:
    - **OVS 交换机**: 支持 OpenFlow、VLAN、控制器连接 (Standalone/Secure 模式)
    - **SDN 支持**: 集成 Ryu 控制器，支持手动流表下发
    - **点对点连接**: 直接 veth 对连接，零延迟
    - **流量控制**: 支持带宽限制、延迟、丢包等 TC 规则
- **崩溃安全清理**: 
    - **标签跟踪**: 所有资源使用持久化标签标识
    - **独立清理工具**: 即使程序崩溃也能准确清理资源
    - **会话隔离**: 多个部署互不影响，6 字符会话前缀防止命名冲突
- **交互式 CLI**:
    - **智能会话管理**: 自动检测和选择活动会话，支持多会话切换
    - **节点名称简写**: 直接使用节点名（如 H1）而非完整容器名
    - **批量操作**: 一次性打开多个节点终端
    - **命令历史与补全**: 支持方向键历史记录和 Tab 自动补全
    - **丰富信息展示**: 美观的拓扑结构、链路信息、节点状态显示
    - **常用操作**: shell 访问、ping 测试、查看状态、资源清理
    - **可选清理**: 支持持久化部署 (`auto_cleanup=False`)
- **自动化管理**:
    - **镜像构建**: 自动检测并构建所需的 Docker 镜像（如 `vortinet_base`, `vortinet_frr`）。
    - **网络配置**: 自动选择合适的网络后端（Direct veth / OVS Bridge）。
    - **生命周期管理**: `DeploymentController` 类统一管理容器和网络的创建、配置和清理。
- **高度可扩展**:
    - **自定义节点**: 方便地扩展支持新的节点类型（例如，Linux Bridge、特定应用服务器）。
    - **可插拔后端**: 网络后端架构支持轻松添加新的连接方式。
- **开箱即用的示例**: 提供多个示例（如基础拓扑、FRR OSPF 动态路由、混合网络、CLI 集成）帮助您快速上手。

## 📂 项目结构

```
.
├── vortinet/             # 新架构核心代码
│   ├── models/             # 数据模型（Topology, Node, Link）
│   ├── config/             # 配置（BackendConfig, OVSBridgeConfig）
│   ├── network/            # 网络后端（Direct veth, OVS Bridge）
│   ├── container/          # 容器管理（ContainerManager）
│   ├── deployment/         # 部署控制（DeploymentController）
│   └── utils/              # 工具（ResourceTracker）
├── core/                 # 旧架构（正在迁移）
│   ├── topology.py
│   ├── docker_controller.py
│   └── ...
├── dockerfile/           # Docker 镜像定义
│   ├── vortinet_base/      # 基础镜像
│   └── vortinet_frr/       # FRR 路由器镜像
├── examples/             # 示例代码
│   ├── README.md           # 示例总览
│   ├── 01_basic_p2p/       # 基础点对点
│   ├── 02_ovs_switch/      # OVS 交换机
│   ├── 03_traffic_control/ # 流量控制
│   ├── 04_router_gateway/  # 路由器与网关
│   ├── 05_complex_mixed/   # 混合复杂拓扑
│   ├── 06_frr_ospf/        # FRR OSPF 动态路由
│   ├── 07_frr_bgp/         # FRR BGP 动态路由
│   ├── 08_custom_service/  # 自定义服务
│   ├── 09_sdn_flow_table/  # SDN 手动流表
│   ├── 10_ryu_controller/  # Ryu 控制器集成
│   └── legacy/             # 旧版示例归档
├── vortinet_cli.py       # 交互式 CLI 工具
└── README.md             # 本文档
```

## 🚀 快速开始

### 1. 环境准备

- Python 3.10+
- Docker Desktop 或 Docker Engine
- Open vSwitch (可选，用于 OVS 交换机功能)

### 2. 安装依赖

进入项目根目录，创建 Python 虚拟环境：

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

### 3. 运行示例

#### 示例 1: 基础点对点 (Basic P2P)

```bash
sudo -E .venv/bin/python examples/01_basic_p2p/basic_p2p.py
```

#### 示例 2: OVS 交换机 (OVS Switch)

```bash
sudo -E .venv/bin/python examples/02_ovs_switch/ovs_switch.py
```

#### 示例 3: Ryu 控制器集成 (SDN)

```bash
sudo -E .venv/bin/python examples/10_ryu_controller/ryu_demo.py
```

这个示例将创建包含 Ryu 控制器容器和 OVS 交换机的 SDN 拓扑，演示：
- 容器化 SDN 控制器 (Ryu)
- OVS 带内控制 (In-Band Control)
- 自动流表下发

更多示例请参考 [examples/README.md](examples/README.md)。

### 4. 使用 CLI 工具

Vortinet CLI 提供了友好的交互式界面：

```bash
# 启动交互式 CLI
sudo -E .venv/bin/python vortinet_cli.py

# 直接执行命令
sudo -E .venv/bin/python vortinet_cli.py sessions          # 列出所有会话
sudo -E .venv/bin/python vortinet_cli.py switch 1          # 切换到会话 1
sudo -E .venv/bin/python vortinet_cli.py topology          # 显示拓扑
sudo -E .venv/bin/python vortinet_cli.py shell H1 H2 H3    # 批量打开终端
sudo -E .venv/bin/python vortinet_cli.py cleanup 1         # 清理会话 1
sudo -E .venv/bin/python vortinet_cli.py cleanup -f        # 清理所有资源
```

**CLI 常用命令**:
- `sessions`: 列出所有会话
- `switch <session>`: 切换到指定会话
- `list` / `ls`: 列出当前会话的节点
- `info <node>`: 查看节点详细信息
- `topology`: 显示网络拓扑结构
- `links`: 显示所有链路信息
- `shell <node> [node2...]`: 打开一个或多个节点的交互式终端（批量）
- `exec <node> <cmd>`: 在节点中执行命令
- `ping <src> <dst>`: 测试连通性
- `interfaces <node>`: 查看网络接口
- `routes <node>`: 查看路由表
- `cleanup [session]`: 清理指定会话或全部资源
- `help`: 查看帮助

### 5. 清理残留资源

```bash
# 快速清理所有会话（无需确认）
sudo -E .venv/bin/python vortinet_cli.py cleanup -f

# 清理指定会话（交互式）
sudo -E .venv/bin/python vortinet_cli.py cleanup 1

# 交互模式清理
sudo -E .venv/bin/python vortinet_cli.py
vortinet> cleanup        # 选择要清理的会话
vortinet> cleanup -f     # 清理所有会话
```

## 🔧 工作原理

Vortinet 采用模块化架构，核心流程分为三个阶段：

### 1. 定义阶段 (Topology & Models)
- 用户使用 `Topology` 对象定义网络结构
- 通过工厂函数（如 `create_host()`, `create_ovs_switch()`）创建节点
- 使用 `Link` 对象描述连接关系，支持交换链路和点对点链路

### 2. 部署阶段 (DeploymentController)
- **资源跟踪**: `ResourceTracker` 生成唯一会话 ID，为所有资源打标签
- **容器管理**: `ContainerManager` 创建容器并应用标签
- **网络配置**: `NetworkManager` 根据链路类型自动选择后端：
  - 点对点链路 → `DirectVethBackend` (直接 veth 对)
  - 交换链路 → `OVSBridgeBackend` (OVS 网桥)
- **启动**: 启动所有容器，拓扑开始运行

### 3. 清理阶段 (ResourceTracker)
- **标签查询**: 通过 Docker labels 和 OVS external-ids 识别资源
- **批量清理**: 停止并移除所有标记的容器和网桥
- **崩溃恢复**: 即使程序崩溃，独立清理工具也能通过标签恢复清理

### 关键设计

#### 标签系统
所有资源使用 `vortinet.*` 命名空间标签：
- **容器**: Docker labels (`vortinet.project`, `vortinet.session`, etc.)
- **OVS**: external-ids (`vortinet:project`, `vortinet:session`, etc.)
- **持久化**: 标签存储在 Docker/OVS 数据库中，不依赖内存

#### 网络后端
- **DirectVethBackend**: 直接创建 veth 对，支持 MAC、IP、TC 配置
- **OVSBridgeBackend**: 创建 OVS 网桥，支持 OpenFlow、VLAN、控制器
- **可扩展**: 新增后端只需实现 `NetworkBackend` 接口

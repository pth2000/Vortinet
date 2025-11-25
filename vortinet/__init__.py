"""
Vortinet - 基于 Docker 的网络仿真平台

提供声明式 API 用于定义和运行网络拓扑仿真。
"""

__version__ = "0.2.0"
__author__ = "pth2000"

# 核心抽象
from .models import Node, Interface, Link, Topology

# 部署控制器
from .deployment import DeploymentController

# 配置模型
from .config import NodeConfig, LinkConfig, ContainerConfig, BackendConfig

# 预定义节点类型
from .nodes import (
    create_base_node,
    create_router_node,
    create_host_node,
    create_ovs_switch,
    create_frr_router,
)

# 导入服务模块以触发注册
# 注意：必须在 DeploymentController 使用之前导入
from .services import frr
from .services.frr import FrrConfig

# IP 分配策略
from .utils import (
    IPAllocationStrategy,
    AutoSubnetStrategy,
    SharedSubnetStrategy,
    TopologyVisualizer,
)

__all__ = [
    # Core
    "Node",
    "Interface", 
    "Link",
    "Topology",
    "DeploymentController",
    # Config
    "BackendConfig",
    "NodeConfig",
    "LinkConfig",
    "ContainerConfig",
    # Nodes
    "create_base_node",
    "create_router_node",
    "create_host_node",
    "create_ovs_switch",
    "create_frr_router",
    "FrrConfig",
    # IP Strategies
    "IPAllocationStrategy",
    "AutoSubnetStrategy",
    "SharedSubnetStrategy",
    # Utils
    "TopologyVisualizer",
]

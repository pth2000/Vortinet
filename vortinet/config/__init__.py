"""
配置模型模块

使用 dataclass 提供类型安全的配置对象，替代 kwargs 字典。
"""

from .backend_config import BackendConfig, ContainerConfig, BuildConfig, OVSBridgeConfig
from .node_config import NodeConfig
from .link_config import LinkConfig, TrafficControlConfig
from .topology_config import TopologyConfig

__all__ = [
    "BackendConfig",
    "ContainerConfig",
    "BuildConfig",
    "OVSBridgeConfig",
    "NodeConfig",
    "LinkConfig",
    "TrafficControlConfig",
    "TopologyConfig",
]

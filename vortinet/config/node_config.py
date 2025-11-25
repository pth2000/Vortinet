"""
节点配置数据类

提供类型安全的节点配置，替代 kwargs 字典。
"""

from dataclasses import dataclass, field
from typing import Any, Dict
from .backend_config import BackendConfig


@dataclass
class NodeConfig:
    """节点配置
    
    只包含所有节点类型共有的配置。
    特定后端的配置（如容器的 build、post_start_commands）
    现在由各个 BackendConfig 子类管理。
    
    设计原则：
    - 单一职责：只管理节点级别的配置
    - 后端无关：不包含任何特定后端的配置
    - 委托验证：将验证逻辑委托给后端
    
    注意：请使用 vortinet.nodes 中的工厂函数创建节点，
    而不是直接使用 NodeConfig。
    """
    # 基础信息
    node_type: str
    
    # 后端配置（抽象，可以是容器、OVS、BMv2 等）
    backend: BackendConfig

    # 服务配置（可选）
    # 用于存储运行在节点上的服务配置，如 FRR 路由协议配置
    services: Dict[str, Any] = field(default_factory=dict)
    
    def validate(self) -> None:
        """验证配置的完整性和正确性
        
        委托给后端进行具体验证。
        """
        self.backend.validate()
    
    @property
    def backend_type(self) -> str:
        """获取后端类型"""
        return self.backend.get_backend_type()

    @property
    def is_switch(self) -> bool:
        """是否为交换机节点（L2 转发）"""
        return self.node_type in {
            "switch", 
            "ovs_switch", 
            "linux_bridge_switch", 
            "linux_bridge"
        }

    @property
    def is_router(self) -> bool:
        """是否为路由器节点（L3 转发）"""
        return self.node_type in {"router", "frr_router"}

    @property
    def is_host(self) -> bool:
        """是否为主机节点（终端设备）"""
        return self.node_type in {"host", "base"}

    @property
    def is_ovs(self) -> bool:
        """是否为 OVS 交换机"""
        return self.node_type == "ovs_switch"

    @property
    def is_linux_bridge(self) -> bool:
        """是否为 Linux Bridge 交换机"""
        return self.node_type in {"linux_bridge_switch", "linux_bridge"}


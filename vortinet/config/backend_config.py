"""
后端配置抽象

支持多种节点实现方式：
- Docker 容器
- OVS 进程
- BMv2 P4 交换机
- Linux Network Namespace
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path


class BackendConfig(ABC):
    """后端配置的抽象基类
    
    不同的后端实现（容器、OVS、BMv2）都继承此类。
    这样 NodeConfig 可以接受任何后端类型。
    """
    
    @abstractmethod
    def get_backend_type(self) -> str:
        """返回后端类型标识
        
        Returns:
            后端类型：'container', 'ovs', 'bmv2', 'netns' 等
        """
        pass
    
    @abstractmethod
    def validate(self) -> None:
        """验证配置的有效性
        
        Raises:
            ValueError: 配置无效时抛出
        """
        pass


@dataclass(frozen=True)
class BuildConfig:
    """Docker 镜像构建配置"""
    context_path: Path
    dockerfile: str = "Dockerfile"
    build_args: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        # 验证路径存在
        if not self.context_path.exists():
            raise ValueError(f"构建上下文路径不存在: {self.context_path}")


@dataclass
class ContainerConfig(BackendConfig):
    """Docker 容器后端配置
    
    用于基于 Docker 容器的网络节点（如 FRR 路由器）。
    包含所有容器特定的配置。
    """
    # 基础镜像配置
    image: str
    command: Optional[str] = None
    entrypoint: Optional[str] = None
    
    # 镜像构建配置（可选）
    build: Optional[BuildConfig] = None
    
    # 运行时配置
    environment: Dict[str, str] = field(default_factory=dict)
    capabilities: List[str] = field(default_factory=lambda: ["NET_ADMIN", "NET_RAW", "SYS_ADMIN"])
    privileged: bool = False
    volumes: List[str] = field(default_factory=list)
    
    # 生命周期钩子（容器特有）
    post_start_commands: List[str] = field(default_factory=list)
    pre_stop_commands: List[str] = field(default_factory=list)
    
    def get_backend_type(self) -> str:
        return "container"
    
    def validate(self) -> None:
        """验证容器配置"""
        if not self.image:
            raise ValueError("容器镜像不能为空")
        
        # 验证构建配置
        if self.build and not self.build.context_path.exists():
            raise ValueError(f"构建上下文不存在: {self.build.context_path}")
        
        # 验证 capabilities 格式
        valid_caps = {"NET_ADMIN", "NET_RAW", "SYS_ADMIN", "SYS_MODULE", "NET_BROADCAST"}
        for cap in self.capabilities:
            if cap not in valid_caps:
                # 警告但不抛出异常，允许自定义 capability
                pass


@dataclass
class OVSBridgeConfig(BackendConfig):
    """Open vSwitch Bridge 后端配置
    
    用于 OVS 交换机节点。OVS 在宿主机上作为进程运行，
    不需要容器。
    """
    bridge_name: str
    controller: Optional[str] = None  # OpenFlow controller (e.g., "tcp:127.0.0.1:6653")
    openflow_version: str = "OpenFlow13"
    fail_mode: str = "standalone"  # "standalone" or "secure"
    
    def get_backend_type(self) -> str:
        return "ovs_bridge"
    
    def validate(self) -> None:
        """验证 OVS 配置"""
        if not self.bridge_name:
            raise ValueError("OVS bridge 名称不能为空")
        
        valid_of_versions = {"OpenFlow10", "OpenFlow11", "OpenFlow12", 
                            "OpenFlow13", "OpenFlow14", "OpenFlow15"}
        if self.openflow_version not in valid_of_versions:
            raise ValueError(
                f"不支持的 OpenFlow 版本: {self.openflow_version}。"
                f"支持的版本: {valid_of_versions}"
            )
        
        valid_fail_modes = {"standalone", "secure"}
        if self.fail_mode not in valid_fail_modes:
            raise ValueError(
                f"无效的失败模式: {self.fail_mode}。"
                f"有效值: {valid_fail_modes}"
            )


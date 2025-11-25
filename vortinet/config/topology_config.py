"""
拓扑全局配置
"""

from dataclasses import dataclass
from ipaddress import IPv4Network


@dataclass
class TopologyConfig:
    """拓扑全局配置"""
    # IP 地址分配
    base_network: IPv4Network = IPv4Network("10.10.0.0/16")
    subnet_prefix_length: int = 24
    
    def validate(self) -> None:
        """验证配置有效性"""
        if self.subnet_prefix_length <= self.base_network.prefixlen:
            raise ValueError(
                f"子网前缀长度 ({self.subnet_prefix_length}) "
                f"必须大于基础网络前缀长度 ({self.base_network.prefixlen})"
            )
        
        if self.subnet_prefix_length > 30:
            raise ValueError(f"子网前缀长度过大，无法分配足够的主机地址: {self.subnet_prefix_length}")

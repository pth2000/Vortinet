"""
IP 地址分配器

支持可插拔的分配策略，提供灵活的 IP 管理能力。

改进：
- 策略模式: 支持多种分配策略
- 向后兼容: 保持原有 API
- 可扩展: 用户可自定义策略
"""

from ipaddress import IPv4Network, IPv4Address
from typing import Optional
import logging

from .ip_strategy import IPAllocationStrategy, AutoSubnetStrategy

logger = logging.getLogger(__name__)


class IPAddressAllocator:
    """管理和分配指定网络中的IP地址
    
    特点：
    - 支持可插拔的分配策略
    - 默认使用自动扩展网段策略
    - 可在运行时切换策略
    
    示例:
        # 使用默认策略
        allocator = IPAddressAllocator()
        
        # 使用自定义策略
        from vortinet.utils import SharedSubnetStrategy
        allocator = IPAddressAllocator(strategy=SharedSubnetStrategy(...))
    """
    
    def __init__(self, strategy: Optional[IPAllocationStrategy] = None):
        """
        Args:
            strategy: IP 分配策略，None 则使用默认的自动扩展网段策略
        """
        self._strategy = strategy or AutoSubnetStrategy()
        logger.debug(f"IPAddressAllocator 使用策略: {self._strategy.__class__.__name__}")
    
    @property
    def strategy(self) -> IPAllocationStrategy:
        """当前使用的分配策略（只读）"""
        return self._strategy
    
    def set_strategy(self, strategy: IPAllocationStrategy) -> None:
        """切换分配策略
        
        Args:
            strategy: 新的分配策略
            
        Warning:
            切换策略会重置之前的分配状态
        """
        self._strategy = strategy
        logger.info(f"切换 IP 分配策略为: {strategy.__class__.__name__}")
    
    def add_network(self, network: IPv4Network) -> None:
        """添加一个新的网络到分配器中
        
        Args:
            network: IPv4 网络对象
        """
        self._strategy.add_network(network)
    
    def allocate_ip(
        self,
        network: IPv4Network,
        hint: Optional[str] = None
    ) -> IPv4Address:
        """为指定的网络分配一个可用的IP地址
        
        Args:
            network: IPv4 网络对象
            hint: 分配提示（如节点名、角色），策略可选择使用
            
        Returns:
            分配的 IP 地址
            
        Raises:
            RuntimeError: 如果网络中没有可用IP地址
        """
        return self._strategy.allocate(network, hint)
    
    def reserve_ip(
        self,
        network: IPv4Network,
        hint: str,
        ip: IPv4Address
    ) -> None:
        """预留 IP 地址
        
        Args:
            network: IPv4 网络对象
            hint: 节点名称
            ip: IP 地址
        """
        self._strategy.reserve(network, hint, ip)

    def release_ip(self, network: IPv4Network, ip: IPv4Address) -> None:
        """释放一个IP地址，使其可以被重新分配
        
        Args:
            network: IPv4 网络对象
            ip: 要释放的 IP 地址
        """
        self._strategy.release(network, ip)
    
    def reset(self) -> None:
        """重置分配器，清空所有网络和IP地址"""
        self._strategy.reset()
        logger.debug("IPAddressAllocator 已重置")

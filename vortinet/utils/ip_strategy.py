"""
IP 地址分配策略

提供实用的 IP 分配策略：
1. AutoSubnetStrategy - 自动扩展网段（点对点连接），支持手动预留
2. SharedSubnetStrategy - 同网段自增 IP（交换机组网）

设计原则:
- 实用性: 每个策略对应一个真实场景
- 简单性: 易于理解和使用
- 灵活性: 支持自定义扩展
"""

from abc import ABC, abstractmethod
from ipaddress import IPv4Address, IPv4Network
from typing import Optional, Dict, Set, List, Tuple
import logging

logger = logging.getLogger(__name__)


class IPAllocationStrategy(ABC):
    """IP 分配策略抽象基类"""
    
    @abstractmethod
    def allocate(self, network: IPv4Network, hint: Optional[str] = None) -> IPv4Address:
        """分配 IP 地址
        
        Args:
            network: 目标网络
            hint: 分配提示（如节点名、角色等）
            
        Returns:
            分配的 IP 地址
        """
        pass
    
    @abstractmethod
    def release(self, network: IPv4Network, ip: IPv4Address) -> None:
        """释放 IP 地址"""
        pass
    
    @abstractmethod
    def reset(self) -> None:
        """重置策略状态"""
        pass
    
    @abstractmethod
    def add_network(self, network: IPv4Network) -> None:
        """添加网络到策略管理"""
        pass

    def reserve(self, network: IPv4Network, hint: str, ip: IPv4Address) -> None:
        """预留 IP 地址 (可选实现)"""
        raise NotImplementedError(f"{self.__class__.__name__} 不支持 IP 预留")



class AutoSubnetStrategy(IPAllocationStrategy):
    """自动扩展网段策略（默认策略）
    
    特点:
    - 每个连接使用独立子网
    - 自动从子网池分配
    - 适合点对点连接（如路由器-路由器、主机-主机）
    
    使用场景:
    - 无交换机的拓扑
    - 路由器互联
    - 点对点链路
    
    示例:
        R1-R2: 10.10.0.0/24 (R1: .1, R2: .2)
        R2-R3: 10.10.1.0/24 (R2: .1, R3: .2)
        H1-H2: 10.10.2.0/24 (H1: .1, H2: .2)
    
    优点:
    - 每个链路独立，互不干扰
    - 符合路由器网络设计
    - 子网隔离清晰
    """
    
    def __init__(self, start_from: int = 1):
        """
        Args:
            start_from: 每个子网内从第几个 IP 开始分配（默认 1，即 .1）
        """
        self._start_from = start_from
        self._network_counters: Dict[str, int] = {}  # 每个子网的分配计数器
        self._used_ips: Dict[str, Set[IPv4Address]] = {}
        # 预留记录: network_str -> {hint -> ip}
        self._reservations: Dict[str, Dict[str, IPv4Address]] = {}
    
    def add_network(self, network: IPv4Network) -> None:
        network_str = str(network)
        if network_str not in self._network_counters:
            self._network_counters[network_str] = self._start_from
            self._used_ips[network_str] = set()
            self._reservations[network_str] = {}
            logger.debug(f"[AutoSubnet] 添加网络 {network_str}")
    
    def reserve(self, network: IPv4Network, hint: str, ip: IPv4Address) -> None:
        """预留 IP"""
        network_str = str(network)
        if network_str not in self._network_counters:
            self.add_network(network)
            
        if ip not in network:
            raise ValueError(f"IP {ip} 不在网络 {network} 中")
            
        if ip in self._used_ips[network_str]:
            # 检查是否是同一个 hint 的重复预留
            existing = self._reservations[network_str].get(hint)
            if existing == ip:
                return
            raise ValueError(f"IP {ip} 已被使用")
            
        self._used_ips[network_str].add(ip)
        self._reservations[network_str][hint] = ip
        logger.debug(f"[AutoSubnet] 预留 {ip} for {hint} in {network_str}")

    def allocate(self, network: IPv4Network, hint: Optional[str] = None) -> IPv4Address:
        network_str = str(network)
        if network_str not in self._network_counters:
            self.add_network(network)
        
        # 1. 检查是否有预留
        if hint and hint in self._reservations[network_str]:
            ip = self._reservations[network_str][hint]
            logger.debug(f"[AutoSubnet] 分配预留 IP {ip} for {hint}")
            return ip

        # 2. 自动分配
        total_hosts = network.num_addresses - 2
        
        while True:
            counter = self._network_counters[network_str]
            if counter > total_hosts:
                raise RuntimeError(
                    f"子网 {network_str} 已耗尽 (需要第 {counter} 个 IP，但只有 {total_hosts} 个)"
                )
            
            ip = network[counter]
            self._network_counters[network_str] += 1
            
            # 如果 IP 已被使用（例如被预留），跳过
            if ip in self._used_ips[network_str]:
                continue
                
            self._used_ips[network_str].add(ip)
            logger.debug(f"[AutoSubnet] 分配 {ip} from {network_str} (第 {counter} 个)")
            return ip
    
    def release(self, network: IPv4Network, ip: IPv4Address) -> None:
        network_str = str(network)
        if network_str in self._used_ips:
            self._used_ips[network_str].discard(ip)
            # 清理预留记录
            if network_str in self._reservations:
                # 效率较低，但 release 操作不频繁
                for hint, reserved_ip in list(self._reservations[network_str].items()):
                    if reserved_ip == ip:
                        del self._reservations[network_str][hint]
                        break
    
    def reset(self) -> None:
        self._network_counters.clear()
        self._used_ips.clear()
        self._reservations.clear()


class SharedSubnetStrategy(IPAllocationStrategy):
    """同网段自增 IP 策略
    
    特点:
    - 所有节点共享同一个子网
    - IP 地址顺序递增
    - 适合交换机组网场景
    
    使用场景:
    - 交换机连接的多个主机
    - 同一广播域的网络
    - 快速搭建局域网
    
    示例:
        使用子网 192.168.1.0/24:
        H1: 192.168.1.1
        H2: 192.168.1.2
        H3: 192.168.1.3
        R1: 192.168.1.254 (可选网关)
    
    优点:
    - 简单直观
    - 节省子网
    - 适合交换网络
    """
    
    def __init__(
        self,
        shared_network: IPv4Network,
        start_from: int = 1,
        reserve_gateway: bool = False,
        gateway_ip: Optional[str] = None
    ):
        """
        Args:
            shared_network: 共享的子网（如 192.168.1.0/24）
            start_from: 从第几个 IP 开始分配（默认 1）
            reserve_gateway: 是否预留网关地址
            gateway_ip: 网关 IP（如 "192.168.1.254"），None 则使用最后一个可用 IP
        """
        self._shared_network = shared_network
        self._start_from = start_from
        self._reserve_gateway = reserve_gateway
        
        # 优化：不再预生成所有 IP 列表，改为按需计算
        self._next_index = start_from
        self._released_ips: List[IPv4Address] = []  # 释放的 IP 列表（优先重用）
        self._used_ips: Set[IPv4Address] = set()
        
        # 处理网关预留
        self._gateway_ip: Optional[IPv4Address] = None
        if reserve_gateway:
            if gateway_ip:
                self._gateway_ip = IPv4Address(gateway_ip)
                # 验证网关 IP 是否在子网内
                if self._gateway_ip not in shared_network:
                    raise ValueError(f"网关 IP {gateway_ip} 不在子网 {shared_network} 内")
                if self._gateway_ip == shared_network.network_address or self._gateway_ip == shared_network.broadcast_address:
                    raise ValueError(f"网关 IP {gateway_ip} 不能是网络地址或广播地址")
            else:
                # 默认使用最后一个 IP 作为网关
                # network[-2] 是最后一个可用 IP (network[-1] 是广播)
                self._gateway_ip = shared_network[-2]
        
        logger.debug(
            f"[SharedSubnet] 初始化子网 {shared_network}，"
            f"网关: {self._gateway_ip}"
        )

    def add_network(self, network: IPv4Network) -> None:
        # SharedSubnet 只使用一个预定义的网络，忽略新网络
        if network != self._shared_network:
            logger.warning(
                f"[SharedSubnet] 忽略网络 {network}，"
                f"只使用预定义的 {self._shared_network}"
            )
    
    def allocate(self, network: IPv4Network, hint: Optional[str] = None) -> IPv4Address:
        # 检查是否请求网关地址
        if hint and "gateway" in hint.lower() and self._gateway_ip:
            logger.debug(f"[SharedSubnet] 分配网关 IP: {self._gateway_ip}")
            return self._gateway_ip
        
        # 优先使用释放的 IP
        if self._released_ips:
            ip = self._released_ips.pop(0)
            self._used_ips.add(ip)
            logger.debug(f"[SharedSubnet] 重用释放 IP {ip}")
            return ip

        # 分配新 IP
        total_hosts = self._shared_network.num_addresses - 2
        
        while True:
            if self._next_index > total_hosts:
                raise RuntimeError(
                    f"共享子网 {self._shared_network} 的 IP 地址已耗尽 "
                    f"(已用: {len(self._used_ips)})"
                )
            
            ip = self._shared_network[self._next_index]
            self._next_index += 1
            
            # 如果是网关 IP，跳过
            if self._reserve_gateway and self._gateway_ip and ip == self._gateway_ip:
                continue
                
            self._used_ips.add(ip)
            logger.debug(f"[SharedSubnet] 分配 {ip}")
            return ip
    
    def release(self, network: IPv4Network, ip: IPv4Address) -> None:
        if ip in self._used_ips:
            self._used_ips.remove(ip)
            self._released_ips.append(ip)
    
    def reset(self) -> None:
        self._next_index = self._start_from
        self._released_ips.clear()
        self._used_ips.clear()
    
    @property
    def gateway_ip(self) -> Optional[IPv4Address]:
        """获取网关 IP（如果预留了）"""
        return self._gateway_ip


# 默认策略：自动扩展网段（最通用）
DEFAULT_STRATEGY = AutoSubnetStrategy()

"""
IP地址分配工具
"""
from ipaddress import IPv4Network, IPv4Address, AddressValueError


class IPAddressAllocator:
    """
    管理和分配指定网络中的IP地址。
    """
    def __init__(self):
        self.available_ips = {}  # key: network_cidr_str, value: list of available IPv4Address
        self.used_ips = {}       # key: network_cidr_str, value: set of used IPv4Address

    def add_network(self, network_cidr: IPv4Network):
        """
        添加一个新的网络到分配器中，并初始化其IP地址池。
        默认会排除网络地址、广播地址和通常被用作网关的`.1`地址。
        """
        network_cidr_str = str(network_cidr)
        if network_cidr_str in self.available_ips:
            return

        # 获取所有可用主机IP地址
        available_ips = set(network_cidr.hosts())

        # 排除 .1 地址 (通常是Docker网桥的IP)
        try:
            excluded_ip = network_cidr.network_address + 1
            if excluded_ip in available_ips:
                available_ips.remove(excluded_ip)
        except (AddressValueError, ValueError):
            # 在 /31 或 /32 网络中，+1 可能无效
            pass

        # 倒序排序，方便 pop() 获取较小的地址
        self.available_ips[network_cidr_str] = sorted(list(available_ips), reverse=True)
        self.used_ips[network_cidr_str] = set()

    def allocate_ip(self, network_cidr: IPv4Network) -> IPv4Address:
        """
        为指定的网络分配一个可用的IP地址。
        """
        network_cidr_str = str(network_cidr)
        if network_cidr_str not in self.available_ips:
            self.add_network(network_cidr)

        if not self.available_ips[network_cidr_str]:
            raise ValueError(f"网络 {network_cidr_str} 中已无可用IP地址。")

        ip = self.available_ips[network_cidr_str].pop()
        self.used_ips[network_cidr_str].add(ip)
        return ip

    def release_ip(self, network_cidr: IPv4Network, ip: IPv4Address):
        """
        释放一个IP地址，使其可以被重新分配。
        """
        network_cidr_str = str(network_cidr)
        if network_cidr_str in self.used_ips and ip in self.used_ips[network_cidr_str]:
            self.used_ips[network_cidr_str].remove(ip)
            self.available_ips[network_cidr_str].append(ip)
            self.available_ips[network_cidr_str].sort(reverse=True)  # 保持有序

    def reset(self):
        """
        重置分配器，清空所有网络和IP地址。
        """
        self.available_ips = {}
        self.used_ips = {}


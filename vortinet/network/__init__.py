"""
网络管理模块

负责创建和管理实际的网络连接（veth pair, OVS bridge, Linux bridge等）
"""

from .network_backend import NetworkBackend
from .direct_veth_backend import DirectVethBackend
from .ovs_bridge_backend import OVSBridgeBackend
from .linux_bridge_backend import LinuxBridgeBackend
from .network_manager import NetworkManager

__all__ = [
    "NetworkBackend",
    "DirectVethBackend",
    "OVSBridgeBackend",
    "LinuxBridgeBackend",
    "NetworkManager",
]

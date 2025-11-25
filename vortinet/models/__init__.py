"""
核心领域模型

定义网络拓扑的基础抽象，职责单一、边界清晰。
"""

from .node import Node
from .interface import Interface
from .link import Link
from .topology import Topology

__all__ = ["Node", "Interface", "Link", "Topology"]

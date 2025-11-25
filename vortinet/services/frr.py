"""
FRR 服务模块

包含 FRR 配置生成逻辑和服务注册。
"""

import os
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Union, Optional
from ..models.node import Node
from .registry import ServiceRegistry

logger = logging.getLogger(__name__)

@dataclass
class FrrConfig:
    """FRR 服务配置
    
    用于定义 FRR 路由器的行为。
    """
    # 启用的守护进程列表
    # 默认只启用 zebra，其他协议需显式启用
    daemons: List[str] = field(default_factory=lambda: ["zebra"])
    
    # 是否自动生成 OSPF 配置
    # 默认为 False，以保持配置的显式性和严谨性
    # 如果需要快速搭建 OSPF 实验，请显式设置为 True
    auto_ospf: bool = False
    
    # 额外的原生配置行
    # 用于注入 BGP, RIP, ISIS 或更复杂的 OSPF 配置
    extra_config: List[str] = field(default_factory=list)


class FrrConfigGenerator:
    """FRR 配置生成器"""

    @staticmethod
    def generate(node: Node, output_dir: Path) -> None:
        """
        为指定节点生成 FRR 配置文件。

        Args:
            node: FRR 路由器节点对象
            output_dir: 配置文件输出目录 (宿主机路径)
        """
        if not output_dir.exists():
            output_dir.mkdir(parents=True, exist_ok=True)

        # 获取 FRR 配置
        frr_config = node.config.services.get('frr')
        if not isinstance(frr_config, FrrConfig):
            # 如果未配置，使用默认配置
            frr_config = FrrConfig()
        
        # 1. 生成 daemons 文件
        FrrConfigGenerator._generate_daemons(output_dir, frr_config)

        # 2. 生成 vtysh.conf 文件
        FrrConfigGenerator._generate_vtysh_conf(output_dir)

        # 3. 生成 frr.conf 文件
        FrrConfigGenerator._generate_frr_conf(node, output_dir, frr_config)

    @staticmethod
    def _generate_daemons(output_dir: Path, config: FrrConfig) -> None:
        """生成 daemons 配置文件"""
        daemons_path = output_dir / 'daemons'
        
        # 默认启用的守护进程
        enabled_daemons = set(config.daemons)
        
        # 所有支持的守护进程列表
        all_daemons = [
            "zebra", "bgpd", "ospfd", "ospf6d", "ripd", "ripngd", "isisd", 
            "pimd", "ldpd", "nhrpd", "eigrpd", "babeld", "sharpd", "staticd", 
            "pbrd", "bfdd", "fabricd", "vrrpd"
        ]
        
        content = []
        for daemon in all_daemons:
            state = "yes" if daemon in enabled_daemons else "no"
            content.append(f"{daemon}={state}")
            
        with open(daemons_path, 'w') as f:
            f.write("\n".join(content) + "\n")

    @staticmethod
    def _generate_vtysh_conf(output_dir: Path) -> None:
        """生成 vtysh.conf 配置文件"""
        vtysh_path = output_dir / 'vtysh.conf'
        with open(vtysh_path, 'w') as f:
            f.write("service integrated-vtysh-config\n")
            f.write("hostname {}\n".format(output_dir.parent.name)) # 这里的 hostname 实际上由 frr.conf 控制，vtysh.conf 主要是 service 配置

    @staticmethod
    def _generate_frr_conf(node: Node, output_dir: Path, config: FrrConfig) -> None:
        """生成 frr.conf 配置文件"""
        frr_conf_path = output_dir / 'frr.conf'
        
        with open(frr_conf_path, 'w') as f:
            f.write(f"hostname {node.name}\n")
            f.write("log stdout\n")
            f.write("!\n")
            
            # 自动生成 OSPF 配置
            if config.auto_ospf:
                # 配置接口
                for iface in node.interfaces.values():
                    f.write(f"interface {iface.name}\n")
                    # 强制点对点模式，加快收敛并避免 DR/BDR 选举问题
                    f.write(" ip ospf network point-to-point\n")
                    f.write("!\n")
                
                f.write("router ospf\n")
                # 尝试获取 eth0 的 IP 作为 Router ID，如果没有则不设置（FRR 会自动选择）
                if 'eth0' in node.interfaces and node.interfaces['eth0'].ip_address:
                     f.write(f" router-id {node.interfaces['eth0'].ip_address}\n")
                
                f.write(" redistribute connected\n") # 确保所有直连网段都被发布
                
                # 动态宣告该节点所有接口所在的网络
                has_networks = False
                for iface in node.interfaces.values():
                    if iface.link and iface.link.subnet:
                        f.write(f" network {iface.link.subnet} area 0\n")
                        has_networks = True
                
                if not has_networks:
                    f.write(" ! Warning: No subnets detected from interfaces\n")
                
                f.write("!\n")
            
            # 写入额外的自定义配置
            if config.extra_config:
                f.write("! Extra Configuration\n")
                if isinstance(config.extra_config, list):
                    f.write("\n".join(config.extra_config) + "\n")
                else:
                    f.write(str(config.extra_config) + "\n")
                f.write("!\n")

            f.write("line vty\n")
            f.write("!\n")


class FrrService:
    """FRR 节点服务处理器"""
    
    def prepare(self, node: Node, session_id: str) -> List[str]:
        """
        准备 FRR 节点资源
        
        1. 生成配置文件
        2. 返回挂载路径
        """
        config_dir = Path(f"/tmp/vortinet/{session_id}/configs/{node.name}/etc/frr")
        
        # 生成配置文件
        FrrConfigGenerator.generate(node, config_dir)
        
        logger.info(f"为节点 {node.name} 生成 FRR 配置: {config_dir}")
        
        # 返回挂载配置: host_path:container_path:mode
        return [f"{config_dir.absolute()}:/etc/frr:rw"]


# 注册服务
ServiceRegistry.register("frr_router", FrrService())

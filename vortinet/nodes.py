"""
预定义节点类型

提供常用节点类型的工厂函数，简化节点创建。
基于能力组合实现，而非继承。
"""

from pathlib import Path
from typing import Optional, Union, List

from .models import Node
from .config import NodeConfig, ContainerConfig, BuildConfig, OVSBridgeConfig
from .services.frr import FrrConfig

# 获取项目根目录（用于定位 Dockerfile）
PROJECT_ROOT = Path(__file__).parent.parent


def create_base_node(
    name: str,
    image: str = "vortinet_base:latest",
    command: Optional[str] = None,
    volumes: Optional[List[str]] = None
) -> Node:
    """创建基础节点
    
    Args:
        name: 节点名称
        image: 容器镜像
        command: 启动命令
        volumes: 挂载卷列表 (e.g. ["/host/path:/container/path"])
    
    Returns:
        基础节点对象
    """
    dockerfile_path = PROJECT_ROOT / "dockerfile" / "vortinet_base"
    config = NodeConfig(
        node_type="base",
        backend=ContainerConfig(
            image=image,
            command=command or "sh -c 'tail -f /dev/null'",
            volumes=volumes or [],
            build=BuildConfig(
                context_path=dockerfile_path,
                dockerfile="Dockerfile"
            ) if dockerfile_path.exists() else None
        )
    )
    
    return Node(name, config)


def create_host_node(
    name: str,
    image: str = "vortinet_base:latest",
    command: Optional[str] = None,
    volumes: Optional[List[str]] = None
) -> Node:
    """创建主机节点
    
    Args:
        name: 节点名称
        image: 容器镜像
        command: 启动命令
        volumes: 挂载卷列表 (e.g. ["/host/path:/container/path"])
    
    Returns:
        主机节点对象
    """
    dockerfile_path = PROJECT_ROOT / "dockerfile" / "vortinet_base"
    config = NodeConfig(
        node_type="host",
        backend=ContainerConfig(
            image=image,
            command=command or "sh -c 'tail -f /dev/null'",
            volumes=volumes or [],
            build=BuildConfig(
                context_path=dockerfile_path,
                dockerfile="Dockerfile"
            ) if dockerfile_path.exists() else None
        )
    )
    
    return Node(name, config)


def create_router_node(
    name: str,
    routing_protocol: Optional[str] = None,
    image: str = "vortinet_base:latest",
    enable_ip_forward: bool = True,
    volumes: Optional[List[str]] = None
) -> Node:
    """创建路由器节点
    
    Args:
        name: 节点名称
        routing_protocol: 路由协议 ("static", "ospf", "bgp", None) - 用于文档记录
        image: 容器镜像
        enable_ip_forward: 是否启用 IP 转发
        volumes: 挂载卷列表
    
    Returns:
        路由器节点对象
    """
    dockerfile_path = PROJECT_ROOT / "dockerfile" / "vortinet_base"
    config = NodeConfig(
        node_type="router",
        backend=ContainerConfig(
            image=image,
            command="sh -c 'tail -f /dev/null'",
            volumes=volumes or [],
            build=BuildConfig(
                context_path=dockerfile_path,
                dockerfile="Dockerfile"
            ) if dockerfile_path.exists() else None,
            post_start_commands=[
                "sysctl -w net.ipv4.ip_forward=1" if enable_ip_forward else ""
            ]
        )
    )
    
    return Node(name, config)


def create_frr_router(
    name: str,
    image: str = "vortinet_frr:latest",
    frr_config: Optional[FrrConfig] = None,
    volumes: Optional[List[str]] = None
) -> Node:
    """创建 FRR 路由器节点
    
    Args:
        name: 节点名称
        image: 容器镜像 (默认为 vortinet_frr:latest)
        frr_config: FRR 配置对象
        volumes: 挂载卷列表
    
    Returns:
        FRR 路由器节点对象
    """
    dockerfile_path = PROJECT_ROOT / "dockerfile" / "vortinet_frr"
    
    # 确保镜像名称包含 tag
    if ":" not in image:
        image = f"{image}:latest"
    
    # 处理配置
    final_config = frr_config
    if frr_config is None:
        final_config = FrrConfig()
    elif not isinstance(frr_config, FrrConfig):
        raise TypeError(f"frr_config must be of type FrrConfig, got {type(frr_config)}")
        
    config = NodeConfig(
        node_type="frr_router",
        backend=ContainerConfig(
            image=image,
            command="sh -c 'tail -f /dev/null'", # 保持容器运行
            volumes=volumes or [],
            build=BuildConfig(
                context_path=dockerfile_path,
                dockerfile="Dockerfile"
            ) if dockerfile_path.exists() else None,
            # 启动 FRR 服务
            post_start_commands=[
                "sysctl -w net.ipv4.ip_forward=1",
                "/usr/lib/frr/frrinit.sh start"
            ],
            # 赋予必要的权限
            privileged=True,
            capabilities=["NET_ADMIN", "SYS_ADMIN", "NET_RAW"]
        ),
        services={"frr": final_config}
    )
    
    return Node(name, config)


def create_ovs_switch(
    name: str,
    controller: Optional[str] = None,
    openflow_version: str = "OpenFlow13"
) -> Node:
    """创建 OVS 交换机节点
    
    Args:
        name: 交换机名称
        controller: OpenFlow 控制器地址 (e.g., "tcp:127.0.0.1:6653")
        openflow_version: OpenFlow 协议版本
    
    Returns:
        OVS 交换机节点对象
    """
    config = NodeConfig(
        node_type="ovs_switch",
        backend=OVSBridgeConfig(
            bridge_name=f"ovs-{name}",
            controller=controller,
            openflow_version=openflow_version
        )
    )
    
    return Node(name, config)

"""
清理工具插件
提供便捷的清理函数，可在示例中直接调用
"""

import docker
import logging
from typing import Dict, Optional

from .resource_tracker import ResourceTracker


logger = logging.getLogger(__name__)


def cleanup_all(verbose: bool = False) -> Dict[str, int]:
    """
    清理所有 Vortinet 资源
    
    这是一个便捷函数，可在示例代码中直接调用，无需重复编写清理逻辑。
    
    Args:
        verbose: 是否显示详细信息
        
    Returns:
        清理统计字典 {containers: int, ovs_bridges: int, veth_interfaces: int, errors: list}
        
    Example:
        >>> from vortinet.utils import cleanup_all
        >>> cleanup_all()  # 静默清理
        >>> cleanup_all(verbose=True)  # 显示详细信息
    """
    try:
        client = docker.from_env()
        sessions = ResourceTracker.list_all_sessions(client)
        
        if not sessions:
            if verbose:
                logger.info("没有找到 Vortinet 会话")
            return {"containers": 0, "ovs_bridges": 0, "veth_interfaces": 0, "errors": []}
        
        if verbose:
            logger.info(f"检测到 {len(sessions)} 个残留会话，正在清理...")
        
        stats = ResourceTracker.cleanup_all_vortinet_resources(client)
        
        if verbose:
            logger.info(
                f"清理完成: 容器={stats['containers']}, "
                f"OVS Bridges={stats['ovs_bridges']}, "
                f"Veth={stats['veth_interfaces']}"
            )
            if stats['errors']:
                logger.warning(f"清理错误 ({len(stats['errors'])} 个)")
                for error in stats['errors']:
                    logger.warning(f"  - {error}")
        
        return stats
        
    except Exception as e:
        if verbose:
            logger.error(f"清理失败: {e}")
        return {"containers": 0, "ovs_bridges": 0, "veth_interfaces": 0, "errors": [str(e)]}


def cleanup_session(session_id: str, verbose: bool = False) -> Dict[str, int]:
    """
    清理指定会话的资源
    
    Args:
        session_id: 会话ID
        verbose: 是否显示详细信息
        
    Returns:
        清理统计字典
        
    Example:
        >>> from vortinet.utils import cleanup_session
        >>> cleanup_session("abc123def456")
    """
    try:
        client = docker.from_env()
        
        if verbose:
            logger.info(f"清理会话: {session_id}")
        
        stats = ResourceTracker.cleanup_session(client, session_id)
        
        if verbose:
            logger.info(
                f"清理完成: 容器={stats['containers']}, "
                f"OVS Bridges={stats['ovs_bridges']}, "
                f"Veth={stats['veth_interfaces']}"
            )
            if stats['errors']:
                logger.warning(f"清理错误 ({len(stats['errors'])} 个)")
        
        return stats
        
    except Exception as e:
        if verbose:
            logger.error(f"清理失败: {e}")
        return {"containers": 0, "ovs_bridges": 0, "veth_interfaces": 0, "errors": [str(e)]}


def list_sessions(verbose: bool = True) -> Dict[str, dict]:
    """
    列出所有 Vortinet 会话
    
    Args:
        verbose: 是否打印会话信息
        
    Returns:
        会话字典 {session_id: {project, timestamp, containers}}
        
    Example:
        >>> from vortinet.utils import list_sessions
        >>> sessions = list_sessions()
        >>> for sid, info in sessions.items():
        ...     print(f"会话: {sid}, 项目: {info['project']}")
    """
    try:
        client = docker.from_env()
        sessions = ResourceTracker.list_all_sessions(client)
        
        if verbose:
            if not sessions:
                print("没有找到 Vortinet 会话")
            else:
                print(f"\n找到 {len(sessions)} 个会话:\n")
                for session_id, info in sessions.items():
                    print(f"会话 ID: {session_id}")
                    print(f"  项目: {info['project']}")
                    print(f"  时间: {info['timestamp']}")
                    print(f"  容器数: {len(info['containers'])}")
                    for container in info['containers']:
                        print(f"    - {container['name']} ({container['status']})")
                    print()
        
        return sessions
        
    except Exception as e:
        if verbose:
            logger.error(f"列出会话失败: {e}")
        return {}

"""
资源跟踪器

使用标签标记所有创建的资源（容器、OVS bridge等），
确保即使程序崩溃也能准确识别和清理。
"""

import hashlib
import time
from typing import Dict, Any, Optional
from datetime import datetime


class ResourceTracker:
    """资源跟踪器
    
    为所有创建的资源生成唯一标签，支持崩溃后的清理。
    
    设计原则：
    1. 每个部署会话有唯一的 session_id
    2. 所有资源都标记 session_id 和 project 标签
    3. 支持按 session_id 或 project 批量清理
    """
    
    # 标签前缀
    LABEL_PREFIX = "vortinet"
    
    # 标签键
    LABEL_PROJECT = f"{LABEL_PREFIX}.project"
    LABEL_SESSION = f"{LABEL_PREFIX}.session"
    LABEL_TIMESTAMP = f"{LABEL_PREFIX}.timestamp"
    LABEL_NODE_NAME = f"{LABEL_PREFIX}.node_name"
    LABEL_NODE_TYPE = f"{LABEL_PREFIX}.node_type"
    LABEL_LINK_NAME = f"{LABEL_PREFIX}.link_name"
    LABEL_RESOURCE_TYPE = f"{LABEL_PREFIX}.resource_type"
    
    def __init__(self, project_name: str, session_id: Optional[str] = None):
        """初始化资源跟踪器
        
        Args:
            project_name: 项目名称（拓扑名称）
            session_id: 会话ID，如果不提供则自动生成
        """
        self.project_name = project_name
        self.session_id = session_id or self._generate_session_id()
        self.timestamp = datetime.now().isoformat()
    
    def _generate_session_id(self) -> str:
        """生成唯一的会话ID
        
        Returns:
            会话ID字符串
        """
        # 使用项目名 + 时间戳 + 随机数生成哈希
        content = f"{self.project_name}-{time.time()}-{id(self)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def get_container_labels(self, node_name: str, node_type: str = "host") -> Dict[str, str]:
        """获取容器标签
        
        Args:
            node_name: 节点名称
            node_type: 节点类型 (host, router, switch等)
            
        Returns:
            标签字典
        """
        return {
            self.LABEL_PROJECT: self.project_name,
            self.LABEL_SESSION: self.session_id,
            self.LABEL_TIMESTAMP: self.timestamp,
            self.LABEL_NODE_NAME: node_name,
            self.LABEL_NODE_TYPE: node_type,
            self.LABEL_RESOURCE_TYPE: "container",
        }
    
    def get_ovs_bridge_tags(self, bridge_name: str, link_name: str) -> Dict[str, str]:
        """获取 OVS bridge 的外部ID标签
        
        OVS 使用 external-ids 而不是 Docker labels
        注意：OVS external-ids 的 key 中不能使用冒号，使用点号代替
        
        Args:
            bridge_name: Bridge 名称
            link_name: 链路名称
            
        Returns:
            外部ID字典
        """
        return {
            f"{self.LABEL_PREFIX}.project": self.project_name,
            f"{self.LABEL_PREFIX}.session": self.session_id,
            f"{self.LABEL_PREFIX}.timestamp": self.timestamp,
            f"{self.LABEL_PREFIX}.link-name": link_name,
            f"{self.LABEL_PREFIX}.resource-type": "ovs-bridge",
        }
    
    def get_veth_comment(self, node_name: str, interface_name: str) -> str:
        """获取 veth 接口的注释
        
        用于在主机上标记 veth 接口（通过 ip link 的 alias）
        
        Args:
            node_name: 节点名称
            interface_name: 接口名称
            
        Returns:
            注释字符串
        """
        return (
            f"{self.LABEL_PREFIX}:"
            f"project={self.project_name},"
            f"session={self.session_id},"
            f"node={node_name},"
            f"interface={interface_name}"
        )
    
    def get_cleanup_filters(self) -> Dict[str, Any]:
        """获取用于清理的过滤条件
        
        Returns:
            过滤条件字典
        """
        return {
            "label": [
                f"{self.LABEL_PROJECT}={self.project_name}",
                f"{self.LABEL_SESSION}={self.session_id}",
            ]
        }
    
    def get_project_cleanup_filters(self) -> Dict[str, Any]:
        """获取按项目清理的过滤条件（清理所有会话）
        
        Returns:
            过滤条件字典
        """
        return {
            "label": [
                f"{self.LABEL_PROJECT}={self.project_name}",
            ]
        }
    
    @classmethod
    def list_all_sessions(cls, docker_client: Any) -> Dict[str, Dict[str, Any]]:
        """列出所有 Vortinet 会话
        
        Args:
            docker_client: Docker 客户端
            
        Returns:
            会话信息字典 {session_id: {project, timestamp, containers, ...}}
        """
        sessions = {}
        
        # 查找所有带 vortinet 标签的容器
        filters = {"label": f"{cls.LABEL_PREFIX}.session"}
        containers = docker_client.containers.list(all=True, filters=filters)
        
        for container in containers:
            labels = container.labels
            session_id = labels.get(cls.LABEL_SESSION)
            project = labels.get(cls.LABEL_PROJECT, "unknown")
            timestamp = labels.get(cls.LABEL_TIMESTAMP, "unknown")
            
            if session_id not in sessions:
                sessions[session_id] = {
                    "project": project,
                    "timestamp": timestamp,
                    "containers": [],
                }
            
            sessions[session_id]["containers"].append({
                "id": container.id[:12],
                "name": container.name,
                "status": container.status,
                "node_name": labels.get(cls.LABEL_NODE_NAME),
            })
        
        return sessions
    
    @classmethod
    def cleanup_session(cls, docker_client: Any, session_id: str) -> Dict[str, int]:
        """清理指定会话的所有资源
        
        Args:
            docker_client: Docker 客户端
            session_id: 会话ID
            
        Returns:
            清理统计 {containers: count, ovs_bridges: count}
        """
        import subprocess
        import logging
        
        logger = logging.getLogger(__name__)
        stats = {"containers": 0, "ovs_bridges": 0, "veth_interfaces": 0, "errors": []}
        
        # 1. 清理容器
        filters = {"label": f"{cls.LABEL_SESSION}={session_id}"}
        containers = docker_client.containers.list(all=True, filters=filters)
        
        for container in containers:
            try:
                logger.info(f"清理容器: {container.name}")
                container.stop(timeout=5)
                container.remove(force=True)
                stats["containers"] += 1
            except Exception as e:
                logger.error(f"清理容器 {container.name} 失败: {e}")
                stats["errors"].append(f"Container {container.name}: {e}")
        
        # 2. 清理 OVS bridges
        # 列出所有 bridges
        try:
            result = subprocess.run(
                ["sudo", "ovs-vsctl", "list-br"],
                capture_output=True,
                text=True,
                check=True
            )
            bridges = result.stdout.strip().split('\n') if result.stdout.strip() else []
            
            for bridge in bridges:
                if not bridge:
                    continue
                
                # 检查 external-ids 是否匹配
                try:
                    result = subprocess.run(
                        ["sudo", "ovs-vsctl", "get", "bridge", bridge, "external-ids"],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    external_ids = result.stdout.strip()
                    
                    # 检查是否包含我们的会话标记
                    # 支持多种格式:
                    # 1. vortinet.session=xxx (无引号)
                    # 2. vortinet.session="xxx" (值带引号)
                    # 3. "vortinet.session"="xxx" (键值都带引号)
                    # 4. vortinet:session=xxx (旧格式，兼容)
                    patterns = [
                        f"{cls.LABEL_PREFIX}.session={session_id}",
                        f'{cls.LABEL_PREFIX}.session="{session_id}"',
                        f'"{cls.LABEL_PREFIX}.session"="{session_id}"',
                        f"{cls.LABEL_PREFIX}:session={session_id}",
                        f'"{cls.LABEL_PREFIX}:session"="{session_id}"',
                    ]
                    
                    if any(pattern in external_ids for pattern in patterns):
                        logger.info(f"清理 OVS bridge: {bridge}")
                        subprocess.run(
                            ["sudo", "ovs-vsctl", "del-br", bridge],
                            check=True,
                            capture_output=True
                        )
                        stats["ovs_bridges"] += 1
                except subprocess.CalledProcessError:
                    # Bridge 可能已经被删除或无法访问
                    pass
                    
        except subprocess.CalledProcessError as e:
            logger.warning(f"列出 OVS bridges 失败: {e}")
            stats["errors"].append(f"List OVS bridges: {e}")
        except FileNotFoundError:
            logger.warning("OVS 未安装")
        
        # 3. 清理残留的 veth 接口
        stats["veth_interfaces"] = cls._cleanup_veth_interfaces(session_id)
        
        return stats
    
    @classmethod
    def cleanup_all_vortinet_resources(cls, docker_client: Any) -> Dict[str, int]:
        """清理所有 Vortinet 资源（危险操作！）
        
        Args:
            docker_client: Docker 客户端
            
        Returns:
            清理统计
        """
        import logging
        import subprocess
        
        logger = logging.getLogger(__name__)
        logger.warning("清理所有 Vortinet 资源...")
        
        # 获取所有会话
        sessions = cls.list_all_sessions(docker_client)
        
        total_stats = {"containers": 0, "ovs_bridges": 0, "veth_interfaces": 0, "errors": []}
        
        for session_id in sessions.keys():
            logger.info(f"清理会话: {session_id}")
            stats = cls.cleanup_session(docker_client, session_id)
            
            total_stats["containers"] += stats["containers"]
            total_stats["ovs_bridges"] += stats["ovs_bridges"]
            total_stats["veth_interfaces"] += stats["veth_interfaces"]
            total_stats["errors"].extend(stats["errors"])
        
        # 额外清理：通过 external-ids 标签精确识别 Vortinet 创建的 bridge
        # 只清理带有 vortinet.project 标签的 bridge，避免误删其他应用的 bridge
        try:
            result = subprocess.run(
                ["ovs-vsctl", "list-br"],
                capture_output=True,
                text=True,
                check=True
            )
            bridges = result.stdout.strip().split('\n') if result.stdout.strip() else []
            
            for bridge in bridges:
                if not bridge:
                    continue
                
                # 检查 bridge 是否有 vortinet 标签
                try:
                    result = subprocess.run(
                        ["ovs-vsctl", "get", "bridge", bridge, "external-ids"],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    external_ids = result.stdout.strip()
                    
                    # 只清理明确标记为 vortinet 的 bridge
                    # 支持新旧两种格式：vortinet.project 和 vortinet:project
                    is_vortinet_bridge = (
                        f"{cls.LABEL_PREFIX}.project" in external_ids or
                        f'"{cls.LABEL_PREFIX}.project"' in external_ids or
                        f"{cls.LABEL_PREFIX}:project" in external_ids or
                        f'"{cls.LABEL_PREFIX}:project"' in external_ids
                    )
                    
                    if is_vortinet_bridge:
                        logger.info(f"清理残留 OVS bridge: {bridge}")
                        try:
                            subprocess.run(
                                ["ovs-vsctl", "del-br", bridge],
                                check=True,
                                capture_output=True
                            )
                            total_stats["ovs_bridges"] += 1
                        except subprocess.CalledProcessError as e:
                            logger.warning(f"清理 bridge {bridge} 失败: {e}")
                            total_stats["errors"].append(f"OVS bridge {bridge}: {e}")
                except subprocess.CalledProcessError:
                    # Bridge 可能已经被删除或没有 external-ids
                    pass
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        
        return total_stats
    
    @staticmethod
    def _cleanup_veth_interfaces(session_id: str = None) -> int:
        """清理残留的 veth 接口
        
        Args:
            session_id: 可选的会话ID，如果提供则只清理该会话的 veth
                       如果为 None，清理所有 vortinet 相关的 veth
        
        Returns:
            清理的接口数量
        """
        import subprocess
        import logging
        import re
        
        logger = logging.getLogger(__name__)
        count = 0
        
        try:
            # 获取所有网络接口
            result = subprocess.run(
                ["ip", "link", "show"],
                capture_output=True,
                text=True,
                check=True
            )
            
            # 匹配 veth 接口
            # OVS backend 创建的格式: H1-eth0@tmp-H1-eth0 或 tmp-H1-eth0@H1-eth0
            # Direct veth 格式: veth-xxx@veth-yyy
            # Docker 默认格式: vethXXXXXXX@if123 (7位随机十六进制)
            
            # 提取所有可能的 veth 接口名
            veth_pattern = re.compile(r'^\d+:\s+([^@:]+)[@:]', re.MULTILINE)
            all_interfaces = veth_pattern.findall(result.stdout)
            
            # 过滤 vortinet 相关的 veth
            vortinet_veths = []
            for iface in all_interfaces:
                # 排除 Docker 默认格式 (veth + 7位随机十六进制)
                if re.match(r'^veth[a-f0-9]{7}$', iface):
                    continue
                
                # 包含 vortinet 模式：
                # 1. veth- 开头 (direct veth backend)
                # 2. tmp- 开头 (OVS backend 临时端)
                # 3. H/R/S 等节点名开头且包含 -eth (OVS backend 主机端)
                # 4. 包含会话前缀格式 (6位hex-)
                if (iface.startswith('veth-') or 
                    iface.startswith('tmp-') or
                    re.match(r'^[A-Z]\d+-eth\d+', iface) or
                    re.match(r'^[a-f0-9]{6}-.+', iface)):
                    vortinet_veths.append(iface)
            
            if not vortinet_veths:
                return 0
            
            logger.info(f"发现 {len(vortinet_veths)} 个残留的 veth 接口")
            
            # 删除 veth 接口
            for veth in vortinet_veths:
                try:
                    logger.debug(f"删除 veth 接口: {veth}")
                    subprocess.run(
                        ["ip", "link", "delete", veth],
                        capture_output=True,
                        check=True
                    )
                    count += 1
                except subprocess.CalledProcessError as e:
                    # 接口可能已经不存在
                    logger.debug(f"删除 {veth} 失败: {e}")
            
            if count > 0:
                logger.info(f"✓ 清理了 {count} 个 veth 接口")
            
        except subprocess.CalledProcessError as e:
            logger.warning(f"清理 veth 接口失败: {e}")
        except Exception as e:
            logger.warning(f"清理 veth 接口时出错: {e}")
        
        return count


# 类型注解
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    Any = object

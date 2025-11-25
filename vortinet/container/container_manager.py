"""
容器管理器
负责创建、配置和管理 Docker 容器，集成 ResourceTracker 实现崩溃安全的资源跟踪
"""

import docker
from typing import Dict, List, Optional, Union
import logging

from ..models.node import Node
from ..utils import ResourceTracker


logger = logging.getLogger(__name__)

# 常量定义
SESSION_PREFIX_LENGTH = 6  # 会话ID前缀长度
DEFAULT_STOP_TIMEOUT = 10  # 容器停止超时时间（秒）


class ContainerManager:
    """容器管理器，使用 ResourceTracker 进行资源跟踪"""
    
    def __init__(
        self,
        client: docker.DockerClient,
        resource_tracker: Optional[ResourceTracker] = None
    ):
        """
        初始化容器管理器
        
        Args:
            client: Docker 客户端
            resource_tracker: 资源跟踪器（可选）
        """
        self.client = client
        self.resource_tracker = resource_tracker
        self._containers: Dict[str, docker.models.containers.Container] = {}
    
    def set_resource_tracker(self, tracker: ResourceTracker):
        """设置资源跟踪器"""
        self.resource_tracker = tracker
    
    def create_container(
        self,
        node: Node,
        image: str,
        privileged: bool = True,
        cap_add: Optional[List[str]] = None,
        environment: Optional[Dict[str, str]] = None,
        entrypoint: Optional[str] = None,
        volumes: Optional[List[str]] = None,
        **kwargs
    ) -> docker.models.containers.Container:
        """
        创建容器并应用资源标签
        
        Args:
            node: 节点对象
            image: 镜像名称
            privileged: 是否特权模式
            cap_add: 额外的 capabilities
            environment: 环境变量
            entrypoint: 容器入口点
            volumes: 卷挂载列表
            **kwargs: 传递给 docker.containers.create 的其他参数
        
        Returns:
            创建的容器对象
        """
        # 默认 capabilities
        if cap_add is None:
            cap_add = ["NET_ADMIN", "SYS_ADMIN"]
        
        # 合并环境变量
        env = environment or {}
        
        # 准备标签
        labels = {}
        container_name = node.name
        if self.resource_tracker:
            # 获取节点类型字符串
            node_type_str = node.node_type.value if hasattr(node.node_type, 'value') else str(node.node_type)
            labels = self.resource_tracker.get_container_labels(node.name, node_type_str)
            # 使用会话ID前缀避免容器重名
            session_prefix = self.resource_tracker.session_id[:SESSION_PREFIX_LENGTH]
            container_name = f"{session_prefix}-{node.name}"
            
            # 检查容器是否已存在
            try:
                existing = self.client.containers.get(container_name)
                logger.warning(f"容器 {container_name} 已存在，将被移除")
                existing.remove(force=True)
            except docker.errors.NotFound:
                pass  # 容器不存在，正常情况
        
        # 创建容器配置
        container_config = {
            "image": image,
            "name": container_name,
            "hostname": node.name,  # hostname 保持原名，便于识别
            "privileged": privileged,
            "cap_add": cap_add,
            "environment": env,
            "labels": labels,
            "detach": True,
            "network_mode": "none",  # 禁用默认网络，使用自定义 veth
            "stdin_open": True,
            "tty": True,
            **kwargs
        }
        
        # 添加可选配置
        if entrypoint:
            container_config["entrypoint"] = entrypoint
        
        if volumes:
            container_config["volumes"] = volumes
        
        logger.info(f"创建容器 {container_name} (node={node.name}, image={image})")
        
        try:
            container = self.client.containers.create(**container_config)
            self._containers[node.name] = container
            
            # 记录标签信息
            if labels:
                logger.debug(f"容器 {container_name} 标签: {labels}")
            
            return container
            
        except docker.errors.APIError as e:
            logger.error(f"创建容器失败: {e}")
            raise
    
    def start_container(self, node_name: Union[str, Node], node: Optional[Node] = None):
        """启动容器并执行启动后命令
        
        Args:
            node_name: 容器名称或节点对象
            node: 节点对象（可选，用于获取 post_start_commands）
        """
        if isinstance(node_name, Node):
            # 如果传入的是 Node 对象，且 node 参数为空，则自动填充 node 参数
            if node is None:
                node = node_name
            node_name = node_name.name

        container = self._containers.get(node_name)
        if not container:
            raise ValueError(f"容器 {node_name} 不存在")
        
        logger.info(f"启动容器 {node_name}")
        container.start()
        
        # 执行 post_start_commands
        if node and hasattr(node.config, 'backend'):
            backend = node.config.backend
            if hasattr(backend, 'post_start_commands') and backend.post_start_commands:
                logger.info(f"执行容器 {node_name} 的启动后命令")
                for cmd in backend.post_start_commands:
                    if cmd:  # 跳过空命令
                        try:
                            exit_code, output = container.exec_run(cmd)
                            if exit_code != 0:
                                error_msg = (
                                    f"容器 {node_name} 启动后命令失败 (退出码: {exit_code}): {cmd}\n"
                                    f"输出: {output.decode() if output else 'N/A'}"
                                )
                                logger.error(error_msg)
                                raise RuntimeError(error_msg)
                            else:
                                logger.debug(f"容器 {node_name} 执行成功: {cmd}")
                        except Exception as e:
                            logger.error(f"容器 {node_name} 执行命令失败: {cmd}\n错误: {e}")
                            raise
    
    def stop_container(self, node_name: Union[str, Node], node: Optional[Node] = None, timeout: int = DEFAULT_STOP_TIMEOUT):
        """停止容器并执行停止前命令
        
        Args:
            node_name: 容器名称或节点对象
            node: 节点对象（可选，用于获取 pre_stop_commands）
            timeout: 停止超时时间
        """
        if isinstance(node_name, Node):
            # 如果传入的是 Node 对象，且 node 参数为空，则自动填充 node 参数
            if node is None:
                node = node_name
            node_name = node_name.name

        container = self._containers.get(node_name)
        if not container:
            raise ValueError(f"容器 {node_name} 不存在")
        
        # 执行 pre_stop_commands
        if node and hasattr(node.config, 'backend'):
            backend = node.config.backend
            if hasattr(backend, 'pre_stop_commands') and backend.pre_stop_commands:
                logger.info(f"执行容器 {node_name} 的停止前命令")
                for cmd in backend.pre_stop_commands:
                    if cmd:  # 跳过空命令
                        try:
                            exit_code, output = container.exec_run(cmd)
                            if exit_code != 0:
                                error_msg = (
                                    f"容器 {node_name} 停止前命令失败 (退出码: {exit_code}): {cmd}\n"
                                    f"输出: {output.decode() if output else 'N/A'}"
                                )
                                logger.error(error_msg)
                                raise RuntimeError(error_msg)
                            else:
                                logger.debug(f"容器 {node_name} 执行成功: {cmd}")
                        except Exception as e:
                            logger.error(f"容器 {node_name} 执行命令失败: {cmd}\n错误: {e}")
                            raise
        
        logger.info(f"停止容器 {node_name}")
        container.stop(timeout=timeout)
    
    def remove_container(self, node_name: Union[str, Node], force: bool = True):
        """移除容器"""
        if isinstance(node_name, Node):
            node_name = node_name.name

        container = self._containers.get(node_name)
        if not container:
            raise ValueError(f"容器 {node_name} 不存在")
        
        logger.info(f"移除容器 {node_name}")
        container.remove(force=force)
        del self._containers[node_name]
    
    def get_container(self, node_name: Union[str, Node]) -> Optional[docker.models.containers.Container]:
        """获取容器对象"""
        if isinstance(node_name, Node):
            node_name = node_name.name
        return self._containers.get(node_name)
    
    def exec_run(
        self,
        node_name: Union[str, Node],
        cmd: str,
        **kwargs
    ) -> tuple:
        """
        在容器中执行命令
        
        Args:
            node_name: 节点名称或节点对象
            cmd: 命令
            **kwargs: 传递给 container.exec_run 的其他参数
        
        Returns:
            (exit_code, output)
        """
        if isinstance(node_name, Node):
            node_name = node_name.name

        container = self._containers.get(node_name)
        if not container:
            raise ValueError(f"容器 {node_name} 不存在")
        
        return container.exec_run(cmd, **kwargs)
    
    def cleanup_all(self):
        """清理所有管理的容器
        
        注意：清理时不执行 pre_stop_commands，以加快清理速度
        """
        logger.info(f"清理 {len(self._containers)} 个容器")
        
        errors = []
        for node_name in list(self._containers.keys()):
            try:
                # 清理时直接停止，不执行 pre_stop_commands
                container = self._containers.get(node_name)
                if container:
                    logger.info(f"停止容器 {node_name}")
                    container.stop(timeout=DEFAULT_STOP_TIMEOUT)
                self.remove_container(node_name)
            except Exception as e:
                logger.error(f"清理容器 {node_name} 失败: {e}")
                errors.append(str(e))
        
        if errors:
            raise Exception(f"清理过程中有 {len(errors)} 个错误")
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出，自动清理"""
        try:
            self.cleanup_all()
        except Exception as e:
            logger.error(f"上下文退出时清理失败: {e}")
    
    def provision_node(
        self,
        node: Node,
        project_name: str,
        session_id: str,
        default_image: str = "vortinet_base:latest",
        extra_volumes: Optional[List[str]] = None
    ) -> Optional[docker.models.containers.Container]:
        """
        根据节点配置自动置备容器
        
        Args:
            node: 节点对象
            project_name: 项目名称
            session_id: 会话 ID
            default_image: 默认镜像
            extra_volumes: 额外的卷挂载列表 (e.g. ["/host/path:/container/path:ro"])
            
        Returns:
            创建的容器对象，如果节点不是容器后端则返回 None
        """
        # 1. 检查后端类型
        if not hasattr(node.config, 'backend'):
            return None
            
        backend = node.config.backend
        if backend.get_backend_type() != 'container':
            return None
            
        # 2. 确定镜像
        # 如果 backend 配置中有镜像则使用，否则使用默认镜像
        # 注意：ContainerConfig.image 是必填项，但为了健壮性这里做个检查
        image = getattr(backend, 'image', None) or default_image
        
        # 3. 准备环境变量
        env = {
            "VORTINET_PROJECT": project_name,
            "VORTINET_SESSION": session_id,
            "VORTINET_NODE_NAME": node.name,
            "VORTINET_NODE_TYPE": node.config.node_type
        }
        if hasattr(backend, 'environment') and backend.environment:
            env.update(backend.environment)
            
        # 4. 准备参数
        create_kwargs = {
            'node': node,
            'image': image,
            'environment': env
        }
        
        # 提取可选配置
        if hasattr(backend, 'privileged'):
            create_kwargs['privileged'] = backend.privileged
        
        if hasattr(backend, 'capabilities'):
            create_kwargs['cap_add'] = backend.capabilities
        
        if hasattr(backend, 'entrypoint') and backend.entrypoint:
            create_kwargs['entrypoint'] = backend.entrypoint
        
        # 合并 volumes
        volumes = []
        if hasattr(backend, 'volumes') and backend.volumes:
            volumes.extend(backend.volumes)
        if extra_volumes:
            volumes.extend(extra_volumes)
        
        if volumes:
            create_kwargs['volumes'] = volumes
            
        if hasattr(backend, 'command') and backend.command:
            create_kwargs['command'] = backend.command
            
        # 5. 创建容器
        return self.create_container(**create_kwargs)

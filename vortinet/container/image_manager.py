"""
镜像管理器
负责 Docker 镜像的检查、拉取和构建
"""

import docker
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)


class ImageManager:
    """镜像管理器"""
    
    def __init__(self, client: docker.DockerClient):
        """
        初始化镜像管理器
        
        Args:
            client: Docker 客户端
        """
        self.client = client
        self._checked_images = set()
    
    def ensure_image(self, image_name: str, pull: bool = True) -> bool:
        """
        确保镜像存在
        
        Args:
            image_name: 镜像名称 (e.g. 'ubuntu:20.04')
            pull: 如果不存在是否尝试拉取
            
        Returns:
            bool: 镜像是否可用
        """
        # 避免重复检查
        if image_name in self._checked_images:
            return True
            
        try:
            self.client.images.get(image_name)
            self._checked_images.add(image_name)
            return True
        except docker.errors.ImageNotFound:
            if not pull:
                logger.warning(f"镜像 {image_name} 不存在且 pull=False")
                return False
                
            logger.info(f"镜像 {image_name} 本地不存在，尝试拉取...")
            try:
                # 分离仓库名和标签
                if ':' in image_name:
                    repository, tag = image_name.split(':', 1)
                else:
                    repository, tag = image_name, 'latest'
                
                self.client.images.pull(repository, tag=tag)
                logger.info(f"✓ 镜像 {image_name} 拉取成功")
                self._checked_images.add(image_name)
                return True
            except docker.errors.APIError as e:
                logger.error(f"拉取镜像 {image_name} 失败: {e}")
                return False
        except Exception as e:
            logger.error(f"检查镜像 {image_name} 时出错: {e}")
            return False

    def build_image(
        self, 
        path: str, 
        tag: str, 
        dockerfile: str = "Dockerfile",
        buildargs: Optional[dict] = None,
        nocache: bool = False
    ) -> bool:
        """
        构建镜像
        
        Args:
            path: 构建上下文路径
            tag: 目标镜像标签
            dockerfile: Dockerfile 文件名
            buildargs: 构建参数
            nocache: 是否禁用缓存
            
        Returns:
            bool: 构建是否成功
        """
        logger.info(f"正在构建镜像 {tag} (path={path})...")
        try:
            # 使用低级 API 以获取构建日志
            # 注意：这里简化处理，直接使用 images.build
            image, logs = self.client.images.build(
                path=path,
                tag=tag,
                dockerfile=dockerfile,
                buildargs=buildargs,
                nocache=nocache,
                rm=True
            )
            
            logger.info(f"✓ 镜像 {tag} 构建成功 ({image.short_id})")
            self._checked_images.add(tag)
            return True
            
        except docker.errors.BuildError as e:
            logger.error(f"构建镜像 {tag} 失败:")
            for line in e.build_log:
                if 'stream' in line:
                    logger.error(f"  {line['stream'].strip()}")
            return False
        except Exception as e:
            logger.error(f"构建镜像 {tag} 时出错: {e}")
            return False

"""
此模块定义了 SimulationRunner 类，用于封装标准的仿真流程。
"""
import logging
import time
from .topology import Topology
from .docker_controller import DockerController

class SimulationRunner:
    """
    封装标准的仿真流程，包括日志设置、环境准备、启动和清理。
    """
    def __init__(self, simulation_name: str = "VortinetCore"):
        self.logger = self._setup_logger(simulation_name)
        self.controller = None

    def _setup_logger(self, name: str) -> logging.Logger:
        """配置并返回一个日志记录器实例。"""
        logger = logging.getLogger(name)
        if not logger.handlers: # 防止重复添加 handler
            logger.setLevel(logging.INFO)
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '[%(asctime)s][%(name)s][%(levelname)s] - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        return logger

    def run(self, topology: Topology, auto_cleanup_after: int = 0):
        """
        执行完整的仿真流程。

        :param topology: 要仿真的网络拓扑。
        :param auto_cleanup_after: 仿真启动后自动清理的等待时间（秒）。
                                   如果为 0，则会一直运行直到手动中断 (Ctrl+C)。
        """
        self.logger.info("=== 初始化Docker控制器 ===")
        self.controller = DockerController(topology)

        try:
            self.logger.info("=== 步骤 1: 清理旧的仿真环境 ===")
            self.controller.stop_and_cleanup()

            self.logger.info("=== 步骤 2: 预配置Docker容器和网络 ===")
            self.controller.provision()

            self.logger.info("=== 步骤 3: 启动仿真 ===")
            self.controller.start()

            if auto_cleanup_after > 0:
                self.logger.info(f"仿真已启动。等待{auto_cleanup_after}秒后自动清理...")
                time.sleep(auto_cleanup_after)
            else:
                self.logger.info("仿真已启动。按 Ctrl+C 停止并清理环境。")
                while True:
                    time.sleep(1)

        except KeyboardInterrupt:
            self.logger.info("接收到手动中断信号...")
        except Exception as e:
            self.logger.error(f"仿真过程中发生错误: {e}", exc_info=True)
        finally:
            self.logger.info("=== 步骤 4: 停止并清理仿真环境 ===")
            if self.controller:
                self.controller.stop_and_cleanup()
            self.logger.info("仿真结束。")


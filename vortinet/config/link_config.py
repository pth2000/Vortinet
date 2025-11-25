"""
链路配置数据类

提供类型安全的链路配置，包括流量控制参数。
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrafficControlConfig:
    """流量控制配置（TC 参数）"""
    delay: Optional[str] = None  # e.g., "100ms"
    jitter: Optional[str] = None  # e.g., "10ms"
    loss: Optional[float] = None  # 丢包率百分比 0-100
    duplicate: Optional[float] = None  # 重复包百分比
    corrupt: Optional[float] = None  # 损坏包百分比
    reorder: Optional[float] = None  # 乱序百分比
    bandwidth: Optional[int] = None  # 带宽限制 (kbit/s)
    
    def validate(self) -> None:
        """验证 TC 参数的有效性"""
        if self.loss is not None and not (0 <= self.loss <= 100):
            raise ValueError(f"丢包率必须在 0-100 之间: {self.loss}")
        
        if self.duplicate is not None and not (0 <= self.duplicate <= 100):
            raise ValueError(f"重复率必须在 0-100 之间: {self.duplicate}")
        
        if self.bandwidth is not None and self.bandwidth <= 0:
            raise ValueError(f"带宽必须大于 0: {self.bandwidth}")
    
    def has_any_rule(self) -> bool:
        """检查是否设置了任何 TC 规则"""
        return any([
            self.delay, self.jitter, self.loss, 
            self.duplicate, self.corrupt, self.reorder, 
            self.bandwidth
        ])
    
    def to_tc_command_args(self) -> str:
        """生成 tc netem 命令参数"""
        args = []
        
        if self.delay:
            delay_str = f"delay {self.delay}"
            if self.jitter:
                delay_str += f" {self.jitter}"
            args.append(delay_str)
        
        if self.loss:
            args.append(f"loss {self.loss}%")
        
        if self.duplicate:
            args.append(f"duplicate {self.duplicate}%")
        
        if self.corrupt:
            args.append(f"corrupt {self.corrupt}%")
        
        if self.reorder:
            args.append(f"reorder {self.reorder}%")
        
        if self.bandwidth:
            args.append(f"rate {self.bandwidth}kbit")
        
        return " ".join(args)


@dataclass
class LinkConfig:
    """链路配置"""
    # 流量控制
    traffic_control: Optional[TrafficControlConfig] = None
    
    # 链路属性
    mtu: int = 1500
    enabled: bool = True
    
    def validate(self) -> None:
        """验证配置有效性"""
        if self.mtu <= 0:
            raise ValueError(f"MTU 必须大于 0: {self.mtu}")
        
        if self.traffic_control:
            self.traffic_control.validate()
    
    @classmethod
    def create_default(cls) -> "LinkConfig":
        """创建默认链路配置"""
        return cls()
    
    @classmethod
    def create_with_tc(
        cls,
        delay: Optional[str] = None,
        loss: Optional[float] = None,
        bandwidth: Optional[int] = None,
        **tc_kwargs
    ) -> "LinkConfig":
        """创建带流量控制的链路配置"""
        tc_config = TrafficControlConfig(
            delay=delay,
            loss=loss,
            bandwidth=bandwidth,
            **tc_kwargs
        )
        return cls(traffic_control=tc_config)

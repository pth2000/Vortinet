# OVS 交换机 + 流量控制演示

演示如何在 OVS 交换机拓扑中使用流量控制 (TC) 功能。

## 拓扑结构

```
H1 ---+
      |
H2 ---+--- SW1 (with TC)
      |
H3 ---+
```

## TC 配置

所有主机到交换机的连接共享相同的 TC 规则:
- **延迟**: 50ms (单向)
- **丢包率**: 2%
- **带宽限制**: 10 Mbps

### 重要说明

在 OVS 交换机场景中,多个主机连接到同一个交换机时会形成一个**交换链路** (switched link),所有连接共享相同的 TC 配置。这是正确的设计,因为:

1. 它们属于同一个广播域
2. 模拟真实交换机环境中的统一 QoS 策略
3. 简化配置和管理

如果需要不同的 TC 规则,可以:
- 使用多个交换机
- 使用 VLAN 隔离不同的流量
- 使用点对点链接 (Direct Veth)

## 运行示例

```bash
sudo -E .venv/bin/python examples/7.\ tc_with_ovs/tc_ovs_demo.py
```

## 验证 TC 规则

部署后,可以使用 CLI 工具验证 TC 规则:

```bash
# 查看拓扑
sudo -E .venv/bin/python vortinet_cli.py topology tc_ovs_demo

# 在 H1 中检查 TC 配置
sudo -E .venv/bin/python vortinet_cli.py exec tc_ovs_demo H1 "tc qdisc show dev eth0"

# 测试延迟 (从 H1 ping H2)
sudo -E .venv/bin/python vortinet_cli.py exec tc_ovs_demo H1 "ping -c 5 <H2_IP>"
```

## 预期结果

1. **RTT (往返延迟)**: 约 100ms (50ms 单向延迟 × 2)
2. **丢包率**: 约 2% (可能看到 ping 偶尔超时)
3. **带宽**: 限制在 ~10 Mbps

## 技术细节

- TC 规则应用在容器端接口 (`eth0`)
- OVS bridge 负责二层交换
- 延迟是单向的,RTT 包含往返延迟
- TC 使用 `netem` (Network Emulator) 实现

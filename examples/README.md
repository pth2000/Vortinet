# Vortinet 示例指南

本目录包含了一系列循序渐进的示例，旨在帮助用户从零开始掌握 Vortinet 的使用。

## 目录结构

示例按照复杂度递增的顺序排列：

### [01. 基础点对点 (Basic P2P)](01_basic_p2p/basic_p2p.py)
- **目标**: 了解最基本的拓扑构建。
- **内容**: 两个主机通过 veth pair 直接相连。
- **关键点**: `Topology`, `create_host_node`, `add_link`, `DeploymentController`。

### [02. OVS 交换机 (OVS Switch)](02_ovs_switch/ovs_switch.py)
- **目标**: 学习二层交换网络。
- **内容**: 多个主机连接到一个 Open vSwitch (OVS) 交换机。
- **关键点**: `create_ovs_switch`, 共享子网 (Access Links), 自动 IP 分配。

### [03. 流量控制 (Traffic Control)](03_traffic_control/traffic_control.py)
- **目标**: 模拟弱网环境。
- **内容**: 在链路中引入延迟 (delay)、丢包 (loss) 和抖动 (jitter)。
- **关键点**: `LinkConfig`, `tc` 参数配置。

### [04. 路由器与网关 (Router & Gateway)](04_router_gateway/router_gateway.py)
- **目标**: 学习三层路由网络。
- **内容**: 两个不同子网的主机通过路由器通信。
- **关键点**: `create_router_node`, `set_default_gateway`, 跨子网通信。

### [05. 混合复杂拓扑 (Complex Mixed)](05_complex_mixed/complex_mixed.py)
- **目标**: 综合应用。
- **内容**: 结合路由器、交换机，并演示手动 IP 预留。
- **关键点**: `reserve_ip`, 混合拓扑构建, 显式子网指定。

### [06. FRR OSPF 动态路由 (FRR OSPF)](06_frr_ospf/frr_ospf.py)
- **目标**: 学习动态路由协议。
- **内容**: 使用 FRR 运行 OSPF 协议，实现跨网段自动路由。
- **关键点**: `create_frr_router`, OSPF, 自动配置生成。

### [07. FRR BGP 动态路由 (FRR BGP)](07_frr_bgp/frr_bgp.py)
- **目标**: 学习 BGP 协议。
- **内容**: 两个自治系统 (AS) 之间的 BGP 互联。
- **关键点**: `create_frr_router`, BGP, AS Number。

### [08. 自定义服务 (Custom Service)](08_custom_service/custom_service.py)
- **目标**: 扩展节点功能。
- **内容**: 创建自定义的 Client/Server 服务节点。
- **关键点**: `NodeConfig`, `ContainerConfig`, 自定义 Dockerfile。

### [09. SDN 手动流表 (SDN Flow Table)](09_sdn_flow_table/sdn_flow_demo.py)
- **目标**: 学习 OpenFlow 手动控制。
- **内容**: 使用 `ovs-ofctl` 手动下发流表控制流量。
- **关键点**: `run_ovs_ofctl`, OpenFlow 规则, 丢弃/转发动作。

### [10. Ryu 控制器集成 (Ryu Controller)](10_ryu_controller/ryu_demo.py)
- **目标**: 集成外部 SDN 控制器。
- **内容**: 运行 Ryu 容器并控制 OVS 交换机。
- **关键点**: Ryu, 带内控制 (In-Band Control), 控制器连接。

## 运行方式

所有示例均需要 `root` 权限（因为涉及网络接口操作），建议在虚拟环境中运行。

```bash
# 示例：运行基础点对点示例
sudo -E python3 examples/01_basic_p2p/basic_p2p.py

# 示例：运行 OVS 交换机示例
sudo -E python3 examples/02_ovs_switch/ovs_switch.py
```

## 旧版示例

旧版本的示例代码已被归档至 `legacy/` 目录。

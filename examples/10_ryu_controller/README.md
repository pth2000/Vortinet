# 示例 10: Ryu 控制器集成

本示例演示如何将 Ryu SDN 控制器作为容器运行，并控制 OVS 交换机。

## 目录结构

- `ryu_demo.py`: 主程序，定义拓扑并启动仿真。
- `simple_switch_13.py`: Ryu 应用程序（L2 交换机逻辑）。

## 运行方法

```bash
sudo python3 ryu_demo.py
```

## 原理说明

1.  **Ryu 容器**: 使用 `vortinet_ryu` 镜像启动一个容器，运行 `ryu-manager`。
2.  **带内控制 (In-Band Control)**:
    -   Ryu 容器 (`c0`) 连接到 OVS 交换机 (`sw1`)。
    -   OVS 交换机配置为连接到 `c0` 的 IP 地址 (`10.0.0.3`)。
    -   为了让宿主机上的 OVS 进程能够访问容器网络，我们在宿主机的 OVS 网桥接口上配置了一个 IP 地址 (`10.0.0.254`)。
3.  **流表下发**:
    -   当主机 `h1` ping `h2` 时，第一个包触发 Packet-In 消息发送给 Ryu。
    -   Ryu 计算路径并下发流表 (Flow Mod)。
    -   后续数据包直接由 OVS 转发。
4.  **Fail Mode**:
    -   本示例中 OVS 默认使用 `standalone` 模式。这意味着如果 Ryu 未启动或连接断开，OVS 会回退为普通交换机。
    -   若要强制 OVS 仅受控制器控制（断连即断网），可在创建交换机时设置 `fail_mode="secure"`。

## 注意事项

-   首次运行会自动构建 `vortinet_ryu` 镜像，可能需要几分钟。
-   需要 root 权限运行。
-   **服务启动时序**: 由于容器启动和网络配置存在时序差，若需在容器内运行依赖网络的服务（如 Web Server），建议在 `deploy()` 完成后使用 `controller.exec_in_node(..., detach=True)` 手动启动。

# Windows 控制台 + WSL Ubuntu Compute 改造说明

更新时间：`2026-04-06`

## 背景

当前 seller 旧路线是把 `Windows + Docker Desktop` 直接当作 compute node。

这条路线的问题已经收敛到一个明确根因：

- `Docker Swarm manager` 只能稳定识别卖家主机的公网 IP
- 不能稳定把 seller compute node 识别成平台要求的卖家 `WireGuard IP`

这会导致：

- `NodeAddr`
- `advertise_addr`
- `data_path_addr`

无法稳定落到平台期望的 WireGuard 数据面路由上。

最终影响的是：

- `manager -> node`
- `gateway -> runtime`
- buyer shell / workspace sync

## 新方案

- `Windows`
  - 只保留控制台、安装器、日志、文件入口、Codex/MCP 宿主职责
- `WSL Ubuntu`
  - 成为 seller 正式 compute substrate
  - 运行 WireGuard compute peer
  - 运行 Docker Engine
  - 作为 Swarm worker
  - 执行 runtime image build / push

## 目标

让 seller compute node 对 Swarm 数据面暴露一个真正可路由、可预测、可长期交付的地址。

这个地址必须优先是：

- Ubuntu compute peer 的 WireGuard IP

而不是：

- Windows 主机公网 IP
- Docker Desktop 内部 NAT 地址

## 文档落点

seller 权威设计文档见：

- `/root/Pivot_network/seller-client/docs/windows-console-wsl-ubuntu-compute.md`

后端配套实现说明见：

- `/root/Pivot_network/Backend/docs/windows-wsl-ubuntu-compute-implementation.md`

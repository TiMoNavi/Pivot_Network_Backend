# Seller Agent V2: Windows Console + WSL Ubuntu Compute

更新时间：`2026-04-06`

## 1. 背景与失败原因

这次 seller 架构改造不是“体验优化”，而是一次必须完成的网络与节点身份修正。

旧路线是：

- `Windows 主机`
- `Docker Desktop / Windows 可见 docker CLI`
- seller 直接把 Windows 机器当成 compute node

这条路线的核心问题不是 UI，也不是脚本不够完善，而是 **Swarm 节点数据面地址无法稳定收敛到平台要求的 WireGuard 地址**。

当前已经确认的失败机制是：

- `Docker Swarm manager` 只会稳定识别卖家电脑的公网 IP
- 它不会稳定把 seller compute node 识别成我们期望的卖家 `WireGuard IP`
- 这会导致 seller node 的 `NodeAddr`、`advertise_addr`、`data_path_addr` 落不到统一的 WireGuard 路由上
- 最终影响：
  - `manager -> node` 调度与回程链路不稳定
  - `gateway -> runtime` 跨节点访问不稳定
  - buyer shell / workspace sync 容易卡住或超时

平台真正需要的不是“卖家电脑对公网有一个地址”，而是：

> seller compute node 在平台数据面上暴露一个真实可路由、可预测、可长期交付的 Linux 网络地址。

因此 seller compute 必须从 Windows 宿主迁到 `WSL Ubuntu`，让下面四件事运行在同一 Linux 网络栈里：

- `WireGuard peer`
- `Docker Engine`
- `Swarm worker`
- runtime build / run

这样才能保证：

- `advertise_addr` 与 `data_path_addr` 使用 Ubuntu 的 WireGuard IP
- Swarm manager、gateway、runtime、buyer runtime client 都围绕同一个 seller 数据面地址工作

## 2. 新架构与角色边界

### 2.1 正式架构

```text
Seller User
    |
    v
Windows Seller Console
    |
    +--> Public HTTPS --> Backend --> Adapter
    |
    +--> WSL Ubuntu Compute
              |
              +--> WireGuard compute peer
              +--> Docker Engine
              +--> Swarm worker
              +--> runtime image build / push
```

### 2.2 角色边界

#### `Windows Host`

负责：

- UI / 本地网页控制台
- 启动脚本
- 卖家登录
- Windows 环境安装与检查
- 文件选择
- 日志展示
- Codex / MCP 宿主
- 调起 Ubuntu bootstrap / sync / join / build 流程

不负责：

- 作为正式 seller compute node
- 直接运行 seller runtime
- 直接以 Windows Docker 参与 `build / join / push`

#### `WSL Ubuntu Compute`

负责：

- seller compute 的正式运行时环境
- `wireguard-tools`
- 原生 `docker.io` / `dockerd`
- Swarm worker join
- seller runtime image `build / tag / push`
- runtime 容器实际运行

#### `Backend`

负责：

- 鉴权、seller onboarding、会话态、策略下发
- `windows_host_bootstrap` 与 `ubuntu_compute_bootstrap`
- host / ubuntu 双环境报告与审计
- seller / buyer 业务状态机

不负责：

- SSH 到 seller 节点
- 直接操作 seller Docker Socket
- 直接修改 seller 本地 WireGuard 配置文件

#### `Adapter`

负责：

- 真实执行 Swarm / WireGuard 基础设施动作
- 节点认领
- runtime bundle / gateway / wireguard 资源编排
- runtime contract 校验

## 3. Seller Onboarding 全链路

卖家的正式链路固定为：

1. Windows 启动 seller console。
2. Windows 执行 seller host 安装/检查流程。
3. seller 登录 `Backend`。
4. seller 创建 onboarding session。
5. seller console 拉取：
   - `bootstrap-config`
   - `ubuntu-bootstrap`
6. Windows 把会话级 Codex/MCP 配置落到本地工作目录。
7. Windows 调起 `WSL Ubuntu` bootstrap。
8. Ubuntu 安装并准备：
   - `docker.io`
   - `wireguard-tools`
   - `/opt/pivot/compute`
   - `/opt/pivot/workspace`
   - `/opt/pivot/logs`
9. Windows 把 build context 同步到 Ubuntu。
10. Ubuntu 以 WireGuard IP 执行 `docker swarm join`。
11. seller console 向 `Backend` 回写：
   - `host-env-report`
   - `ubuntu-env-report`
   - `compute-ready`
12. seller 发起 `claim node`。
13. Ubuntu 执行 `docker build/tag/push`。
14. Windows 发起 `image report`。

## 4. Bootstrap / Policy / Runtime Contract

### 4.1 Seller Onboarding Policy

seller onboarding policy 的正式含义是“平台稳定约束”，而不是某次执行的临时脚本结果。

必须固定包含：

- `compute_substrate = "wsl_ubuntu"`
- `compute_host_type = "windows_wsl_ubuntu"`
- `compute_network_mode = "wireguard"`
- `compute_runtime = "docker_engine"`
- `allowed_runtime_base_image`
- `runtime_contract_version`
- `allowed_registry_host`
- `allowed_registry_namespace`

### 4.2 Bootstrap 拆分

#### `windows_host_bootstrap`

只包含 Windows 控制台需要的材料：

- seller console 启动入口
- Windows 工作目录
- 会话级 Codex 配置
- 会话级 Codex auth
- MCP server 配置

#### `ubuntu_compute_bootstrap`

只包含 Ubuntu compute 执行材料：

- `ubuntu_distribution_name`
- `required_packages`
- `docker_engine_install_mode`
- `workspace_root`
- `runtime_root`
- `logs_root`
- `wireguard_compute_peer`
- `swarm_join`
- `bootstrap_script_bash`
- `bootstrap_script_powershell`

### 4.3 Runtime Contract V2

seller runtime image 的正式契约升级为 `platform runtime contract v2`。

必须满足：

- 基于平台 managed base image `FROM`
- 保留以下标签：
  - `io.pivot.runtime.base_image`
  - `io.pivot.runtime.contract_version=v2`
  - `io.pivot.runtime.seller_build_host=wsl_ubuntu`
  - `io.pivot.runtime.buyer_agent=v1`
- 必须提供以下能力：
  - `/health`
  - `/shell/`
  - `/api/exec`
  - `/api/workspace/upload`
  - `/api/workspace/extract`
  - `/api/workspace/status`

旧 contract 镜像策略：

- seller 可见
- buyer 不可售
- buyer catalog 不收录

## 5. Windows 安装与检查流程

Windows seller host 的正式安装/检查脚本固定放在：

- `/root/Pivot_network/environment_check/windows_seller_host_install_and_check.ps1`

配套说明：

- `/root/Pivot_network/environment_check/README.md`

这个流程脚本只负责 **Windows seller host 正式依赖**，不再把 `Docker Desktop` 当成 seller 正式依赖。

### 5.1 阻塞项

- 管理员权限
- PowerShell
- Python 3.11+
- WSL2
- `Ubuntu` 发行版存在
- `codex` CLI
- `Backend` HTTPS 健康检查可达

### 5.2 非阻塞支持项

- Windows WireGuard 客户端
- OpenSSH client
- OpenSSH server

### 5.3 输出模型

脚本必须输出结构化结果：

- `title`
- `category`
- `status`
- `blocking`
- `detail`
- `hint`

主结果按域分开：

- `windows_host_checks`
- `platform_checks`
- `assistant_checks`
- `support_checks`

## 6. Ubuntu Bootstrap / Join / Claim / Build / Report

### 6.1 Ubuntu Bootstrap

Ubuntu bootstrap 的目标不是“让 WSL 有 docker 命令”，而是让 Ubuntu 成为 seller 正式 compute substrate。

必须完成：

- 安装 `docker.io`
- 安装 `wireguard-tools`
- 创建固定目录
- 应用 compute peer 配置
- 启动原生 `dockerd`

### 6.2 Swarm Join

join 的正式要求是：

- 在 Ubuntu 中执行
- 使用 Ubuntu WireGuard IP 作为 `advertise_addr`
- 使用 Ubuntu WireGuard IP 作为 `data_path_addr`

验收标准是：

- `docker info` 中节点使用的平台数据面地址等于预期的 Ubuntu WireGuard IP
- manager 看到该节点为 `Ready`

### 6.3 Claim Node

claim 的输入必须绑定：

- `onboarding_session_id`
- `compute_node_id`
- `requested_accelerator`
- seller 在 Ubuntu 中 join 出来的真实 node ref

### 6.4 Build / Push / Report

正式路径固定为：

- Windows 选择本地目录
- Windows 同步 build context 到 Ubuntu
- Ubuntu 执行 `docker build`
- Ubuntu 执行 `docker push`
- Windows 调用 `Backend` 执行 `image report`

Windows 本机 Docker 不再是 seller 正式 build host。

## 7. 错误模型

seller 侧错误必须按层展示，而不是只吐原始 stdout/stderr。

正式分层：

- `windows_host`
- `ubuntu_compute`
- `swarm`
- `platform`
- `runtime_contract`

前端展示规则：

- 阻塞项单独高亮
- Windows 问题、Ubuntu 问题、平台问题分开展示
- 原始 stdout/stderr 只放 debug 区

## 8. 旧路径删除清单

下列路径不再是 seller 官方交付路径，后续要逐步删除，不允许继续出现在正式文档和正式操作说明中：

- `bootstrap/start_seller_client.ps1`
- `/local-api/join/run`
- `seller_client_app/mcp_server.py` 中基于本机 `docker` 的 `run_swarm_join`
- `seller_client_app/mcp_server.py` 中基于本机 `docker` 的 `build_image`
- `seller_client_app/mcp_server.py` 中基于本机 `docker` 的 `push_image`
- `seller_client_app/docker_workbench.py`

需要重写的旧逻辑：

- `seller_client_app/env_scan.py`
- `bootstrap/repair_connectivity.ps1`

需要从文档中彻底删除的旧认知：

- Windows 主机是正式 seller compute node
- Docker Desktop 是 seller 正式依赖
- Windows 侧直接 `join / build / push` 是可接受正式路径

## 9. 当前仓库状态说明

截至这次文档改造，仓库里仍存在少量过渡实现与兼容代码。

它们只能被视为：

- 过渡状态
- 待清理实现
- 非官方正式路径

seller 官方设计与交付路径以本文为准。

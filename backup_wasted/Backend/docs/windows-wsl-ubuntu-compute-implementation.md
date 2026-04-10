# Windows 控制台 + WSL Ubuntu Compute 配套实施说明

更新时间：`2026-04-06`

## 1. 为什么这是强制改造

seller compute 从 Windows 宿主迁到 `WSL Ubuntu`，不是为了“更 Linux 化”，而是因为当前 Swarm 数据面地址无法在旧路线上稳定成立。

已经确认的约束是：

- `Docker Swarm manager` 只稳定识别卖家主机的公网 IP
- 不稳定识别 seller 期望暴露给平台的数据面 `WireGuard IP`

这会让以下信息不稳定：

- `NodeAddr`
- `advertise_addr`
- `data_path_addr`

从而影响：

- manager 到 seller node 的稳定回程
- gateway 到 runtime 的跨节点访问
- buyer shell / workspace sync

因此 seller compute 必须迁到 `WSL Ubuntu`，让：

- `WireGuard peer`
- `Docker Engine`
- `Swarm worker`
- runtime build / run

都在同一 Linux 网络栈中工作。

## 2. Backend 需要明确的边界

`Backend` 的职责固定为：

- seller / buyer 业务模型
- seller onboarding session
- seller compute policy
- bootstrap config 下发
- host / ubuntu 双环境报告
- seller / buyer runtime 相关元数据与审计

`Backend` 不负责：

- SSH 到 seller 节点
- 直接改 seller Docker Socket
- 直接写 seller 本地 WireGuard 配置

## 3. Seller Onboarding 设计

seller onboarding 现在固定为双阶段模型：

- `windows_host_bootstrap`
- `ubuntu_compute_bootstrap`

### 3.1 `windows_host_bootstrap`

用于 seller console：

- Windows 工作目录
- seller console 启动入口
- 会话级 Codex config
- 会话级 Codex auth
- MCP server 启动配置

### 3.2 `ubuntu_compute_bootstrap`

用于 WSL Ubuntu compute：

- `distribution_name`
- `required_packages`
- `docker_engine_install_mode`
- `workspace_root`
- `runtime_root`
- `logs_root`
- `wireguard_compute_peer`
- `swarm_join`
- `bootstrap_script_bash`
- `bootstrap_script_powershell`

### 3.3 Seller Onboarding Policy

policy 需要稳定暴露：

- `compute_substrate = "wsl_ubuntu"`
- `compute_host_type = "windows_wsl_ubuntu"`
- `compute_network_mode = "wireguard"`
- `compute_runtime = "docker_engine"`

以及 seller build 约束：

- `allowed_runtime_base_image`
- `runtime_contract_version`
- `allowed_registry_host`
- `allowed_registry_namespace`

## 4. 当前后端接口边界

seller 侧当前正式接口应围绕以下能力组织：

- `GET /api/v1/seller/onboarding/sessions/{id}/bootstrap-config`
- `GET /api/v1/seller/onboarding/sessions/{id}/ubuntu-bootstrap`
- `POST /api/v1/seller/onboarding/sessions/{id}/host-env-report`
- `POST /api/v1/seller/onboarding/sessions/{id}/ubuntu-env-report`
- `POST /api/v1/seller/onboarding/sessions/{id}/compute-ready`

seller node 与镜像相关接口保持：

- `POST /api/v1/seller/nodes/register`
- `POST /api/v1/seller/nodes/{node_id}/claim`
- `POST /api/v1/seller/images/report`

buyer runtime client 继续保持独立，不依赖 seller 的 Windows 主机。

## 5. Runtime Contract V2

seller runtime image 的正式语义是“在 Ubuntu compute 中构建，并供 buyer runtime client 使用”。

必须固定要求：

- 标签：
  - `io.pivot.runtime.base_image`
  - `io.pivot.runtime.contract_version=v2`
  - `io.pivot.runtime.seller_build_host=wsl_ubuntu`
  - `io.pivot.runtime.buyer_agent=v1`
- 能力：
  - `/health`
  - `/shell/`
  - `/api/exec`
  - `/api/workspace/upload`
  - `/api/workspace/extract`
  - `/api/workspace/status`

历史旧镜像策略：

- seller 可见
- buyer 不可售

## 6. Client 边界

### 6.1 Seller Client

`Windows Host` 负责：

- 登录
- 启动 seller console
- Windows 环境检查
- 获取 bootstrap
- 文件同步
- 查看 Ubuntu compute 状态
- claim / report
- 展示结构化错误

`WSL Ubuntu Compute` 负责：

- `wireguard-tools`
- 原生 `docker.io`
- Swarm join
- runtime image `build / tag / push`

### 6.2 Buyer Client

buyer-client 继续保持：

- Windows 本地控制台
- 公网 HTTPS 控制面
- 本机 WireGuard
- shell / workspace sync

buyer 不需要 Ubuntu compute。

## 7. 文档与实现清理方向

seller 正式路径不再包含：

- Windows Docker Desktop 直接作为 compute
- Windows 本地 docker 直接 join Swarm
- Windows 本地 docker 直接 build / push runtime image

仓库中仍然存在的旧兼容代码，只能视为：

- 过渡实现
- 待删除路径

seller 权威设计以：

- `/root/Pivot_network/seller-client/docs/windows-console-wsl-ubuntu-compute.md`

为准。

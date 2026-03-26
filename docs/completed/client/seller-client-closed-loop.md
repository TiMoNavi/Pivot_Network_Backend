# 卖家客户端完成态

## 结论

截至 `2026-03-26`，卖家客户端这条线已经完成从本地安装、平台接入、WireGuard、Swarm 到实际承载任务的闭环。
这个结论不是基于单元测试，而是基于真实机器、真实腾讯云 manager、真实 `wg0`、真实 Docker Swarm 的联调结果。

## 这条线最终做成了什么

卖家本地现在具备：

- 一次性安装器
- 本地 seller-Agent
- 本地 seller 网页控制面
- 平台登录、节点令牌申请、节点注册、节点心跳
- CodeX runtime bootstrap 拉取
- `wg-seller` profile 生成与本地激活
- Docker registry trust 配置
- Docker Swarm worker 自动加入确认
- 镜像推送与平台登记

对应关键文件：

- `seller_client/install_windows.ps1`
- `seller_client/installer.py`
- `seller_client/windows_elevation.py`
- `seller_client/windows_elevated_helper.py`
- `seller_client/agent_mcp.py`
- `seller_client/agent_server.py`
- `seller_client/web/index.html`

## 从开始制作以来做过的主要修改

### 1. 安装器与本地状态目录

补齐了 Windows 安装器骨架，负责：

- 创建本地状态目录
- 检测 Docker / Python / Codex CLI / WireGuard
- 安装 MCP 入口
- 准备 Windows WireGuard 提权 helper

同时修复了两个关键问题：

- `install_windows.ps1` 的 `param(...)` 位置错误
- `~/.codex/config.toml` 中 Windows 路径直接写入 TOML 双引号字符串的问题

现在 installer 会把 Python 路径按合法 TOML 形式写入 `config.toml`，不再破坏 Codex 配置加载。

### 2. seller-Agent 本地能力

`seller_client/agent_mcp.py` 逐步补齐了以下能力：

- 本地环境配置
- 卖家注册 / 登录
- 节点注册令牌申请
- 节点注册与心跳
- CodeX runtime bootstrap 拉取
- seller WireGuard keypair 与 profile 落盘
- 向平台请求 seller WireGuard bootstrap
- `wg-seller` 本地激活 / 断开
- Docker Swarm 状态检查
- 确保加入平台 Swarm
- registry trust 配置
- 镜像推送与平台汇报

### 3. seller 本地网页控制面

`seller_client/agent_server.py` 和 `seller_client/web/index.html` 由实验页收敛成 seller 控制台。

页面职责被明确限制为：

- 只与本地 seller-Agent 通信
- 展示 readiness、阶段状态、平台回显、本地动作日志
- 不直接操作 Docker、WireGuard、远端主机

页面当前支持：

- installer dry-run / apply 结果展示
- 卖家意图解释
- onboarding 触发
- CodeX runtime 拉取
- WireGuard bootstrap
- Swarm 状态与远端 overview
- registry trust
- 镜像 push/report

### 4. Windows WireGuard 产品化

这条线一开始被 Windows 权限拦住。
最后落地为：

- 一次性管理员安装 `PivotSellerWireGuardElevated`
- 之后普通用户运行 seller 网页 / seller-Agent
- 运行期由 helper task 代替普通进程执行 `wireguard.exe /installtunnelservice`

这意味着日常 seller 使用不再要求每次手动管理员运行。

## 真实验证过什么

### seller fresh 接入

做过一轮 fresh seller `0 -> 1` 闭环，结果成功。

真实验证包含：

- fresh backend
- fresh seller state dir
- fresh seller 账号
- fresh seller 节点注册
- fresh `wg-seller`
- fresh Swarm worker 验证

关键结果：

- `wg-seller` 地址为 `10.66.66.10/32`
- `ping 10.66.66.1` 成功
- 本机 `docker-desktop` 真实加入 `81.70.52.75:2377`
- 远端 manager 能把 smoke service 调度到本机 worker

### 卖家闭环定义

按项目当前定义：

- 卖家从零开始接入
- 平台识别为可用节点
- 节点位于 WireGuard 内网
- 节点位于 Swarm 中
- 节点能实际承载任务

这套标准已经满足，因此“卖家闭环成功”已被确认。

## 当前边界

卖家客户端完成的，是“接入闭环”和“可承载 runtime”闭环，不是完整交易产品。

当前尚未在卖家客户端侧闭环的内容：

- GPU 能力自动识别与上报
- Portainer/UI 级长期运维入口
- 更强的流式日志与实时任务事件
- 自动化安装第三方依赖

## 当前推荐理解

卖家客户端现在已经不是“脚本集合”，而是：

- 一个本地安装器
- 一个本地 agent
- 一个本地网页控制面

它已经足够支撑平台第一阶段的 seller onboarding 和 seller node runtime 承载。

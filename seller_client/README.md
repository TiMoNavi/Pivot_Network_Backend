# Seller Client MCP Prototype

这是当前卖家节点客户端的本地 `MCP` 原型。

目标不是立即提供完整 GUI，而是先把卖家端最关键的本地 Agent 能力做实：

- Agent 配置本地环境
- Agent 准备和连接服务器侧 `WireGuard`
- Agent 检查、拉起和使用本机 Docker
- Agent 测量本机和容器状态
- Agent 构建并上传 Docker 镜像到服务器 registry
- Agent 管理已上传到服务器 registry 的镜像
- Agent 辅助节点加入和离开 Swarm

## 当前工具

- `ping`
- `host_summary`
- `environment_check`
- `configure_environment`
- `register_seller_account`
- `login_seller_account`
- `issue_node_registration_token`
- `register_node_with_platform`
- `send_node_heartbeat`
- `report_image_to_platform`
- `get_client_config`
- `fetch_codex_runtime_bootstrap`
- `prepare_wireguard_profile`
- `generate_wireguard_keypair`
- `request_wireguard_bootstrap`
- `bootstrap_wireguard_from_platform`
- `wireguard_summary`
- `connect_server_vpn`
- `disconnect_server_vpn`
- `docker_summary`
- `ensure_docker_engine`
- `join_swarm_manager`
- `leave_swarm`
- `swarm_summary`
- `list_docker_images`
- `list_docker_containers`
- `create_docker_container`
- `inspect_container`
- `measure_container`
- `build_image`
- `tag_image_for_server`
- `push_image`
- `push_image_to_server`
- `probe_registry`
- `list_uploaded_images`
- `list_uploaded_image_tags`
- `delete_uploaded_image`
- `explain_seller_intent`
- `onboard_seller_from_intent`

## 运行方式

在仓库根目录执行：

```powershell
python seller_client\agent_mcp.py
```

当前默认使用 `stdio` 传输。

本地网页控制面可直接运行：

```powershell
python seller_client\agent_server.py
```

然后打开：

```text
http://127.0.0.1:3847
```

当前本地网页已经具备：

- 本地 dashboard / readiness 检查
- 卖家自然语言意图预览
- 安装器 dry-run 入口
- 后端 CodeX runtime 拉取入口
- WireGuard profile bootstrap 入口
- 卖家 onboarding 触发入口
- 本地动作日志
- registry 信任配置入口
- 镜像推送与平台登记入口
- 平台节点 / 镜像回显

当前 WireGuard onboarding 已推进到：

- seller-Agent 本地生成 WireGuard keypair
- seller-Agent 从后端获取 bootstrap profile
- 后端在启用 SSH 时自动把 peer 写入服务器 `wg0`
- seller-Agent 写本地 profile
- seller-Agent 在条件满足时尝试拉起本地 WireGuard

Windows 当前真实边界：

- 如果本地 seller-Agent 不是管理员权限，`wireguard.exe /installtunnelservice` 会被拒绝
- 当前已补出 `PivotSellerWireGuardElevated` scheduled-task helper 路径
- 需要先执行一次：

```powershell
powershell -ExecutionPolicy Bypass -File "seller_client\install_windows.ps1" -Apply
```

这样安装器会请求 UAC，并注册后续可复用的受权 helper task

## 当前边界

这还不是完整卖家客户端成品。

当前已经覆盖的是：

- 本地配置与状态文件
- 安装器骨架
- CodeX MCP 挂载骨架
- WireGuard 配置文件生成与启停入口
- 平台后端注册 / 登录 / 节点令牌 / 节点注册 / 心跳 / 镜像登记入口
- Docker 检查、启动、镜像和容器操作
- Swarm join / leave 入口
- 服务器 registry 查询和删除接口

## 安装器与界面

- Windows 安装器骨架：`seller_client/install_windows.ps1`
- Linux 安装器骨架：`seller_client/install_linux.sh`
- 安装器逻辑：`seller_client/installer.py`
- 本地 Web 控制面：`seller_client/agent_server.py` + `seller_client/web/index.html`
- 最小 GUI 壳子：`seller_client/gui_app.py`

当前还没有的是：

- 安装器真正自动化
- 自动节点注册协议
- 自动心跳与任务回传
- 后端下发 CodeX API key
- WireGuard 真正自动接入
- 一键式 Windows / Linux 全自动环境安装

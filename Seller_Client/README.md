# Pivot Seller Client

当前 `Seller_Client/` 是卖家本地客户端的**正式入口目录**。

如果你是第一次接触项目，建议先读：

1. `/root/Pivot_network/docs/tutorials/seller-buyer-e2e-guide-cn.md`
2. `/root/Pivot_network/Seller_Client/docs/current-seller-onboarding-flow-cn.md`

这份 README 只解决一件事：

- 新人如果要复现 seller 客户端，应该先跑什么、再跑什么、成功标准是什么

## 1. 卖家端当前正式入口

当前 seller 端 Windows 正式入口只有两个：

- 环境检查 / 安装：
  - `bootstrap/windows/install_and_check_seller_client.ps1`
- 打开本地页面：
  - `bootstrap/windows/start_seller_client.ps1`

当前 seller 页面默认本地地址：

- `http://127.0.0.1:8901/`

## 2. 新人最短操作顺序

### 第一步：先做环境检查

运行：

```powershell
powershell -ExecutionPolicy Bypass -File ".\bootstrap\windows\install_and_check_seller_client.ps1"
```

这一步会做：

- Python / `.venv` 准备
- 本地 seller client 依赖安装
- `Codex` 模板路径检查
- WSL / Docker / WireGuard / backend 连通性摘要检查
- 必要的半自动修复

如果你只是想看它会检查什么，不真正执行修复，可以先 dry run：

```powershell
powershell -ExecutionPolicy Bypass -File ".\bootstrap\windows\install_and_check_seller_client.ps1" -DryRun
```

### 第二步：做网络 / Overlay 检查

运行：

```powershell
powershell -ExecutionPolicy Bypass -File ".\bootstrap\windows\check_windows_overlay_runtime.ps1"
```

这一步主要看：

- 当前机器自己的 `wg-seller` / WireGuard 状态
- manager WireGuard 地址 `10.66.66.1` 的关键端口可达性
- 本地 seller 页面端口是否监听
- Docker Desktop / overlay 相关状态

### 第三步：打开 seller 页面

运行：

```powershell
powershell -ExecutionPolicy Bypass -File ".\bootstrap\windows\start_seller_client.ps1"
```

正常情况下它会打开：

- `http://127.0.0.1:8901/`

如果浏览器没自动弹出，可以手工打开这个地址。

## 3. 页面里怎么操作

### 3.1 登录 / 注册

先在“接入会话”区域：

- 登录 seller 账号
- 或注册 seller 账号

### 3.2 创建 fresh onboarding session

在同一区域填写：

- `Requested Accelerator`
- `Requested Compute Node ID`
- `Requested Offer Tier`
- `Expected WireGuard IP`

然后点击：

- `创建 onboarding session`

### 3.3 用 AI 助手走正式接入主线

当前推荐的新手入口不是手敲所有 probe，而是在“AI 助手”里直接输入：

```text
帮我接入
```

或者：

```text
帮我加入 swarm，并以 manager task execution 作为完成标准
```

当前 seller 自然语言主线默认走 MCP 编排，不再推荐旧的裸 workflow。

## 4. 成功标准怎么判断

### 4.1 不要把这些当最终成功

以下都**不能单独算成功**：

- 本地 `docker info` 显示 `LocalNodeState=active`
- WireGuard 本地能通
- 本地页面里看到 join 命令跑完了

### 4.2 当前唯一正式成功标准

当前 seller 接入成功，必须同时满足：

- manager 侧确认这台 worker 是 `Ready`
- manager 侧确认这台 worker 上存在可执行或已运行中的 swarm task

也就是说，最终标准是 **manager 真相**，不是本地自报。

## 5. seller 成功后平台会发生什么

一旦 backend 把这台 seller 节点写成 `verified`，后续会自动进入：

1. capability assessment
2. real offer commercialization

也就是说，seller 当前不是只负责“接入成功”，而是会继续触发平台上架。

## 6. 常见问题

### 6.1 如果需要从零重来

当前正式清理入口是：

- `cleanup_join_state`
- `stop_local_service_and_cleanup`

推荐顺序：

1. 清理本地 join 状态
2. 不复用旧 onboarding session
3. 创建 fresh session
4. 再重新执行 AI 助手接入

### 6.2 如果想看带截图版本

请直接看：

- `/root/Pivot_network/docs/tutorials/seller-buyer-e2e-guide-cn.md`

### 6.3 如果想看 seller 当前权威流程说明

请看：

- `/root/Pivot_network/Seller_Client/docs/current-seller-onboarding-flow-cn.md`

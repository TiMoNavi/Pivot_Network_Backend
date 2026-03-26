# 平台后端完成态

## 结论

截至 `2026-03-26`，平台后端已经从最初的认证与节点登记骨架，扩展成支撑 seller 接入、buyer runtime session、WireGuard 凭证、Swarm 信息获取与租期回收的中枢。

它已经能够支撑当前卖家闭环和买家第一阶段闭环。

## 这条线最终做成了什么

平台后端当前负责：

- 用户注册 / 登录
- seller 节点令牌发放
- 节点注册、心跳、镜像登记、活动日志
- CodeX runtime bootstrap
- seller WireGuard bootstrap
- 远端 Swarm overview 与 worker join token
- buyer runtime session 创建、兑换、状态查询、结果上报、停止、续期
- buyer session 专属 WireGuard bootstrap
- 过期 session 自动清理
- 到期时自动撤掉 buyer WireGuard peer

对应关键文件：

- `backend/app/api/routes/platform.py`
- `backend/app/api/routes/buyer.py`
- `backend/app/services/runtime_bootstrap.py`
- `backend/app/services/runtime_sessions.py`
- `backend/app/services/swarm_manager.py`
- `backend/app/services/wireguard_server.py`
- `backend/app/core/config.py`
- `backend/app/main.py`
- `backend/app/models/platform.py`
- `backend/app/schemas/platform.py`

## 从开始制作以来做过的主要修改

### 1. seller onboarding 相关接口

补齐了 seller 侧需要的基础接口：

- 节点注册令牌
- 节点注册
- 节点心跳
- 镜像登记
- seller overview
- activity feed

在此基础上继续补齐：

- `GET /api/v1/platform/runtime/codex`
- `POST /api/v1/platform/nodes/wireguard/bootstrap`
- `GET /api/v1/platform/swarm/worker-join-token`
- `GET /api/v1/platform/swarm/overview`

### 2. CodeX runtime 由后端统一保管

真实 OpenAI key 只保留在后端，不下放到 seller 网页或 buyer 网页。

后端支持从：

- `OPENAI_API_KEY`
- `backend/.codex/auth.json`

读取 runtime 认证，然后再通过 runtime bootstrap 接口下发给 seller-Agent。

### 3. seller WireGuard bootstrap

后端负责：

- 根据 `wg0` 这套网段为 seller 分配地址
- 生成 seller 需要的 WireGuard bootstrap 参数
- 在启用 SSH 时自动把 seller peer 写入服务器 `wg0`

这使 seller 本地不再需要手工维护 peer 信息。

### 4. buyer runtime session 模型

后端新增 `RuntimeAccessSession` 并逐步补成以下能力：

- `create`
- `redeem`
- `status`
- `report`
- `stop`
- `renew`

后续又为 session 增加：

- `network_mode`
- `buyer_wireguard_public_key`
- `buyer_wireguard_client_address`
- `seller_wireguard_target`

这使 buyer session 从“临时任务”提升为“有租期、有网络凭证的运行时会话”。

### 5. session 到期自动回收

后端 `main.py` 增加后台 reaper，定期扫描过期 session。

到期时当前会做：

- 尝试删除 runtime service
- 标记 session 为 `expired`
- 如果该 session 有 buyer WireGuard peer，则自动撤销该 peer

### 6. buyer WireGuard bootstrap

新增：

- `POST /api/v1/buyer/runtime-sessions/{session_id}/wireguard/bootstrap`

该接口负责：

- 为 buyer session 下发专属 WireGuard 凭证
- 返回 buyer 地址
- 返回 seller 在 `wg0` 中的目标地址
- 将该 buyer peer 写入服务器 `wg0`

### 7. stale peer 自动替换

在真实验证 buyer 直连 seller 时，发现一个关键问题：

- 服务器 `wg0` 上同一 `AllowedIPs` 可能绑着 stale seller peer

之后后端补成：

- `apply_server_peer()` 在写新 peer 前，会自动移除同一 `AllowedIPs` 的旧 peer

这意味着 seller 重新 bootstrap 新 key 时，不需要再手工修 `wg0`。

## 真实验证过什么

### 1. seller backend 链路

真实确认过：

- 节点注册
- 心跳
- CodeX runtime bootstrap
- seller WireGuard bootstrap
- Swarm overview
- worker join token

### 2. buyer backend 链路

真实确认过：

- runtime session 创建
- Swarm service 下发
- 结果回传
- session stop
- session renew
- buyer WireGuard bootstrap
- 到期回收 buyer peer

### 3. 测试覆盖

当前后端测试已回归通过：

- `pytest backend/tests -q`

最新结果为：

- `20 passed`

## 当前边界

平台后端当前还不是完整交易后端。

尚未完成的部分：

- 真正的买卖撮合和订单模型
- 计费和支付
- GPU 能力与 GPU 调度
- 持久化的日志 / artifact 存储
- buyer 真终端 websocket/gateway
- 生产级数据库与队列部署

## 当前推荐理解

平台后端现在已经是：

- seller 接入中枢
- buyer runtime session 中枢
- WireGuard 凭证中枢
- 远端 Swarm 读写与观察中枢

它已经足以支撑当前阶段的 seller / buyer 闭环验证。

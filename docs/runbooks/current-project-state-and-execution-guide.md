# Pivot Network 当前项目状态与执行总览

更新时间：`2026-04-11`

## 1. 这份文档解决什么问题

这份文档是当前项目的一号入口。

理想状态下，一个第一次进入 repo 的人，先读这份文档，就应该能回答下面这些问题：

- 项目的根本目标是什么
- 当前全局架构是什么
- `Docker Swarm` 现在是什么情况
- `Docker_Swarm_Adapter` 现在是什么情况
- backend 现在有哪些接口和能力
- seller、platform、buyer 各自做到哪里了
- 当前到底处于哪个阶段
- 当前阶段要改哪里、不能改哪里
- Windows 远控入口怎么用
- 每个阶段的成功标准和能力边界是什么

## 2. 项目的根本目标

当前项目的根本目标不是“证明某台机器能 join swarm”，也不是“做一个只会下单的页面”。

当前项目的完整产品目标是：

1. 卖家可以把自己的真实节点接入平台
2. 平台可以把已验收节点自动商品化成真实 `Offer`
3. 买家可以在平台上下单并拿到会话准入凭证
4. 买家可以在本地 `Buyer_Client` 里建立一个 `RuntimeSession`
5. 买家最终既能：
   - 访问 seller runtime 容器的 shell
   - 又能通过 `CodeX` 自然语言描述，把 task 传递并完成

一句话总结：

- seller 卖的是可售算力节点
- buyer 买的是云主机会话，不是 seller 裸 IP

## 3. 当前阶段定位

当前项目阶段应固定理解为：

- `phase3` 末期
  - 核心是验证 seller 节点商品化与平台上架逻辑
- `phase4`
  - 核心是买家客户端实施
- `phase5`
  - 核心是卖家、平台、买家联调闭环

当前不再是：

- seller onboarding 早期探索阶段
- 只有 `phase2B` Windows 接入纠偏阶段

## 4. 当前全局架构

当前全局架构不是一条链，而是两条相连的链：

### 4.1 seller 接入与商品化链

- `Seller_Client -> Plantform_Backend -> Docker_Swarm_Adapter -> Docker Swarm`

### 4.2 buyer 交易与会话链

- `Buyer_Client -> Plantform_Backend -> Docker_Swarm_Adapter / WireGuard / Managed Runtime`

当前 seller 链已经有正式代码主线。
当前 buyer 链已经有正式设计主线，但代码还没全部落地。

## 5. Docker Swarm 现在是什么情况

当前 `Docker_Swarm/` 是项目唯一正式基础设施目录。

当前它承担三件事：

1. seller 节点接入所在的 Swarm 集群
2. `Docker_Swarm_Adapter` 的运行环境
3. 未来 buyer `RuntimeSession` 的 runtime bundle 承载环境

### 当前权威地址

- swarm manager 公网地址：`81.70.52.75`
- swarm manager WireGuard / control-plane 地址：`10.66.66.1`
- 当前 seller join target：`10.66.66.1:2377`

地址语义必须这样理解：

- `81.70.52.75`
  - SSH / 外网访问 / 公网入口
- `10.66.66.1`
  - seller join 的 control-plane 目标
  - adapter `join-material.manager_addr`

### 当前能力边界

`Docker Swarm` 本身负责：

- 接纳 seller worker
- 运行平台已有服务
- 承载未来 runtime bundle

它不负责：

- 订单真相
- grant 生命周期
- buyer 账号归属

## 6. Docker_Swarm_Adapter 现在是什么情况

`Docker_Swarm_Adapter` 是当前项目的私有基础设施控制面 HTTP 服务。

它的正式定位是：

- 监听 `0.0.0.0:8010`
- 只接受 `Plantform_Backend` 调用
- 对 Docker Swarm / WireGuard 执行受控操作

### 当前已暴露能力

#### 节点与接入面

- `GET /health`
- `GET /swarm/overview`
- `GET /swarm/nodes`
- `POST /swarm/nodes/inspect`
- `GET /swarm/nodes/by-ref/{node_ref}`
- `GET /swarm/nodes/by-compute-node-id/{compute_node_id}`
- `GET /swarm/nodes/search`
- `POST /swarm/nodes/join-material`
- `POST /swarm/nodes/claim`
- `POST /swarm/nodes/availability`
- `POST /swarm/nodes/remove`

#### 商品化与 runtime 预检面

- `POST /swarm/nodes/probe`
- `POST /swarm/runtime-images/validate`
- `POST /swarm/services/inspect`

#### 未来 buyer 会话承载面

- `POST /swarm/runtime-session-bundles/create`
- `POST /swarm/runtime-session-bundles/inspect`
- `POST /swarm/runtime-session-bundles/remove`

#### WireGuard

- `POST /wireguard/peers/apply`
- `POST /wireguard/peers/remove`

### 当前能力边界

adapter 负责：

- `join-material`
- seller 节点 inspect / claim / probe
- runtime image 校验
- runtime bundle create / inspect / remove
- WireGuard peer apply / remove

adapter 不负责：

- 保存 `JoinSession`
- 保存 `manager_acceptance`
- 保存 `effective_target`
- 定义 seller onboarding 完成标准
- 定义 order / grant / runtime session 业务状态

## 7. Plantform_Backend 现在有哪些真实能力

当前 backend 已经从“seller onboarding 真相面”扩展到了“seller 商品化 + buyer 交易骨架”。

### 7.1 seller onboarding 真相链

当前已有：

- `POST /api/v1/seller/onboarding/sessions`
- `GET /api/v1/seller/onboarding/sessions/{session_id}`
- `POST /api/v1/seller/onboarding/sessions/{session_id}/linux-host-probe`
- `POST /api/v1/seller/onboarding/sessions/{session_id}/linux-substrate-probe`
- `POST /api/v1/seller/onboarding/sessions/{session_id}/container-runtime-probe`
- `POST /api/v1/seller/onboarding/sessions/{session_id}/join-complete`
- `POST /api/v1/seller/onboarding/sessions/{session_id}/corrections`
- `POST /api/v1/seller/onboarding/sessions/{session_id}/re-verify`
- `POST /api/v1/seller/onboarding/sessions/{session_id}/authoritative-effective-target`
- `POST /api/v1/seller/onboarding/sessions/{session_id}/minimum-tcp-validation`

当前真相字段包括：

- `manager_acceptance`
- `effective_target_addr`
- `effective_target_source`
- `truth_authority`
- `minimum_tcp_validation`

### 7.2 seller 商品化

当前已实现：

- `POST /api/v1/seller/capability-assessments`
- `verified onboarding session -> capability assessment`
- `assessment 可售 -> offer upsert`
- `assessment 不可售 -> 已有 listing 自动下架`

也就是说，当前 repo 代码里 seller 节点已经可以从：

- `verified node`

变成：

- 真实 `listed offer`

### 7.3 buyer 交易骨架

当前已有：

- `GET /api/v1/offers`
- `GET /api/v1/offers/{offer_id}`
- `POST /api/v1/orders`
- `GET /api/v1/orders/{order_id}`
- `POST /api/v1/orders/{order_id}/activate`
- `GET /api/v1/me/access-grants/active`

当前 buyer 侧还没实现：

- `grant-first` 正式兑换接口
- `RuntimeSession`
- `TaskExecution`
- buyer WireGuard / shell / workspace / task 数据平面

### backend 当前能力边界

backend 负责：

- seller onboarding 业务真相
- seller 节点商品化
- order / access grant 业务真相
- 未来 runtime session / task execution 业务真相
- 编排 adapter 和 WireGuard

backend 不负责：

- 远程代执行 seller `docker swarm join`
- 直接执行 Docker/WireGuard 命令
- 充当运行态数据平面代理

## 8. Seller_Client 现在是什么情况

`Seller_Client` 当前已经是正式 seller 本地入口，不再是历史参考资产。

### 当前它负责什么

- 本地 Web 壳
- seller 登录 / onboarding session 创建
- 本机环境检查
- WireGuard 配置准备
- seller 本地执行 join
- 通过 MCP / 自然语言引导小白卖家完成接入

### 当前它不负责什么

- 不直连 adapter
- 不直接管理 offer
- 不直接管理 buyer runtime session

### 当前 seller 成功标准

- manager 侧看到 worker `Ready`
- manager 侧确认该 worker 上存在可执行或运行中的 task

### 当前 seller 在整体节奏里的位置

- 已处于 `phase3` 末期
- 当前 seller 侧的重点是验证平台上架逻辑是否稳定

## 9. Buyer_Client 现在是什么情况

`Buyer_Client/` 目录已经存在，而且不是历史废稿目录。

### 当前它已经明确的东西

- 买家主语义：
  - `Order`
  - `AccessGrant`
  - `RuntimeSession`
  - `TaskExecution`
- buyer 的正式入口应是本地 `Buyer_Client`
- shell 正式入口应在本地 client，不在平台前端

### 当前它还没完成的东西

- buyer 本地 API
- buyer 本地 state
- buyer MCP
- buyer WireGuard up/down
- runtime session 真正建立
- shell / workspace / task 正式闭环
- Windows 本地 buyer 体验

## 10. Windows SSH / 远控入口怎么用

Windows 远控当前只定义为 operator 运维入口，用于：

- deployment
- diagnostics
- verification

它不等于产品成功标准。

### 首选入口

```bash
ssh win-local-via-reverse-ssh
```

### 等价命令

```bash
ssh -p 22220 -i /root/.ssh/id_ed25519_windows_local 550w@127.0.0.1
```

### 备用入口

```bash
ssh win-local-via-wg
```

### 登录后建议目录

```cmd
cd /d D:\AI\Pivot_Client
```

这条 Windows 远控入口在 `phase4` 与 `phase5` 中只承担：

- 帮 operator 在 Windows 上部署、排查、验证 buyer / seller 本地链路

它不承担：

- 冒充 buyer 产品入口
- 冒充 seller 产品链路

## 11. 当前阶段任务到底是什么

当前总任务不是“继续猜架构”，而是按阶段推进：

### 当前正在做

- `phase3` 末期验证 seller 真实上架逻辑

### 接下来要做

- `phase4` 买家客户端实施
- `phase5` seller-platform-buyer 闭环联调

## 12. 分阶段任务、改动面、成功标准、能力边界

## 阶段 1. 卖家真实 join 和上架正常

### 前面哪个架构要改什么

- seller / backend / adapter 现有链路继续稳定
- 不新增 buyer 逻辑

### 能力边界

- 只验证 seller join、验收、assessment、上架
- 不进入 buyer runtime session

### 成功标准

- seller 真实 join 成功
- backend session `verified`
- `/offers` 可见真实 `listed` offer

## 阶段 2. 买家注册和下单正常

### 前面哪个架构要改什么

- backend：稳定 buyer `auth / order / access grant`
- 前端 / buyer 侧：先消费真实 offer

### 能力边界

- 只做到注册、登录、浏览、下单、激活
- `activate order` 只签发 grant

### 成功标准

- buyer 能看真实 offer
- buyer 能创建 order
- buyer 激活后拿到 `grant_id / grant_code / expires_at`

## 阶段 3. 买家凭证正常，可以在不做代码的情况下真实接入和使用

### 前面哪个架构要改什么

- backend：补 `grant redeem -> runtime session bootstrap`
- adapter / wireguard / runtime：补 buyer session 最小真链

### 能力边界

- 允许手工 `curl`、简单脚本、手工 WireGuard
- 不要求 Buyer_Client 已做完

### 成功标准

- 真实 grant 可兑换 `RuntimeSession`
- 手工拉起 buyer WireGuard
- 真实访问 seller runtime shell
- 至少一次最小 task 使用验证成功

## 阶段 4. 在 Linux 做客户端和 MCP 正常

### 前面哪个架构要改什么

- `Buyer_Client/`：先落 Linux buyer client、本地 API、state、MCP
- backend：配套 `RuntimeSession`

### 能力边界

- Linux first
- 先不要求 Windows buyer 端
- 先不要求网页自然语言完全打通

### 成功标准

- Linux Buyer_Client 可启动
- grant 导入 / session 创建 / shell 打开 / workspace / task 可用

## 阶段 5. 在网页内，用自然语言描述端到端测试正常

### 前面哪个架构要改什么

- `Buyer_Client` 网页壳
- buyer MCP
- CodeX 自然语言引导

### 能力边界

- 仍以 Linux 为首个完整自然语言落点
- 还不把 Windows 远控写成产品成功

### 成功标准

- 在网页内通过自然语言触发完整 buyer 链路
- 自动完成 grant / session / WireGuard / shell / workspace / task

## 阶段 6. 远控 Win，在 Win 那边操作正常

### 前面哪个架构要改什么

- `Buyer_Client` Windows 本地实现
- Windows 本地 WireGuard
- Windows 本地网页和 CodeX 接入
- operator 远控脚本与 runbook

### 能力边界

- 允许通过 `reverse SSH` / `win-local-via-wg` 进入 Windows
- 远控只用于实施和验证
- 真正产品链仍然必须在 Windows 本地运行

### 成功标准

- Windows 本地 Buyer_Client 可运行
- Windows 本地可访问 seller runtime shell
- Windows 本地网页内通过 `CodeX` 自然语言描述，可以传递并完成 task

## 13. 当前推荐读文顺序

1. 本文
2. `PROJECT.md`
3. `Docker_Swarm/README.md`
4. `Docker_Swarm/Docker_Swarm_Adapter/README.md`
5. `Plantform_Backend/docs/后端当前状态与接入说明.md`
6. `Seller_Client/docs/current-seller-onboarding-flow-cn.md`
7. `Buyer_Client/docs/phase4-buyer-client-implementation-spec-cn.md`
8. `win_romote/windows 电脑ssh 说明.md`

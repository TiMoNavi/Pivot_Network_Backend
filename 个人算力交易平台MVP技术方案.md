# 个人算力交易平台 MVP 技术方案

更新时间：`2026-04-11`

## 1. 文档定位

这份文档定义当前 repo 已经开始执行的 MVP，而不是旧阶段的概念验证稿。

当前 MVP 的主线已经收束成：

- 先把 seller onboarding 做成稳定、可重复的正式链路
- 再把 `verified` seller 节点商品化成真实 `Offer`
- 然后把 buyer 侧收口到 `grant-first + RuntimeSession`

## 1.1 当前阶段定位

当前 MVP 推进节奏应固定为：

- `phase3` 末期
  - seller 节点商品化
  - 平台上架逻辑验证
- `phase4`
  - 买家客户端设计与实施规格
- `phase5`
  - 卖家、平台、买家联调闭环

## 2. 当前 MVP 的核心目标

### 2.1 第一目标

让 Windows 卖家可以通过本地 Web + MCP 主线完成：

- 登录 backend
- 创建 fresh onboarding session
- 准备机器专属 WireGuard 配置
- 本地执行 join
- 由 manager 侧 task execution 完成最终验收

### 2.2 第二目标

让 backend 成为卖家接入的业务真相面，能够保存：

- `JoinSession`
- probes
- `join-complete`
- `manager_acceptance`
- `effective_target`
- `truth_authority`
- `minimum_tcp_validation`

### 2.3 第三目标

让 buyer 侧正式消费 seller 商品化结果，而不是继续依赖脱离 seller 接入链的 placeholder。

目标闭环应是：

- `verified seller node -> assessed offer -> order -> access grant -> runtime session -> shell/task/artifacts`

## 3. 当前正式执行链

当前 MVP 的正式链路固定为：

- `Seller_Client -> Plantform_Backend -> Docker_Swarm_Adapter -> Docker Swarm`

并且遵守这些硬约束：

1. seller 本地执行 `docker swarm join`
2. seller client 不直连 adapter
3. backend 才是 seller onboarding 的业务真相源
4. seller onboarding 的完成标准是 manager-side task execution

## 4. 当前权威地址与术语

### 4.1 地址

- backend 公网入口：`https://pivotcompute.store`
- swarm manager 公网地址：`81.70.52.75`
- swarm manager WireGuard / control-plane 地址：`10.66.66.1`
- 当前权威 join target：`10.66.66.1:2377`

### 4.2 术语

- `manager_acceptance`
  - backend 通过 adapter 验证出来的 raw manager 真相
- `effective_target`
  - backend 当前认可、可供后续连接语义消费的 seller target
- `truth_authority`
  - 当前 target 属于 `raw_manager` 还是 `backend_correction`
- `minimum_tcp_validation`
  - 针对 target 的附加连通证据，不替代 seller join 完成标准

## 5. 当前 seller onboarding MVP

### 5.1 用户视角流程

1. 启动 `start_seller_client.ps1`
2. 登录或注册 backend
3. 创建 fresh onboarding session
4. 在 AI 助手里说“帮我接入”
5. MCP 工具链完成：
   - 环境检查
   - WireGuard 配置准备
   - join material 读取
   - guided join
   - manager task execution 验证

### 5.2 当前 seller 完成标准

当前 seller onboarding 只在下面两条同时成立时算完成：

- manager 侧 worker `Ready`
- manager 侧确认该 worker 上存在可执行或运行中的 task

以下都不再单独算成功：

- 本地 `WireGuard` 通了
- 本地 `docker info` 显示 `LocalNodeState=active`
- 本地 `NodeAddr` 恰好等于期望地址

## 6. 当前 backend MVP

### 6.1 已经落地

- 认证
- seller onboarding session
- Phase 1 probes
- `join-complete`
- `corrections`
- `re-verify`
- `authoritative-effective-target`
- `minimum-tcp-validation`
- 节点只读接口
- placeholder trade/access grant

### 6.2 当前 buyer/trade 现状

backend 当前 repo 代码已经补上 seller 商品化主线：

- `verified` onboarding session 会触发 capability assessment
- assessment 可售时按 `compute_node_id` upsert 真实 offer
- assessment 不可售时自动下架已有 listing

但 buyer 侧正式 runtime 会话闭环仍未完成。

当前 buyer 侧仍缺：

- `grant-first` 正式接口
- `RuntimeSession`
- buyer WireGuard 会话
- shell / workspace / task / artifacts 数据平面

## 7. 当前 adapter / swarm MVP

adapter 当前已经能提供：

- `join-material`
- inspect / search / claim
- runtime bundle create / inspect / remove
- wireguard peer apply / remove

但它仍然不是卖家接入的业务状态机。

当前 MVP 里 adapter 的角色仍然是：

- 基础设施控制面

而不是：

- seller onboarding 真相面

## 8. 当前 correction lane 的定位

当前 repo 仍然保留 correction 相关接口：

- `corrections`
- `re-verify`
- `authoritative-effective-target`
- `minimum-tcp-validation`

它们现在的定位是：

- 当 raw manager truth 不能直接收口时，backend 仍然能保存 formal correction lane
- raw mismatch 不会被伪造成 raw matched
- `effective_target` 可以进入 `backend_correction` 语义

但 seller onboarding 的完成标准已经前移到 manager-side task execution。

换句话说：

- correction lane 现在更偏向“服务端真相收口与后续连接语义”
- 而不是 seller join 本身的唯一完成标准

## 9. 当前未完成的 MVP 部分

- buyer `grant-first` 正式后端模型
- `RuntimeSession / TaskExecution` 落库
- Buyer_Client 正式能力实现
- orders / grants 对接 adapter runtime bundle 真值
- seller 到 buyer 的端到端闭环联调

## 10. 当前建议执行顺序

1. 在 `phase3` 末期继续稳定 seller onboarding 与商品化主线
2. 进入 `phase4`，补 buyer 实施规格
3. 在 backend 落 `grant-first + RuntimeSession`
4. 推进 Buyer_Client 与 runtime/session 正式闭环
5. 进入 `phase5`，做 seller 到 buyer 的完整联调

# 后端 MVP 设计说明

更新时间：`2026-04-10`

## 1. 文档定位

这份文档描述的是“当前 repo 代码已经在执行的 MVP 后端”，不是历史蓝图，也不是未来完整交易平台的终态文档。

当前后端 MVP 的核心任务只有两个：

1. 为 `Seller_Client` 提供稳定的卖家接入业务控制面
2. 为后续 buyer/runtime 闭环保留最小可延展的真相模型

## 2. 当前系统分工

### 2.1 Seller Client

负责：

- 本地 Web 壳
- 本机环境检查
- 本机 WireGuard 配置准备
- 本机 `docker swarm join`
- MCP 编排
- 本地证据采集与回写

不负责：

- 直连 adapter
- 直接给 buyer 发 target

### 2.2 Platform Backend

负责：

- 账号与会话
- `JoinSession`
- Phase 1 扁平 probe / `join-complete` 写入
- `manager_acceptance`
- correction / re-verify
- `effective_target`
- 占位 `offer / order / access_grant`

不负责：

- 远程代执行 seller 机器上的 join
- 直接运行 Docker/WireGuard 命令

### 2.3 Docker Swarm Adapter

负责：

- `join-material`
- 节点 inspect / search / claim
- runtime bundle 与 wireguard 租约

不负责：

- 保存 `JoinSession`
- 保存业务态 `manager_acceptance`
- 决定卖家接入是否完成

## 3. 当前 MVP 锁定的 seller onboarding 模型

当前后端卖家接入模型已经锁定到以下对象：

### 3.1 `JoinSession`

当前真实字段语义包括：

- `status`
- `requested_accelerator`
- `requested_compute_node_id`
- `swarm_join_material`
- `required_labels`
- `expected_wireguard_ip`
- `manager_acceptance`
- `manager_acceptance_history`
- `effective_target_addr`
- `effective_target_source`
- `truth_authority`
- `minimum_tcp_validation`

### 3.2 三类 probe

当前 seller client 会分别提交：

- `linux-host-probe`
- `linux-substrate-probe`
- `container-runtime-probe`

后端当前聚合方式：

- `probe_summary`
  - 聚合 host/substrate
  - 提供 `resource_summary`
- `container_runtime_probe`
  - 单独回传

### 3.3 `join-complete`

当前正式 ingress 是扁平 shape：

- `reported_phase`
- `node_ref`
- `compute_node_id`
- `observed_wireguard_ip`
- `observed_advertise_addr`
- `observed_data_path_addr`
- `notes`
- `raw_payload`

runtime-local 的嵌套 draft 只能留在 `raw_payload`，不能直接替代 backend write shape。

## 4. 当前真相链设计

### 4.1 Raw manager lane

后端创建 session 后，会在 seller 回写 `join-complete` 时通过 adapter 执行：

- inspect
- claim
- inspect

然后把结果收敛为 `manager_acceptance`。

如果 raw manager 已 matched：

- `effective_target_source = manager_matched`
- `truth_authority = raw_manager`

### 4.2 Backend correction lane

如果 raw manager mismatch，但服务端需要正式收口 target，当前允许：

- `corrections`
- `re-verify`
- `authoritative-effective-target`
- `minimum-tcp-validation`

此时：

- raw mismatch 仍保留为可读事实
- `effective_target_addr` 可来自 `backend_correction`
- `truth_authority = backend_correction`

### 4.3 当前完成标准

根据最新 `Seller_Client` 代码，卖家 join 的完成标准已经收束成：

- manager 侧 worker `Ready`
- manager 侧确认该 worker 上存在可执行或运行中的 task

`minimum_tcp_validation` 保留，但它是服务端补充证据与后续 buyer/connect 语义输入，不再是 seller onboarding 完成标准本身。

## 5. 当前 buyer / trade MVP 状态

后端当前确实已经有：

- `offers`
- `orders`
- `access_grants`

但它们仍然是 placeholder MVP：

- `Offer` 来自预置样例，不是卖家上架结果
- `Order` 只是占位订单
- `AccessGrant` 目前可附带 onboarding 产出的 `effective_target`

当前 buyer 侧真实价值在于：

- backend 已经能把 `manager_matched / backend_correction / operator_override` 三种 target lane 暴露进 grant
- 当 session 上存在 `minimum_tcp_validation` 时，grant 会附带该快照

## 6. 当前持久化状态

当前代码现状是：

- seller onboarding 已经迁到 SQLAlchemy + 数据库表
- onboarding 状态已从单表 JSON 收口为 `session + probe/join/history/current-state` 规范化子表
- Alembic 已作为正式迁移入口补回仓库
- `auth / trade` 也已经迁到数据库表
- PostgreSQL 与 SQLAlchemy 骨架已经开始承接当前核心业务态，但 seller node / runtime / offer-profile 等更完整业务模型还没继续展开

如果只按 MVP 的最短路径推进，下一批应该优先落库：

1. `users`
2. `auth_sessions`
3. `join_sessions`
4. `linux_host_probes`
5. `linux_substrate_probes`
6. `container_runtime_probes`
7. `join_completions`
8. `corrections`
9. `manager_acceptance_history`
10. `minimum_tcp_validations`

## 7. 当前最重要的设计约束

- `Seller_Client` 不直连 adapter
- backend 不接受嵌套 runtime draft 直接替代扁平 ingress
- raw manager truth 与 backend correction truth 必须同时可读，不能互相覆盖
- `81.70.52.75` 是公网/SSH 语义，当前 seller join target 必须是 `10.66.66.1:2377`
- buyer/connect 只能消费 backend 已收口出来的 `effective_target`

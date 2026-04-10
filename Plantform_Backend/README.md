# Plantform Backend

更新时间：`2026-04-11`

`Plantform_Backend` 现在已经不是“只有读接口的占位骨架”，而是当前卖家接入主线里的业务控制面。

当前项目阶段更准确地说，应位于：

- `phase3` 末期
  - 验证 seller `verified node -> assessment -> listed offer`
- 下一步进入 `phase4`
  - buyer `grant-first + RuntimeSession` 设计与实现

当前正式链路固定为：

- `Seller_Client -> Plantform_Backend -> Docker_Swarm_Adapter`

其中：

- `Seller_Client` 负责本地 Web、MCP 编排、本机探测、join 执行与本地证据采集
- `Plantform_Backend` 负责接入会话、平台真相、manager 验收、correction/re-verify、effective target
- `Docker_Swarm_Adapter` 负责 `join-material / inspect / claim / inspect` 这类基础设施动作

## 当前已实现能力

- 卖家注册、登录、`/auth/me`
- Seller onboarding session 创建、读取、心跳、关闭
- Phase 1 三类 probe 写入：
  - `linux-host-probe`
  - `linux-substrate-probe`
  - `container-runtime-probe`
- `join-complete`
- `corrections`
- `re-verify`
- `authoritative-effective-target`
- `minimum-tcp-validation`
- 平台节点只读接口：
  - `GET /api/v1/platform/swarm/overview`
  - `GET /api/v1/platform/nodes`
  - `GET /api/v1/platform/nodes/search`
  - `GET /api/v1/platform/nodes/{node_ref}`
  - `GET /api/v1/platform/nodes/by-compute-node-id/{compute_node_id}`
  - `GET /api/v1/platform/swarm/poll-snapshot`
- 文件分发接口
- `seller capability assessment`
- 基于 `verified` 节点的真实 `offer / order / access_grant` 交易骨架

## 当前交易面的真实状态

当前 repo 代码已经把 seller onboarding 与 offer 商品化接起来了。

现在正式主线是：

- seller 节点通过 onboarding 验收
- backend 对 `verified` 节点做 capability assessment
- backend 按 `compute_node_id` 自动创建或更新真实 offer
- assessment 不可售时自动下架已有 listing

下一步正式设计已经单独写入：

- [`docs/卖家节点商品化与能力测算设计.md`](docs/%E5%8D%96%E5%AE%B6%E8%8A%82%E7%82%B9%E5%95%86%E5%93%81%E5%8C%96%E4%B8%8E%E8%83%BD%E5%8A%9B%E6%B5%8B%E7%AE%97%E8%AE%BE%E8%AE%A1.md)

buyer 侧仍然没有进入正式 `RuntimeSession` 闭环，因此当前交易面应理解为：

- seller 商品化已接通
- buyer runtime 会话仍待实现

## 当前卖家接入契约

卖家客户端当前依赖的是扁平写入接口，而不是旧的嵌套 runtime draft：

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
- `POST /api/v1/seller/onboarding/sessions/{session_id}/heartbeat`
- `POST /api/v1/seller/onboarding/sessions/{session_id}/close`

当前 session 返回体已经包含这些卖家客户端正在使用的字段：

- `expected_wireguard_ip`
- `manager_acceptance`
- `manager_acceptance_history`
- `effective_target_addr`
- `effective_target_source`
- `truth_authority`
- `minimum_tcp_validation`
- `required_labels`
- `swarm_join_material`

当前 backend 还新增了 seller/admin 用的独立测算接口：

- `POST /api/v1/seller/capability-assessments`

## 当前权威地址语义

- backend 公网入口：`https://pivotcompute.store`
- swarm manager 公网地址：`81.70.52.75`
- swarm manager WireGuard / control-plane 地址：`10.66.66.1`
- 当前权威 join target：`10.66.66.1:2377`

也就是说：

- `manager_addr` 在当前 join material 里应表示 `SWARM_CONTROL_ADDR`
- `81.70.52.75` 仍然是公网访问/SSH 语义，不再是 seller 的 swarm join target

## 当前真相模型

后端现在维护两层服务端真相：

1. `manager_acceptance`
   - 由 backend 通过 adapter 执行 `inspect / claim / inspect` 得到
   - 表示 raw manager 侧是否按期望地址识别节点
2. `effective_target`
   - 优先级为 `manager_matched -> backend_correction -> operator_override`
   - 可用于后续 buyer/connect 语义或 operator 纠偏

当前卖家接入完成标准已经转成：

- manager 侧确认 worker `Ready`
- manager 侧确认该 worker 上存在可执行或运行中的 task

`minimum_tcp_validation` 仍然保留，但它是服务端附加证据，不再替代 manager-side task execution 成为 seller join 的完成标准。

## 运行方式

```bash
cd /root/Pivot_network/Plantform_Backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
docker compose up -d postgres
uvicorn backend_app.main:app --host 0.0.0.0 --port 8000 --reload
```

数据库迁移：

```bash
cd /root/Pivot_network/Plantform_Backend
source .venv/bin/activate
alembic upgrade head
```

## 关键环境变量

- `BACKEND_ADAPTER_BASE_URL`
- `BACKEND_ADAPTER_TOKEN`
- `BACKEND_DOWNLOAD_ROOT`
- `BACKEND_POSTGRES_HOST`
- `BACKEND_POSTGRES_PORT`
- `BACKEND_POSTGRES_USER`
- `BACKEND_POSTGRES_PASSWORD`
- `BACKEND_POSTGRES_DB`

## 当前实现边界

- seller onboarding 现在已经迁到 SQLAlchemy + 数据库表
- 当前 onboarding 已拆成规范化子表，而不是继续把 probe/history 全塞进 session JSON：
  - `seller_onboarding_sessions`
  - `seller_onboarding_linux_host_probes`
  - `seller_onboarding_linux_substrate_probes`
  - `seller_onboarding_container_runtime_probes`
  - `seller_onboarding_join_completions`
  - `seller_onboarding_corrections`
  - `seller_onboarding_manager_address_overrides`
  - `seller_onboarding_authoritative_effective_targets`
  - `seller_onboarding_manager_acceptances`
  - `seller_onboarding_manager_acceptance_history`
  - `seller_onboarding_minimum_tcp_validations`
- `auth / trade` 也已经迁到数据库表：
  - `users`
  - `auth_sessions`
  - `offers`
  - `orders`
  - `access_grants`
- 当前 repo 里的真实 offer 主来源已经是 capability assessment 自动生成结果；seed offer 只保留在开发/测试夹具或迁移兼容语义里
- backend 会在首次使用 seller onboarding / trade 相关依赖时自动初始化 onboarding 表
- 自动建表只适合本地开发和测试；正式环境应优先运行 `alembic upgrade head`
- adapter 的 runtime bundle 与 wireguard 租约接口已经存在，但 backend 的 buyer runtime 会话面仍未正式接通
- 当前 `auth / trade` 相关表之外，还新增了：
  - `seller_capability_assessments`
- `offers` 已扩展：
  - `compute_node_id`
  - `source_join_session_id`
  - `source_assessment_id`

如果要继续推进，优先顺序建议是：

1. 继续稳定 `verified node -> assessment -> offer`
2. 把 buyer 侧改成 `grant-first + RuntimeSession`
3. 让 buyer runtime/access grant 从交易骨架过渡到 adapter runtime bundle 真值
4. 逐步把自动建表收敛为纯 migration 驱动

# 平台后端重写版实现规划文档

更新时间：`2026-04-05`

## 0. 当前实现快照

截至当前环境，后端与 adapter 的进度并不同步：

- `Docker Swarm Adapter` 已经进入真实可运行阶段
- `Backend/` 已有基础 `FastAPI + PostgreSQL + Alembic + AdapterClient scaffold`
- 但真正的平台业务代码还没有正式落地

当前阶段可概括为：

- adapter：实现领先
- backend：设计领先

因此这份文档的主要作用是：

- 把 backend 的下一阶段实现边界写清楚
- 明确 Windows 本地客户端与平台后端的职责切分
- 让 backend 设计与 adapter 当前已实现的真实行为对齐

## 1. 文档定位

这份文档是平台后端的实施主文档，直接面向当前项目的下一阶段后端开发。

它不再是“通用后端设计稿”，而是要解决当前这个项目里的真实问题：

- `seller client` 和 `buyer client` 是运行在用户本地 Windows 电脑上的独立客户端
- `platform backend` 是唯一正式对接客户端的云端入口
- `platform backend` 也是唯一正式对接 `Docker Swarm Adapter` 的业务控制层

文档主线采用“双层接口”结构：

- 客户端默认走 seller/buyer 工作流接口
- 后端额外提供一层 `/adapter-proxy/...` 全量代理接口
- 平台同步与后台任务作为 Phase 1 优先级最高的基础层

## 2. 目标与边界

## 2.1 系统角色

当前系统有 4 个主要层次：

1. `seller client`
2. `buyer client`
3. `platform backend`
4. `Docker Swarm Adapter`

## 2.2 Windows 本地客户端的边界

### `seller client`

`seller client` 是运行在卖家 Windows 本地电脑上的客户端。它负责：

- 登录平台
- 获取 join-material
- 本地执行或引导 `docker swarm join`
- 获取平台基础镜像与运行时契约
- 基于平台基础镜像构建 seller image
- 上报镜像
- 查看自己的节点、offer、容器状态

它不负责：

- 直接调用 adapter
- 直接 claim 节点
- 直接创建/删除 runtime bundle

### `buyer client`

`buyer client` 是运行在买家 Windows 本地电脑上的客户端。它负责：

- 登录平台
- 浏览 offer
- 下单
- 兑换 access code
- 获取 connect material
- 本地执行 WireGuard 接入
- 打开网页端 shell

它不负责：

- 直接调用 adapter
- 直接创建/删除 runtime session
- 直接操作 Docker / WireGuard 服务端

## 2.3 Platform Backend 的边界

`platform backend` 负责：

- 注册、登录、token、角色、异常处理
- seller / buyer / platform 三类 API
- 订单、offer、access code、runtime session 状态机
- 对接 adapter 并消费其结果
- 暴露客户端真正需要的工作流接口
- 暴露 `/adapter-proxy/...` 全量代理能力
- 保存业务状态、同步快照、审计日志、后台任务状态

`platform backend` 不负责：

- 本地执行 Docker CLI
- 直接访问 Docker Socket
- 直接 SSH 到远端 manager
- 直接修改 WireGuard 配置

## 2.4 Adapter 的边界

`Docker Swarm Adapter` 负责：

- 执行 Swarm / WireGuard 真实动作
- 返回节点、service、bundle、lease 的真实状态

`adapter` 不负责：

- 用户注册/登录
- 订单、支付、价格快照
- 平台数据库写入
- 直接对 Windows 客户端开放

## 3. 后端模块拆分

后端按 8 个模块拆分：

1. `认证与身份模块`
   - 注册、登录、token、角色、Windows 客户端身份绑定
2. `Adapter 集成与代理模块`
   - `AdapterClient`
   - `/adapter-proxy/...`
   - adapter 错误映射、重试、审计
3. `Swarm 同步读模型模块`
   - `swarm_*` 表
   - 周期同步与即时刷新
4. `Seller 工作流模块`
   - 节点接入
   - claim 状态
   - 基础镜像/契约下发
   - 镜像上报
5. `Offer 与供给模块`
   - validate/probe 结果消费
   - `offer_ready` 形成
   - catalog 读模型
6. `Buyer 交易模块`
   - order
   - access code
   - 价格快照
7. `Runtime Session 模块`
   - create / inspect / stop
   - connect material
   - session 状态刷新
8. `平台运维与审计模块`
   - platform/admin 视图
   - `activity_events`
   - `operation_logs`
   - reaper / workers

## 4. FastAPI 架构设计

## 4.1 默认技术栈

后端继续沿用当前 `Backend/` scaffold：

- `FastAPI`
- `Pydantic`
- `SQLAlchemy 2.x`
- `Alembic`
- `PostgreSQL`
- `httpx`

数据库驱动继续推荐：

- 同步栈：`psycopg`
- 异步栈：`asyncpg` 配合 SQLAlchemy async

## 4.2 目录与分层

继续沿用当前 `Backend/backend_app` 结构，并按已有 scaffold 扩展：

```text
backend_app/
├── api/
├── clients/
│   └── adapter/
├── core/
├── db/
├── repositories/
├── schemas/
├── services/
├── workers/
└── main.py
```

应用分层固定为：

- `api/`：HTTP 路由与依赖注入
- `schemas/`：请求/响应模型
- `services/`：业务用例
- `repositories/`：数据访问层
- `clients/adapter/`：adapter HTTP client
- `workers/`：同步、刷新、reaper

## 4.3 AdapterClient 设计

`AdapterClient` 仍然是核心基础设施 client，后端所有对 adapter 的调用都应走它。

它至少要支持：

- `get_health()`
- `get_swarm_overview()`
- `list_nodes()`
- `inspect_node()`
- `get_join_material()`
- `claim_node()`
- `set_node_availability()`
- `remove_node()`
- `validate_runtime_image()`
- `probe_node()`
- `inspect_service()`
- `create_runtime_bundle()`
- `inspect_runtime_bundle()`
- `remove_runtime_bundle()`
- `apply_wireguard_peer()`
- `remove_wireguard_peer()`

当前现实：

- 上述方法在 adapter 侧都已有对应真实 HTTP 接口
- backend Phase 1 不再等待 adapter，而是直接消费这些能力

## 5. API 结构：工作流主入口 + 全量代理

## 5.1 工作流主入口

这是 seller/buyer 默认走的主入口。

### `auth/*`

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`

### `seller/*`

- `POST /seller/node-registration-tokens`
- `POST /seller/nodes/register`
- `GET /seller/nodes`
- `GET /seller/nodes/{node_id}`
- `GET /seller/nodes/{node_id}/claim-status`
- `GET /seller/runtime-base-images`
- `GET /seller/runtime-contract`
- `POST /seller/images/report`
- `GET /seller/images`
- `GET /seller/offers`
- `GET /seller/containers`
- `GET /seller/containers/{container_id}`

### `buyer/*`

- `GET /buyer/catalog/offers`
- `POST /buyer/orders`
- `GET /buyer/orders/{order_id}`
- `POST /buyer/access-codes/redeem`
- `POST /buyer/runtime-sessions`
- `GET /buyer/runtime-sessions/{session_id}`
- `POST /buyer/runtime-sessions/{session_id}/stop`
- `POST /buyer/runtime-sessions/{session_id}/connect-material`

### `platform/*`

- `GET /platform/overview`
- `GET /platform/swarm/overview`
- `POST /platform/swarm/sync`
- `GET /platform/nodes`
- `GET /platform/nodes/{node_id}`
- `GET /platform/offers`
- `GET /platform/orders`
- `GET /platform/runtime-sessions/{session_id}`
- `POST /platform/runtime-sessions/{session_id}/refresh`
- `GET /platform/activity`

## 5.2 Adapter Proxy 接口

这是 backend 对 adapter 的全量代理层，统一挂在：

- `/api/v1/adapter-proxy/swarm/...`
- `/api/v1/adapter-proxy/wireguard/...`

规则固定为：

- 客户端默认只需要工作流接口
- proxy 接口对客户端可见，但必须做角色和 scope 限权
- 后端负责隐藏 adapter 的 Bearer token
- proxy 接口尽量保持和 adapter 路径、payload 接近

建议最小暴露范围：

### `/adapter-proxy/swarm/...`

- `/overview`
- `/nodes`
- `/nodes/inspect`
- `/nodes/join-material`
- `/nodes/claim`
- `/nodes/availability`
- `/nodes/remove`
- `/runtime-images/validate`
- `/nodes/probe`
- `/services/inspect`
- `/runtime-session-bundles/create`
- `/runtime-session-bundles/inspect`
- `/runtime-session-bundles/remove`

### `/adapter-proxy/wireguard/...`

- `/peers/apply`
- `/peers/remove`

## 5.3 工作流接口与 adapter 的映射

文档里要明确几条核心映射：

- `/seller/nodes/register`
  - backend 内部调 `join-material`
- `/seller/nodes/{id}/claim-status`
  - backend 内部调 adapter inspect 或读同步模型
- `/seller/images/report`
  - backend 内部调 `runtime-images/validate` + `nodes/probe`
- `/buyer/runtime-sessions`
  - backend 内部调 `runtime-session-bundles/create`
- `/buyer/runtime-sessions/{id}/connect-material`
  - backend 内部调 `runtime-session-bundles/inspect`
  - 直接返回 `connect_metadata`

## 6. PostgreSQL 设计按阶段落地

## 6.1 Phase 1 必落地

- `users`
- `session_tokens`
- `seller_profiles`
- `buyer_profiles`
- `swarm_clusters`
- `swarm_nodes`
- `swarm_node_labels`
- `swarm_services`
- `swarm_tasks`
- `swarm_sync_runs`
- `swarm_sync_events`
- `activity_events`
- `operation_logs`

## 6.2 Phase 2 落地

- `image_artifacts`
- `image_offers`
- `node_capability_snapshots`
- `offer_price_snapshots`

## 6.3 Phase 3 落地

- `buyer_orders`
- `access_codes`

## 6.4 Phase 4 落地

- `runtime_sessions`
- `runtime_session_events`
- `gateway_endpoints`
- `wireguard_leases`
- `connect_tokens` 可保留为未来扩展，不强制这一阶段实现

## 6.5 字段要求

必须继续保留并强调：

- `runtime_sessions.connect_material_payload`
  - 直接承接 adapter `connect_metadata`
- `wireguard_leases.lease_payload`
  - 直接承接 adapter `wireguard_lease_metadata`
- `image_offers.validation_payload`
  - 必须能存 managed runtime image 契约检查结果
- `swarm_services.service_kind`
  - 至少支持 `runtime` / `gateway` / `other`

## 7. 五个明确 Phase

## 7.1 Phase 1：后端核心 + adapter 代理 + swarm 同步

目标：

- 完成 auth 基础
- 完成 `AdapterClient`
- 完成 `/adapter-proxy/...` 基础层
- 完成 `swarm_*` 读模型和同步 worker
- 完成最小 platform/admin 查看接口

阶段边界：

- 先不做 seller 镜像上报
- 先不做 buyer 订单
- 先不做 runtime session 创建
- 重点是把 backend 变成一个真正能“看 adapter、代理 adapter、落库 swarm 状态”的服务

## 7.2 Phase 2：seller 工作流

目标：

- 完成 seller 登录后节点接入主线
- 完成基础镜像/契约接口
- 完成镜像上报
- 完成节点 claim 状态读取
- 完成 offer readiness 所需的 validate/probe 消费

阶段边界：

- 这一阶段 seller 能把自己的机器和镜像接进平台
- 但 buyer 还不能正式下单

## 7.3 Phase 3：buyer 轻交易

目标：

- 完成 catalog
- 完成 order
- 完成 access code
- 完成轻交易状态流转

阶段边界：

- 不接真实支付
- 不做结算
- 只把“下单 -> access code -> 可开机会话”跑通

## 7.4 Phase 4：runtime session 与连接材料

目标：

- 完成 `runtime_sessions` 表和 service 层
- 完成 create / inspect / stop
- 完成 `connect-material`
- 正式消费 adapter 的 `connect_metadata` 和 `wireguard_lease_metadata`

阶段边界：

- 这一阶段 buyer client 能真正拿到连接材料
- 但平台级运维和稳定性增强还没全部完成

## 7.5 Phase 5：平台运维与稳定性

目标：

- 完成完整 platform/admin 查询
- 完成 runtime refresh worker
- 完成 reaper
- 完成审计、异常重试、手动刷新和排障接口

阶段边界：

- 这是“把产品变成可长期跑”的阶段
- 不再是最小闭环阶段

## 8. 后端不只是业务层，也是客户端统一入口

这次文档必须写死这个原则：

- backend 不只是 DB + 订单层
- backend 也是客户端统一入口层

因此 backend 同时承担：

- 业务状态机
- adapter 能力代理
- 连接材料聚合
- 错误屏蔽与标准化返回

这意味着：

- 客户端不需要知道 adapter token
- 客户端不需要理解 adapter 内部错误码
- 客户端优先拿到的是平台语义响应
- 在专家模式或调试模式下，客户端仍可以通过 `/adapter-proxy/...` 访问被授权的原子能力

## 9. 与 adapter 当前实现的对齐

当前 adapter 已经具备真实能力：

- 节点接入与下线
- validate / probe / service inspect
- runtime bundle create / inspect / remove
- wireguard peers apply / remove

backend 下一步不再是“等 adapter 准备好”，而是要：

- 正式封装 `AdapterClient`
- 把 adapter 返回落到数据库
- 对客户端暴露工作流入口和 proxy 层

## 10. 按阶段验收

## 10.1 Phase 1

- backend 能连 Postgres
- backend 能连 adapter
- `/adapter-proxy/swarm/overview` 可用
- `swarm_*` 同步表会刷新

## 10.2 Phase 2

- seller client 能登录、拿 join-material、看到 claim 状态
- 镜像上报后 validate/probe 结果可落库
- `offer_ready` 状态能形成

## 10.3 Phase 3

- buyer 能浏览 offer、创建订单、拿 access code、兑换 access code

## 10.4 Phase 4

- backend 能创建 runtime session
- backend 能从 adapter 读到真实 `connect_metadata`
- backend 能从 adapter 读到真实 `wireguard_lease_metadata`
- backend 能把 connect material 返回给 buyer client
- backend 能 stop / reclaim session

## 10.5 Phase 5

- runtime refresh worker 和 reaper 正常工作
- `operation_logs` 能记录 adapter 调用失败
- platform/admin 接口能查看节点、service、runtime、订单与异常

## 11. 实施假设

- 继续使用 [platform-backend-implementation-plan.md](/root/Pivot_network/Backend/docs/platform-backend-implementation-plan.md) 作为主文档路径
- 当前 `Backend/` scaffold 保留并沿用
- 客户端是 Windows 本地客户端，这个事实必须写进文档边界
- backend 默认既提供工作流接口，也提供一层全量 adapter proxy
- 当前 adapter 已足够成熟，backend Phase 1 不再等待 adapter
- 真实支付、钱包、结算仍不纳入这一版后端实现规划

# Adapter 能力核查

更新时间：`2026-04-10`

## 1. 结论

当前 `Docker_Swarm_Adapter` 已经足够支撑最新卖家客户端的基础设施调用链，但它仍然只是“基础设施适配层”，不是 seller onboarding 的业务真相源。

当前正式边界依然是：

- `Seller_Client -> Plantform_Backend -> Docker_Swarm_Adapter`

## 2. 当前 Adapter 实际接口

当前代码里真实暴露的是这 `19` 个接口：

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
- `POST /swarm/runtime-images/validate`
- `POST /swarm/nodes/probe`
- `POST /swarm/services/inspect`
- `POST /swarm/runtime-session-bundles/create`
- `POST /swarm/runtime-session-bundles/inspect`
- `POST /swarm/runtime-session-bundles/remove`
- `POST /wireguard/peers/apply`
- `POST /wireguard/peers/remove`

## 3. 对卖家接入主线的实际支撑

### 3.1 已经直接可用

- `POST /swarm/nodes/join-material`
  - 返回当前 seller onboarding 所需的 join token、join command、推荐标签、推荐 compute node id
- `GET /swarm/nodes/by-compute-node-id/{compute_node_id}`
  - backend 可按平台节点标识读取 manager 侧真相
- `POST /swarm/nodes/claim`
  - backend 可在节点 join 后写入平台标签
- `POST /swarm/nodes/inspect`
  - backend 可按 `node_ref` 读取 manager 侧节点详情
- `GET /swarm/nodes/search`
  - backend 和运维都可按 seller/compute/role/status 做检索

### 3.2 当前 join material 语义

根据当前 adapter 实现：

- `manager_addr` 取自 `SWARM_CONTROL_ADDR`
- 当前默认值应是 `10.66.66.1`
- `swarm_join_command` 应 join 到 `10.66.66.1:2377`
- `81.70.52.75` 仍然是 `SWARM_MANAGER_ADDR`，保留公网/SSH 语义

也就是说，adapter 现在已经和最新 seller client 文档保持一致，不应再回退到公网 `81.70.52.75:2377` 作为 seller join target。

## 4. Adapter 仍然不负责什么

当前 adapter 依然不负责：

- `JoinSession`
- `manager_acceptance`
- `effective_target`
- `truth_authority`
- `minimum_tcp_validation`
- manager-side task execution 作为 seller join 完成标准的业务判定

这些都仍然由 backend 或 seller runtime 负责编排与落状态。

## 5. 当前与后端的职责切分

### 5.1 Adapter

只负责：

- 生成 join material
- 读取节点真相
- claim 节点
- 提供 runtime bundle / wireguard 租约能力

### 5.2 Backend

负责：

- 创建 onboarding session
- 接收 seller probes 与 `join-complete`
- 通过 adapter 执行 `inspect / claim / inspect`
- 维护 `manager_acceptance`
- 记录 `corrections / re-verify / authoritative-effective-target / minimum-tcp-validation`

## 6. 当前明显缺失但暂时可接受的点

- 没有独立的 `verify` 或 `join-verify` 聚合接口
- 没有“manager task execution”专用验证接口
- 没有 seller WireGuard onboarding material 的专用服务端接口
- 没有 session-aware 的 correction orchestration 接口

这些缺失不会阻断当前卖家客户端主线，因为当前主线已经把：

- 本机 WireGuard 配置准备
- 本机 join 执行
- manager task execution 验证

都收束在 `Seller_Client` 本地受控脚本和 MCP 编排里了。

## 7. 当前建议

短期内继续保持：

1. adapter 只做基础设施控制与只读真相
2. backend 保留 seller onboarding 业务状态机
3. seller client 继续只通过 backend 获取 join material 和提交证据

如果后续要继续增强 adapter，最值得新增的是：

- 统一的节点验收聚合接口
- manager task execution 验证接口
- runtime/gateway 连通性与 target 观测接口

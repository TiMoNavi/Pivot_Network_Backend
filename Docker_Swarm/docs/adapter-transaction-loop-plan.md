# Docker Swarm Adapter 交易闭环下一阶段规划

更新时间：`2026-04-10`

## 1. 当前实现快照

当前 `Docker_Swarm_Adapter` 已经不是规划稿，而是项目当前正在使用的基础设施控制面。

目前已经真实可用的卖家接入相关能力：

- `join-material`
- 节点 `inspect / by-ref / by-compute-node-id / search`
- `claim`
- `availability`
- `remove`

目前已经真实可用的 runtime 相关能力：

- `runtime-images/validate`
- `nodes/probe`
- `services/inspect`
- `runtime-session-bundles/create`
- `runtime-session-bundles/inspect`
- `runtime-session-bundles/remove`
- `wireguard/peers/apply`
- `wireguard/peers/remove`

## 2. 当前与最新卖家客户端的对齐结论

当前 seller onboarding 正式链路固定为：

- `Seller_Client -> Plantform_Backend -> Docker_Swarm_Adapter`

并且：

- seller 不直接调用 adapter
- backend 是 adapter 的唯一正式调用方
- `join-material.manager_addr` 必须表示 `SWARM_CONTROL_ADDR`
- 当前 seller join target 必须是 `10.66.66.1:2377`

## 3. Adapter 在卖家接入中的边界

当前 adapter 只负责：

1. 提供 join material
2. 读取 manager 侧节点真相
3. 对已 join 节点执行 claim

当前 adapter 不负责：

1. 保存 onboarding session
2. 保存 `manager_acceptance`
3. 决定 seller onboarding 是否完成
4. 记录 `effective_target / truth_authority`
5. 执行 seller 本地 manager task verification

因此，当前 seller onboarding 的业务成功标准仍然必须在 backend 和 seller runtime 层收口。

## 4. 当前最需要继续补的不是“再加更多 join 接口”

基于最新代码，下一阶段最有价值的工作不是把 seller onboarding 再塞进 adapter，而是：

1. 给已有节点接口补更完整的自动化测试
2. 为 runtime bundle / gateway 接口补更稳定的联调证据
3. 明确 buyer runtime connect metadata 与 backend grant 的最终 shape
4. 视需要再考虑增加 manager task execution 只读验证接口

## 5. 下一阶段建议

### 5.1 必做

- 固化 `SWARM_MANAGER_ADDR` 与 `SWARM_CONTROL_ADDR` 的双地址语义
- 保持 `join-material` 继续输出 `10.66.66.1:2377` 这条权威 join target
- 补充 adapter 层自动化测试，覆盖：
  - `join-material`
  - `inspect by compute_node_id`
  - `claim`
  - `search`

### 5.2 可选增强

- 增加 manager-side task execution 的只读检查接口
- 增加 runtime/gateway target 观测接口
- 增加更细粒度的 connect metadata 诊断输出

## 6. 当前判断

当前 adapter 已经足够支撑最新 `Seller_Client` 的基础设施主线，不需要再把 seller onboarding 业务状态往 adapter 里硬塞。

更正确的策略是：

- adapter 继续做基础设施控制面
- backend 继续做业务真相面
- seller client 继续做本机执行与自然语言编排面

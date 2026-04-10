# CCCC Phase 1 Workplan

更新时间：`2026-04-07`

这份文档把 `Phase 1` 固定成按顺序执行的 step，不允许在 prompt 中自由改顺序。

## Step 1. 后端 seller onboarding 写链路收口

### 目标

在 `Plantform_Backend/` 已有 onboarding 基线上，对齐最终 backend contract 与验收行为。

### 目录

- `Plantform_Backend/backend_app/schemas/`
- `Plantform_Backend/backend_app/services/`
- `Plantform_Backend/backend_app/storage/`
- `Plantform_Backend/backend_app/api/`
- `Plantform_Backend/tests/`

### 建议做法

- 保持现有 seller onboarding schema / service / router，不回退成“未实现”
- 保持内存态，不先上数据库迁移
- 明确 `JoinCompleteWrite` 是 flat backend contract
- 明确 nested `local_execution / backend_locator` 不属于正式 backend ingress
- 明确 backend acceptance 走 `inspect -> claim -> inspect`
- 明确 `manager_acceptance.status` 包含 `claim_failed`

### 本 step 重点对象

- `JoinSession`
- `LinuxHostProbe`
- `LinuxSubstrateProbe`
- `ContainerRuntimeProbe`
- `NodeProbeSummary`
- `JoinCompleteWrite`
- `ManagerAcceptance`

### 本 step 成功标准

- 后端能创建 `JoinSession`
- 后端能接收 `LinuxHostProbe`
- 后端能接收 `LinuxSubstrateProbe`
- 后端能接收 `ContainerRuntimeProbe`
- 后端能接收 flat `join-complete`
- nested `local_execution / backend_locator` 会被 backend 拒绝
- claim-required 路径明确是 `inspect -> claim -> inspect`
- 后端能表达 `claim_failed`
- 后端能基于最终 inspect 结果表达“manager 识别到的是否是预期 WireGuard IP”

## Step 2. `Seller_Client` phase-1 contract / exporter 收口

### 目标

在现有 `Seller_Client/` 基线上，对齐 runtime-local contract 和 backend ingress mapping 边界。

### 目录

- `Seller_Client/seller_client_app/contracts/`
- `Seller_Client/seller_client_app/bootstrap/`
- `Seller_Client/seller_client_app/layers/`
- `Seller_Client/docs/`
- `Seller_Client/tests/`

### 建议做法

- 不要把 `Seller_Client` 当成空壳重建
- 保留 runtime-local 的嵌套 `NodeProbeSummary` / `JoinCompletePayload`
- 把 backend payload exporter / mapping 责任固定在 `Seller_Client`
- 固定 3 层：
  - `Linux Host`
  - `Linux substrate`
  - `Container Runtime`
- 固定 bootstrap 阶段：
  - `detect`
  - `prepare`
  - `install`
  - `repair`
- 只定义 probe / join 输入输出和执行边界，不做 buyer 逻辑
- 不引入 Windows 术语

### 本 step 成功标准

- `Seller_Client` 不再被文档或 prompt 描述成空壳
- runtime-local nested draft 与 backend flat ingress 的边界清楚
- exporter / mapping 责任清楚
- probe 点、join-complete 输入输出、失败回滚点可被后端契约消费

## Step 3. 对接 Adapter 现有能力

### 目标

后端与 `Seller_Client` 都围绕 Adapter 现有能力工作，不重新设计基础设施面。

### 目录

- `Plantform_Backend/backend_app/clients/adapter_client.py`
- `Plantform_Backend/backend_app/services/`
- `Seller_Client/seller_client_app/bootstrap/`
- `Docker_Swarm/Docker_Swarm_Adapter/app/routers/`

### 建议做法

- 复用已有 `join-material`
- 复用已有 `inspect`
- 复用已有 `claim`
- 复用已有 `wireguard`
- seller 本地执行真实 join
- backend 负责 `inspect -> claim -> inspect` 验收与归属
- 不设计外部 `adapter-proxy` 产品接口

### 本 step 成功标准

- 文档和 prompt 明确写出“seller client 不直连 Adapter”
- 文档和 prompt 明确写出“backend 通过 adapter client 做 inspect / claim / inspect”
- 文档和 prompt 明确写出“join-material / inspect / claim / wireguard 是 phase-1 的基础设施依赖”
- 文档和 prompt 明确写出业务成功锚点仍然是“join 后 manager 识别到预期 WireGuard IP”

## Step 4. `reviewer` 的验收职责

### 目标

`reviewer` 不做泛泛 review，只检查 phase-1 drift。

### 检查项

- 是否还残留 Windows 术语或 Windows 依赖引用
- 是否把 scope 扩散到 buyer / order / access grant 后续阶段
- 是否还把 backend onboarding 或 `Seller_Client` 写成缺失 / 空壳
- 是否把 runtime-local nested draft 混成正式 backend ingress
- 是否遗漏 `inspect -> claim -> inspect` 或 `claim_failed`
- 是否把 Swarm / WireGuard 状态当成业务真相
- 是否遗漏“manager 识别到 WireGuard IP”这个成功标准

### 本 step 成功标准

- findings 有文件定位
- findings 按严重级别排序
- 明确哪些是已验证事实，哪些仍是推断

# CCCC Phase 1 Current State

更新时间：`2026-04-07`

这份文档只提供 `Phase 1` 的已验证事实，给 CCCC 在开工前快速对齐当前项目现状。

## 1. `Plantform_Backend` 当前现状

### 1.1 已有目录与模块

当前后端主目录是：

- `Plantform_Backend/`

当前已存在并可复用的 Phase 1 核心文件：

- `Plantform_Backend/backend_app/clients/adapter_client.py`
- `Plantform_Backend/backend_app/storage/memory_store.py`
- `Plantform_Backend/backend_app/schemas/seller_onboarding.py`
- `Plantform_Backend/backend_app/services/seller_onboarding_service.py`
- `Plantform_Backend/backend_app/api/v1/seller_onboarding.py`
- `Plantform_Backend/backend_app/api/v1/router.py`
- `Plantform_Backend/tests/test_seller_onboarding_api.py`

### 1.2 已有能力

当前后端不是空白工程，seller onboarding 主链已经存在：

- 能创建 `JoinSession`
- 能接收 `LinuxHostProbe`
- 能接收 `LinuxSubstrateProbe`
- 能接收 `ContainerRuntimeProbe`
- `join-complete` 的正式 backend ingress 已锁成 flat contract
- backend acceptance 已明确走 `inspect -> claim -> inspect`
- `manager_acceptance.status` 已包含：
  - `pending`
  - `matched`
  - `mismatch`
  - `node_not_found`
  - `inspect_failed`
  - `claim_failed`
- 业务成功锚点仍然是：
  - join 后 manager 识别到的是预期 `WireGuard IP`

### 1.3 当前边界

当前后端在 Phase 1 里仍然保持这些边界：

- 继续保持内存态，不先上数据库迁移
- 不扩散到 buyer / order / access-grant 后续阶段
- 不把 Swarm / WireGuard reachability 当业务真相
- backend 才是最终验收方

### 1.4 当前结论

Phase 1 的后端工作不是“从零造后端”，而是：

- 在现有 onboarding 写链路上继续对齐 contract、claim 行为和验收表达

## 2. `Seller_Client` 当前现状

### 2.1 当前目录与模块

`Seller_Client` 不是空目录，当前已存在这些 Phase 1 表面：

- `Seller_Client/seller_client_app/contracts/phase1.py`
- `Seller_Client/seller_client_app/bootstrap/phase1.py`
- `Seller_Client/seller_client_app/bootstrap/backend_payloads.py`
- `Seller_Client/seller_client_app/layers/`
- `Seller_Client/docs/phase1-bootstrap-contract.md`
- `Seller_Client/tests/test_phase1_contracts.py`

### 2.2 已有能力

当前 `Seller_Client` 已经具备这些 Phase 1 基线：

- 固定 3 层：
  - `Linux Host`
  - `Linux substrate`
  - `Container Runtime`
- 固定 bootstrap 顺序：
  - `detect -> prepare -> install -> repair`
- 保留 runtime-local 的嵌套 `NodeProbeSummary` / `JoinCompletePayload`
- 在 `Seller_Client` 内维护 backend payload exporter / mapping 边界
- 明确 seller client 不直连 Adapter

### 2.3 当前结论

Phase 1 不应再把 `Seller_Client` 描述成“空壳”或“空骨架”。

应把它视为：

- 已存在 phase-1 contract / bootstrap / exporter / tests，需要继续按最终 backend contract 对齐

## 3. `Docker_Swarm Adapter` 当前现状

### 3.1 当前真实模块

当前已存在并可复用的模块：

- `Docker_Swarm/Docker_Swarm_Adapter/app/routers/swarm_nodes.py`
- `Docker_Swarm/Docker_Swarm_Adapter/app/routers/swarm_runtime.py`
- `Docker_Swarm/Docker_Swarm_Adapter/app/routers/wireguard.py`
- `Docker_Swarm/Docker_Swarm_Adapter/app/services/swarm_nodes.py`
- `Docker_Swarm/Docker_Swarm_Adapter/app/services/swarm_runtime.py`
- `Docker_Swarm/Docker_Swarm_Adapter/app/services/wireguard.py`

### 3.2 当前真实能力

当前已存在的能力包括：

- `/swarm/overview`
- `/swarm/nodes`
- `/swarm/nodes/search`
- `/swarm/nodes/inspect`
- `/swarm/nodes/join-material`
- `/swarm/nodes/claim`
- `/wireguard/peers/apply`
- `/wireguard/peers/remove`

### 3.3 当前结论

Phase 1 要继续复用这些基础设施能力：

- `join-material`
- `inspect`
- `claim`
- `wireguard`

不要在 phase 1 里重新设计一套基础设施控制链。

## 4. 当前基础设施事实

这些事实来自当前已验证代码与文档，应直接当作 phase-1 prompt 的输入：

- Swarm manager：`81.70.52.75`
- 当前 Swarm：单 manager 基线
- WireGuard 接口：`wg0`
- 当前成功锚点：
  - join 后 manager 识别到的是预期 `WireGuard IP`

这些事实在仓库中已有依据，例如：

- `PROJECT.md`
- `Plantform_Backend/tests/test_seller_onboarding_api.py`
- `Seller_Client/tests/test_phase1_contracts.py`
- `Docker_Swarm/docs/adapter-transaction-loop-plan.md`

## 5. Phase 1 读完这份文档后应知道什么

读完后，CCCC 应明确知道：

- backend onboarding 已存在，不是未实现
- backend `join-complete` 正式 contract 是 flat ingress
- backend acceptance 已包含 `inspect -> claim -> inspect`
- `manager_acceptance.status` 已有 `claim_failed`
- `Seller_Client` 已有 contract / bootstrap / exporter / tests
- Adapter 已经能做什么
- 当前 Swarm / WireGuard 的业务成功锚点是什么

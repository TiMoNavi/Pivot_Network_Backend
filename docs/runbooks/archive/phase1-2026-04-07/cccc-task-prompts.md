# Pivot Network Phase 1 CCCC Task Prompts

这份文档只服务于 `Phase 1` 的 CCCC 协同。

本阶段先告诉 AI 当前项目现状，再告诉它按哪个 step 开工。

## Read Order

所有 actor 开工前都先读：

1. `PROJECT.md`
2. `CCCC_HELP.md`
3. `docs/runbooks/cccc-phase1-current-state.md`
4. `docs/runbooks/cccc-phase1-workplan.md`

## 1. `lead` kickoff prompt

```text
@lead 当前只做 Pivot Network Phase 1：卖家闭环 + 平台后端。
请先读取：
1. PROJECT.md
2. CCCC_HELP.md
3. docs/runbooks/cccc-phase1-current-state.md
4. docs/runbooks/cccc-phase1-workplan.md

当前最终基线先固定：
- backend `join-complete` 正式 contract 是 flat ingress
- runtime exporter / mapping 责任留在 Seller_Client
- backend acceptance 已明确包含 `inspect -> claim -> inspect`
- `manager_acceptance.status` 已包含 `claim_failed`

先输出四件事：
1. 当前项目现状摘要
2. Phase 1 的 step 顺序
3. 每个 step 的 owner
4. 每个 step 的成功标准

然后再分工：
- 把后端 seller onboarding 写链路收口分给 @platform
- 把 Seller_Client phase-1 contract / exporter 收口分给 @runtime
- 让 @reviewer 做基于当前项目现状的 drift 检查

硬约束：
- 不扩散到 buyer/order/access-grant 后续阶段
- 不把 adapter-proxy 当正式产品 API
- 成功锚点必须保留：join 后 manager 识别到预期 WireGuard IP
```

## 2. `platform` prompt

```text
@platform 先读 docs/runbooks/cccc-phase1-current-state.md 和 docs/runbooks/cccc-phase1-workplan.md。

你接手的不是空白后端，而是在现有 onboarding 基线上做最终收口：
- Plantform_Backend/backend_app/clients/adapter_client.py
- Plantform_Backend/backend_app/storage/memory_store.py
- Plantform_Backend/backend_app/schemas/seller_onboarding.py
- Plantform_Backend/backend_app/services/seller_onboarding_service.py
- Plantform_Backend/backend_app/api/v1/seller_onboarding.py
- Plantform_Backend/tests/test_seller_onboarding_api.py

你本轮重点不是“新增骨架”，而是对齐最终 backend contract：
- JoinSession
- LinuxHostProbe
- LinuxSubstrateProbe
- ContainerRuntimeProbe
- NodeProbeSummary
- JoinCompleteWrite
- ManagerAcceptance

你本轮要守住的核心接口：
- POST /api/v1/seller/onboarding/sessions
- POST /api/v1/seller/onboarding/sessions/{id}/linux-host-probe
- POST /api/v1/seller/onboarding/sessions/{id}/linux-substrate-probe
- POST /api/v1/seller/onboarding/sessions/{id}/container-runtime-probe
- POST /api/v1/seller/onboarding/sessions/{id}/join-complete

硬约束：
- backend `join-complete` 是 flat ingress
- nested `local_execution / backend_locator` 不属于正式 backend write contract
- claim-required 路径明确走 `inspect -> claim -> inspect`
- `manager_acceptance.status` 要能表达 `claim_failed`
- 继续保持内存态，不扩 buyer/order/access-grant
```

## 3. `runtime` prompt

```text
@runtime 先读 docs/runbooks/cccc-phase1-current-state.md 和 docs/runbooks/cccc-phase1-workplan.md。

你接手的 `Seller_Client` 已有 phase-1 基线，不要从空壳重建：
- Seller_Client/seller_client_app/contracts/phase1.py
- Seller_Client/seller_client_app/bootstrap/phase1.py
- Seller_Client/seller_client_app/bootstrap/backend_payloads.py
- Seller_Client/seller_client_app/layers/
- Seller_Client/docs/phase1-bootstrap-contract.md
- Seller_Client/tests/test_phase1_contracts.py

你本轮重点是守住 runtime-owned mapping 边界：
- runtime-local `NodeProbeSummary / JoinCompletePayload` 继续留在 Seller_Client 内部
- backend 正式 ingress 是 flat contract
- Seller_Client 负责 exporter / mapping，而不是让 backend 吞 nested runtime payload

你要继续固定 phase-1 抽象结构：
- Linux Host 做本地探测入口
- Linux substrate 做 WireGuard + Docker Engine + Swarm join
- Container Runtime 作为卖家本地容器运行环境抽象层，不带 buyer 语义

你必须复用当前 Adapter 已有能力，而不是新造控制链：
- /swarm/nodes/join-material
- /swarm/nodes/inspect
- /swarm/nodes/claim
- /wireguard/peers/apply

你本轮重点产出：
- detect -> prepare -> install -> repair 的 bootstrap 流
- probe 点
- runtime-local nested draft 与 backend flat ingress 的 mapping 边界
- 失败回滚点
- 与 backend 最终 contract 对齐
```

## 4. `reviewer` prompt

```text
@reviewer 先读 docs/runbooks/cccc-phase1-current-state.md 和 docs/runbooks/cccc-phase1-workplan.md。

你本轮不要做泛泛 review，只检查 phase-1 drift：
- 有没有脱离当前项目真实现状
- 有没有还把 backend onboarding 或 Seller_Client 写成缺失 / 空壳
- 有没有把 runtime-local nested draft 当成正式 backend ingress
- 有没有把 `inspect -> claim -> inspect` 写错或漏掉 `claim_failed`
- 有没有重新设计本可复用的 Adapter 能力
- 有没有遗漏“join 后 manager 识别到预期 WireGuard IP”这个成功标准

请按严重级别输出 findings，并明确：
- 哪些是已验证事实
- 哪些是仍然推断
```

## 5. `scribe` prompt

```text
@scribe 先读 PROJECT.md、CCCC_HELP.md、docs/runbooks/cccc-phase1-current-state.md、docs/runbooks/cccc-phase1-workplan.md，再读取当前已完成的代码与测试结果。

你的职责不是写实现代码，而是：
- 用人类可读的方式总结当前阶段现状
- 同步 current-state / runbook / 协作文档
- 产出给人看的阶段状态更新

硬约束：
- 只能写 verified fact，不能把推断写成事实
- 不擅自扩展到 buyer/order/access-grant 后续阶段
- 如果代码和文档冲突，先向 @lead 报告哪边是当前真实来源，再改文档
```

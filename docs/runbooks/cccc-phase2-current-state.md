# CCCC Phase 2 Current State

更新时间：`2026-04-09`

这份文档只写当前 `Phase 2B` 的已确认事实、历史参考边界、当前缺口和新的成功标准。

## 1. 任务背景

当前 repo 的 `Phase 2` 不再是“从零开始建卖家本地壳”。

当前背景已经明确变成：

- `2A` 卖家本地 app / web / `Codex + MCP` 宿主已经落到 repo，并已留有测试与 reviewer 记录。
- 你已经明确否定“Windows 那边走 WSL 默认主线”的方案，因此 `2B` 需要按新的口径重新定义。
- 当前 `2B` 不再只看“Windows 能否接通”或“manager 是否看见 WG IP”。
- 当前 `2B` 必须升格成更完整的成功标准：
  - backend 看见真实 `join`
  - `runtime / Docker_Swarm` 完成 correction 并留证
  - backend 先完成 raw `manager` re-verify，再决定 raw matched lane 或 formal backend authoritative lane
  - 纠正后的 backend-selected target 能对卖家容器完成最小 TCP 回连验证

## 2. 当前代码状态

### 2.1 Backend 现状

当前 repo 中已存在 seller onboarding 基线：

- `Plantform_Backend/backend_app/schemas/seller_onboarding.py`
- `Plantform_Backend/backend_app/services/seller_onboarding_service.py`
- `Plantform_Backend/backend_app/api/v1/seller_onboarding.py`
- `Plantform_Backend/backend_app/storage/memory_store.py`
- `Plantform_Backend/tests/test_seller_onboarding_api.py`

当前 backend 已有这些能力：

- 创建 `JoinSession`
- 保存 `expected_wireguard_ip`
- 接收 `LinuxHostProbe`
- 接收 `LinuxSubstrateProbe`
- 接收 `ContainerRuntimeProbe`
- 接收 flat `join-complete`
- 接收 correction evidence，并把它挂回 session truth chain
- 显式重跑 `manager_acceptance` re-verify
- 在保留 raw `manager_acceptance` 的同时，记录 `manager_address_override` / `authoritative-effective-target`
- 输出 `effective_target_addr`
- 输出 `effective_target_source`
- 输出 `truth_authority`
- 接收最小 TCP validation 事实，并标记是否命中 manager-verified target
- 接收最小 TCP validation 事实，并标记是否命中 backend-selected effective target
- 执行 `inspect -> claim -> inspect`
- 输出 `manager_acceptance`
- 输出 `correction_history`
- 输出 `manager_acceptance_history`
- 输出 `minimum_tcp_validation`

当前 backend 的硬边界仍然成立：

- backend 不能远程代执行 seller 主机上的 `docker swarm join`
- backend 不能凭人工输入直接把 `manager_acceptance` 从 `mismatch` 写成 `matched`

### 2.2 Seller_Client 现状

当前 repo 中 `Seller_Client/` 已经有 phase-2 本地宿主表面：

- `Seller_Client/seller_client_app/main.py`
- `Seller_Client/seller_client_app/backend.py`
- `Seller_Client/seller_client_app/onboarding.py`
- `Seller_Client/seller_client_app/codex_session.py`
- `Seller_Client/seller_client_app/mcp_server.py`
- `Seller_Client/seller_client_app/state.py`
- `Seller_Client/seller_client_app/static/`
- `Seller_Client/bootstrap/windows/`
- `Seller_Client/scripts/`

当前 `Seller_Client` 已明确遵守这些边界：

- 仍只通过 backend 卖家接入接口工作
- 不直接调用 Adapter
- MCP 表面只提供受控动作，不暴露自由 shell

当前 `Seller_Client` 还没有这些正式能力：

- 将“本地观测成功”与“平台复验成功”明确拆开的专用引导文案

当前 `Seller_Client` 已新增这些本地受控能力：

- seller 侧本地 correction evidence surface：local API / MCP 可记录 correction 动作、观察到的 `WG / advertise / data-path` 地址、脚本/rollback/log 线索；该 surface 只记录本地事实，不表达 `manager matched`
- seller 侧本地 minimum TCP validation surface：local API / MCP 可对指定 seller target 做最小 TCP connect probe，并把结果写入 session runtime file；backend truth 与 `manager` re-verify 仍需单独 refresh / read

### 2.3 当前 focused verification

当前 repo 至少已有下列 focused verification 基线可继续使用：

- `Plantform_Backend/tests/test_seller_onboarding_api.py`
- `Seller_Client/tests/test_phase1_contracts.py`
- `Seller_Client/tests/test_phase2_app.py`
- `Seller_Client/tests/test_codex_session.py`
- `Seller_Client/tests/test_mcp_server.py`

这些测试证明：

- backend 的 seller onboarding 与 `manager_acceptance` 读面存在
- backend 的 correction / re-verify / minimum TCP validation truth slot 已存在
- seller client phase-2 本地宿主表面存在
- seller client 本地 correction evidence / TCP validation 入口已存在
- 当前 repo 不是“只有历史文档、没有 phase-2 主体代码”的状态

## 3. 当前历史参考结论

以下材料只作为 `Windows 卖家接入阶段` 的历史参考，不直接覆盖当前 repo 代码现实：

- `Pivot_backend_build_team/docs/adapter-codex-build-handoff-cn.md`
- `Pivot_backend_build_team/docs/server-ssh-to-windows-via-wireguard-2026-04-05.md`
- `Pivot_backend_build_team/backend/app/services/platform_nodes.py`

从这些材料里，可以确认 3 个参考结论：

1. `docker swarm join` 是卖家主机本地执行的  
   历史文档明确写出 seller 主机自己执行 `docker swarm join`，adapter 只负责下发 join material 和后续 claim。

2. `WireGuard connectivity` 曾真实成立过  
   历史 Windows 路径下，`10.66.66.10` 曾经对 server 可达，也曾被 buyer 路径消费。

3. 历史 buyer target 曾来自卖家本地自报  
   历史 `seller_wireguard_target` 曾通过本地上报的 `wg-seller` 地址派生出来。

同样必须明确不能误判的结论：

- `WireGuard connectivity` 成立，不等于 manager 最终按该地址识别 worker。
- 本地 `docker info .Swarm.NodeAddr = 10.66.66.10`，不等于 backend 复验一定 `matched`。
- 历史 buyer 能消费 `10.66.66.10`，不等于当前 phase2 还应允许未复验地址进入 buyer/connect 真相。

## 4. 当前缺口

当前 repo 相对于这条成功标准，仍缺这些执行证据或收口动作：

1. live Windows 证据还没有稳定闭环  
   当前用户已确认 manager 无法连到 WG 地址的问题解决了，但 Windows 侧端口连接与 Docker Desktop 仍存在波动；因此还缺一条稳定的 live `join -> correction -> re-verify -> TCP validation` 完整留证。

2. 当前控制面仍有旧 stop line 残留  
   repo 代码已经允许 raw `manager` truth mismatch 时继续走 formal backend authoritative lane，但部分文档 / task / board 仍把 raw mismatch 写成终止条件，容易让 runtime 在错误位置停住。

3. 最小 TCP validation 还缺当前轮 live Windows 回传  
   backend truth slot 与 seller 侧本地 probe 已在 repo 中存在，但当前轮 seller-side WG 路径上还没有新的最终 validation 结果写回 backend session。

## 5. 新成功标准

当前 `2B` 正式成功标准固定为：先完成 `join -> correction -> manager re-verify -> minimum TCP validation` 这条链，再落到两条允许的 closeout 之一。

1. raw manager closeout
   - backend 能看到真实 `join`
   - `runtime / Docker_Swarm` 完成 correction 并有证据
   - backend 复验后 raw `manager_acceptance = matched`
   - 用该 manager-verified target 对卖家容器做最小 TCP 回连验证成功

2. backend authoritative closeout
   - backend 能看到真实 `join`
   - `runtime / Docker_Swarm` 完成 correction 并有证据
   - backend 先完成 raw `manager` re-verify，并把 raw mismatch 保留为 truth
   - backend 通过正式 correction lane 写入 `effective_target_addr` / `truth_authority = backend_correction`
   - 用该 backend-selected effective target 对卖家容器做最小 TCP 回连验证成功

以下判断必须写死：

- `WG 通 + 本地 NodeAddr = WG IP + raw manager mismatch`，但没有 formal backend authoritative lane：失败
- `backend 已看见 join，但未纠正 / 未 re-verify`：失败
- `纠正后 raw manager matched` 或 `backend authoritative target` 已确定，但未做 TCP 回连验证：仍未完成
- `raw manager matched + 卖家容器 TCP 可达`：成功
- `truth_authority = backend_correction + effective target TCP 可达`：同样成功

## 6. 当前 blocker

当前 repo 与执行层面的 blocker 不是“完全没有 phase-2 代码”，而是：

1. Windows runtime 稳定性仍然脆弱  
   manager WG 可达问题已解决，但 Windows 侧端口连通与 Docker Desktop engine 仍可能波动；这会直接影响当前轮 live `join / correction / TCP validation` 连续留证。

2. 旧语义还在误导执行  
   repo 已有 backend authoritative effective target 与 minimum TCP validation 链路，但当前文档 / board 若继续把 raw mismatch 写成 terminal blocker，会让 runtime 错过正式收口路径。

3. 当前轮 seller-side WG path 还没有新的 verified closeout evidence  
   需要在不依赖 PICO 路径的前提下，补齐新的 live Windows run 结果，并明确它最终落在 raw manager lane 还是 backend authoritative lane。

## 7. 当前对外说明模板

当前对人说明 `2B` 状态时，应当固定使用以下表述：

- 当前 repo 已有 seller onboarding 与 `manager_acceptance` 基线，也已有卖家本地 `Codex + MCP` 宿主表面。
- 当前历史 Windows 路径证明过：Windows 本地 join、`WireGuard connectivity`、历史 buyer 目标地址都曾成立。
- 但当前 `2B` 的关键问题不再是“WG 能不能通”，而是“在 raw `manager` re-verify 之后，backend 最终选出的 target 是什么，以及该 target 能否最小回连卖家容器”。
- raw `manager_acceptance` 与 backend-selected `effective_target` 必须分开读；backend correction 可以驱动 workflow target，但不能伪造 raw matched。
- 当前 repo 已有 correction、re-verify、effective target 和 minimum TCP validation 的代码链；接下来缺的是当前轮 live Windows seller-path 留证与稳定收口。

# Pivot Network CCCC Help

更新时间：`2026-04-11`

## Phase Lock

- 当前 scope 锁定在 `phase4` 买家客户端实施规划，以及 `phase5` 闭环联调准备。
- `phase3` 卖家真实 join 与商品化现在是既有起跑线，不在这一轮重开 seller 主线设计。
- 当前唯一正式产品路线是：
  - seller 真实 join 并上架
  - buyer 通过 `grant-first + RuntimeSession` 进入 seller runtime shell，并完成 task

## Read This First

开工前必须先读：

1. `docs/runbooks/current-project-state-and-execution-guide.md`
2. `PROJECT.md`
3. `docs/runbooks/cccc-phase4-current-state.md`
4. `docs/runbooks/cccc-phase4-workplan.md`
5. `docs/runbooks/cccc-phase4-task-prompts.md`
6. `Buyer_Client/docs/phase4-buyer-client-implementation-spec-cn.md`
7. `Buyer_Client/docs/current-buyer-purchase-flow-cn.md`

只有在需要 Windows operator / tester 入口时，才再读：

1. `win_romote/windows 电脑ssh 说明.md`
2. `win_romote/windows_ssh_readme.md`
3. `docs/runbooks/cccc-tester-current-state.md`

## Current Repo State You Must Respect

- `Plantform_Backend/` 已有 seller onboarding truth chain
- `Plantform_Backend/` 已有 capability assessment 与 verified-node 商品化
- `Seller_Client/` 继续是正式 seller 本地入口
- `Buyer_Client/` 已有正式目录和买家架构文档，但仍未进入正式实现完成态
- 当前 repo 还没有这些 buyer 正式能力：
  - `grant-first` 正式接口闭环
  - `RuntimeSession` 状态机
  - buyer WireGuard / shell / workspace / task 正式链

## Locked Semantics

- seller 本地执行 `docker swarm join`
- seller 节点在 backend 侧 `verified` 后才允许进入商品化
- buyer 买的是 `RuntimeSession`，不是 seller 裸 IP
- `activate order = issue grant`
- `redeem grant + wireguard public key = create runtime session`
- buyer WireGuard lease 必须与 seller / manager 地址分 lane
- operator SSH / reverse SSH / WireGuard 远控入口只用于 deployment、diagnostics、verification

## Hard Rules

- 当前 `phase4` 从 seller 真实 join 和真实上架之后开始
- 不把 SSH/operator reachability 写成产品成功
- 不把 buyer 退回成 seller target / seller IP 模型
- 不让 buyer client 绕过 backend 直接创建 runtime bundle 或 WireGuard lease
- 不把真实 API key、auth blob、长期 bearer token 写进 repo、prompt、current-state 或 task/context

## Team Shape

- `lead`: 分解阶段、统一口径、同步 CCCC 运行态、最终收口
- `platform`: backend、auth、order、grant、runtime session、task 读模型
- `buyer`: `Buyer_Client/`、buyer MCP、buyer local state、Linux/Windows buyer flow
- `runtime`: `Docker_Swarm/`、`WireGuard`、managed runtime contract、Windows operator 验证入口
- `tester`: Windows client operator 控制、Linux 侧测试创建、手动平台 / Docker Swarm 验证操作
- `reviewer`: 语义一致性、风险审查、阶段验收
- `scribe`: current-state、人类说明、阶段摘要、Windows operator 验证记录

## Actor Focus

### `lead`

- 固定 stage 1-6 的 gating
- 保证 `PROJECT.md`、`CCCC_HELP.md`、`cccc-phase4-*`、买家实施规格一致
- 不允许跳过阶段直接宣称最终成功

### `platform`

- 落 `grant-first`、`RuntimeSession`、`TaskExecution` 读模型
- 守住 buyer WireGuard lease 与 seller truth 的分 lane
- backend 继续是 buyer session 的业务真相面

### `buyer`

- 落 `Buyer_Client` 本地 API、状态、backend client、MCP
- Linux first，再对齐 Windows
- 不提供自由 shell

### `runtime`

- 落 runtime bundle / WireGuard / managed runtime contract
- 负责 Windows operator 验证环境
- 不把 reverse SSH / WG 可达写成产品成功

### `tester`

- 先读 `docs/runbooks/cccc-tester-current-state.md` 和 Windows SSH 说明
- 只负责：
  - 在 Windows 侧通过 SSH 控制客户端并记录状态
  - 在本地 Linux 侧创建、执行、清理测试与探针
  - 为 diagnostics / verification 手动调整平台测试状态与 Docker Swarm 状态
- 每次手动修改都要记录前后状态、命令和回滚方式
- 不把 operator SSH 可达或手动改状态写成产品成功

### `reviewer`

- 审核阶段边界和成功标准
- 审核 WireGuard 网段纪律
- 审核 Windows remote control 是否被误写成产品成功

### `scribe`

- 维护 phase4 / phase5 current-state
- 维护阶段 1-6 的人类摘要
- 维护 Windows operator 入口边界说明

# Pivot Network Phase 4 / Phase 5 CCCC Task Prompts

更新时间：`2026-04-11`

这份文档只服务于当前 `phase4` 买家客户端实施与 `phase5` 闭环联调。

## Read Order

所有 actor 开工前先读：

1. `docs/runbooks/current-project-state-and-execution-guide.md`
2. `PROJECT.md`
3. `CCCC_HELP.md`
4. `docs/runbooks/cccc-phase4-current-state.md`
5. `docs/runbooks/cccc-phase4-workplan.md`
6. `Buyer_Client/docs/phase4-buyer-client-implementation-spec-cn.md`
7. `Buyer_Client/docs/current-buyer-purchase-flow-cn.md`

如果需要 Windows operator / tester 入口，再补读：

1. `docs/runbooks/cccc-tester-current-state.md`
2. `win_romote/windows 电脑ssh 说明.md`
3. `win_romote/windows_ssh_readme.md`

## 1. `lead` kickoff prompt

```text
@lead 当前只做 phase4 / phase5。
请先读取：
1. docs/runbooks/current-project-state-and-execution-guide.md
2. PROJECT.md
3. CCCC_HELP.md
4. docs/runbooks/cccc-phase4-current-state.md
5. docs/runbooks/cccc-phase4-workplan.md
6. Buyer_Client/docs/phase4-buyer-client-implementation-spec-cn.md
7. Buyer_Client/docs/current-buyer-purchase-flow-cn.md

如果需要 Windows operator / tester 入口，再读：
- docs/runbooks/cccc-tester-current-state.md
- win_romote/windows 电脑ssh 说明.md
- win_romote/windows_ssh_readme.md

你先做 4 件事：
1. 确认当前 seller 真实 join 与上架是否已达 phase4 起跑线
2. 按阶段 1-6 固定分工和 gating
3. 明确 buyer WireGuard 网段纪律，禁止 seller / manager / buyer 地址混写
4. 把最终成功标准写死为：
   - 买家在 Windows 本地通过 CodeX 自然语言描述任务
   - 可以访问 seller 容器 shell
   - 可以把任务传递并完成
```

## 2. `platform` prompt

```text
@platform 先读 docs/runbooks/cccc-phase4-current-state.md、docs/runbooks/cccc-phase4-workplan.md、Buyer_Client/docs/phase4-buyer-client-implementation-spec-cn.md。

你负责：
- order / access grant
- runtime session
- task execution 读模型
- backend 到 adapter / wireguard 的编排边界

你当前最重要的约束：
- activate order = issue grant
- redeem grant + wireguard public key = create runtime session
- buyer WireGuard lease 不能复用 seller / manager 地址
- backend 仍然是 buyer session 的业务真相面
```

## 3. `buyer` prompt

```text
@buyer 先读 Buyer_Client/docs/current-buyer-purchase-flow-cn.md、Buyer_Client/docs/phase4-buyer-client-implementation-spec-cn.md、docs/runbooks/cccc-phase4-workplan.md。

你负责：
- Buyer_Client 本地 API
- state / session files
- backend client
- buyer MCP
- Linux first 落地
- 之后再对齐 Windows

硬约束：
- 不提供自由 shell
- 不绕过 backend 直接找 seller target
- 不把 operator SSH 会话写成 buyer 产品入口
- shell / workspace / task 都必须以 RuntimeSession 为主对象
```

## 4. `runtime` prompt

```text
@runtime 先读 docs/runbooks/cccc-phase4-current-state.md、docs/runbooks/cccc-phase4-workplan.md、Buyer_Client/docs/phase4-buyer-client-implementation-spec-cn.md。

需要 Windows operator / tester 入口时，再读：
- docs/runbooks/cccc-tester-current-state.md
- win_romote/windows 电脑ssh 说明.md
- win_romote/windows_ssh_readme.md

你负责：
- Docker_Swarm_Adapter runtime bundle / WireGuard 相关配套
- Managed runtime contract
- Windows 远控验证环境

你当前硬约束：
- operator 远控 Windows 只服务于阶段 6 验证
- 不把 reverse SSH / WG reachability 写成产品成功
- buyer WireGuard lease 必须和 seller / manager 地址分 lane
```

## 5. `reviewer` prompt

```text
@reviewer 先读 docs/runbooks/cccc-phase4-current-state.md、docs/runbooks/cccc-phase4-workplan.md、Buyer_Client/docs/phase4-buyer-client-implementation-spec-cn.md。

你要重点检查：
- 各阶段能力边界是否被越权
- 各阶段成功标准是否可验证
- buyer WireGuard 网段是否和 seller / manager 混写
- 是否把 operator 远控 Windows 错写成产品成功标准
- 是否把 buyer 产品语义退回成 seller target / seller IP
```

## 6. `scribe` prompt

```text
@scribe 先读 docs/runbooks/current-project-state-and-execution-guide.md、PROJECT.md、CCCC_HELP.md、docs/runbooks/cccc-phase4-current-state.md、docs/runbooks/cccc-phase4-workplan.md、Buyer_Client/docs/phase4-buyer-client-implementation-spec-cn.md。

你的职责是：
- 维护 phase4 / phase5 的 current-state
- 维护阶段 1-6 的人类摘要
- 维护 Windows operator 入口边界说明
- 维护最终成功标准的对外表述
```

## 7. `tester` prompt

```text
@tester 先读：
1. PROJECT.md
2. CCCC_HELP.md
3. docs/runbooks/cccc-phase4-current-state.md
4. docs/runbooks/cccc-tester-current-state.md
5. win_romote/windows 电脑ssh 说明.md
6. win_romote/windows_ssh_readme.md

你只负责：
- 在 Windows 侧通过 SSH 控制客户端并记录当前状态
- 在本地 Linux 侧创建、执行、清理测试与探针
- 为 diagnostics / verification 手动调整平台测试状态与 Docker Swarm 状态

你当前硬约束：
- 不把 operator SSH 可达写成产品成功
- 不把手动改平台状态写成业务真相
- 不越权接管 buyer / platform / runtime 的产品语义设计
- 每次手动修改平台或 Swarm 状态，都要记录修改前状态、命令、修改后状态和回滚方式
```

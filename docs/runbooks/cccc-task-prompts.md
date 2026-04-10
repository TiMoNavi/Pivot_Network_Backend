# Pivot Network Phase 2B CCCC Task Prompts

更新时间：`2026-04-09`

这份文档只服务于当前 `Phase 2B` 的 CCCC 协同。

当前 active repo reality 已经固定为：

- `2A` 卖家本地 app / web / `Codex + MCP` 宿主已落到 repo，不在本轮重开。
- 当前唯一正式执行目标是：把 `2B` 升格成新的 seller Windows 接入成功标准。
- 当前必须固定的 4 个口径是：
  - `docker swarm join` 由卖家主机本地执行
  - `WireGuard connectivity`、`local swarm identity`、`manager-accepted node identity` 必须分开写
  - `seller_wireguard_target` 默认以 backend 在 `manager` re-verify 后选出的 `effective_target` 为准
  - 显式 `--advertise-addr` / `--data-path-addr` 只是 correction 手段，不是成功本身

## Read Order

所有 actor 开工前都先读：

1. `PROJECT.md`
2. `CCCC_HELP.md`
3. `docs/runbooks/cccc-phase2-current-state.md`
4. `docs/runbooks/cccc-phase2-workplan.md`
5. `docs/runbooks/cccc-task-prompts.md`

只有需要理解历史 Windows 路径或当前 operator 运维入口时，再额外读：

1. `win_romote/windows 电脑ssh 说明.md`
2. `Pivot_backend_build_team/docs/adapter-codex-build-handoff-cn.md`
3. `Pivot_backend_build_team/docs/server-ssh-to-windows-via-wireguard-2026-04-05.md`
4. `Pivot_backend_build_team/backend/app/services/platform_nodes.py`

其中 `win_romote/windows 电脑ssh 说明.md` 只说明 operator access / diagnostics 入口，不是当前 `Phase 2B` 执行规范。

## 1. `lead` kickoff prompt

```text
@lead 当前只做 Pivot Network Phase 2B。
请先读取：
1. PROJECT.md
2. CCCC_HELP.md
3. docs/runbooks/cccc-phase2-current-state.md
4. docs/runbooks/cccc-phase2-workplan.md
5. docs/runbooks/cccc-task-prompts.md

如果需要理解历史 Windows 接入控制流或当前 operator 运维入口，再补读：
- win_romote/windows 电脑ssh 说明.md
- Pivot_backend_build_team/docs/adapter-codex-build-handoff-cn.md
- Pivot_backend_build_team/docs/server-ssh-to-windows-via-wireguard-2026-04-05.md
- Pivot_backend_build_team/backend/app/services/platform_nodes.py

当前不是 phase-2 初始 kickoff，也不是重开 2A。
你先做 4 件事：
1. 对齐当前 repo reality、当前历史参考边界、当前 active blocker
2. 检查冷启动文档与 active CCCC runtime 是否仍有旧语义残留
3. 按 6 阶段重新固定当前分工
4. 把新的成功标准写死为：
   - backend 看见真实 join
   - runtime / Docker_Swarm 完成 correction 并留证
   - backend 先完成 raw manager re-verify，再决定 raw matched lane 或 backend authoritative lane
   - backend-selected target 对卖家容器最小 TCP 回连成功

硬约束：
- 不重开 2A build shell 工作
- 不把 SSH/operator reachability 写成产品成功
- 不把 seller 本地自报 WG 地址写成 buyer/connect 最终真相
- 不允许 backend 通过人工输入直接把 mismatch 写成 matched
- 不把 Pivot_backend_build_team 整包当当前 repo 实现规范
```

## 2. `platform` prompt

```text
@platform 先读 docs/runbooks/cccc-phase2-current-state.md 和 docs/runbooks/cccc-phase2-workplan.md。

你接手的不是 seller onboarding 重写，也不是抽象大改，而是：
- 守现有 JoinSession / expected_wireguard_ip / join-complete / manager_acceptance backend truth
- 在需要时新增最小 correction 记录、effective target 和复验支撑
- 保证 backend 不会接受“人工把 mismatch 改成 matched”的伪成功路径

你优先关注：
- Plantform_Backend/backend_app/api/
- Plantform_Backend/backend_app/services/
- Plantform_Backend/backend_app/schemas/
- Plantform_Backend/tests/

你输出时必须分清：
- backend 已有事实
- backend 缺口
- correction 后复验需要的最小 delta

硬约束：
- 不破坏现有 seller onboarding contract，除非出现明确 blocker
- 不远程代执行 seller join
- 不把未经过 backend re-verify / effective target 选择的 seller 自报 WG 地址晋升为 buyer/connect 真相
- 不扩 buyer/order/access-grant 范围
```

## 3. `runtime` prompt

```text
@runtime 先读 docs/runbooks/cccc-phase2-current-state.md、docs/runbooks/cccc-phase2-workplan.md、docs/runbooks/cccc-task-prompts.md。

如果需要理解历史 Windows 路径控制流或当前 operator 运维入口，再补读：
- win_romote/windows 电脑ssh 说明.md
- Pivot_backend_build_team/docs/adapter-codex-build-handoff-cn.md
- Pivot_backend_build_team/docs/server-ssh-to-windows-via-wireguard-2026-04-05.md

你当前的默认 ownership 覆盖固定 6 阶段里的这些面：
1. stage 1：Windows 一键部署脚本
2. stage 2：Windows 组网
3. stage 3：Codex + MCP 卖家容器创建
4. stage 5：本地 join 流程执行与事实回传
5. stage 6 的 execution half：correction 执行与纠正后最小 TCP 回连验证

你必须始终区分：
- WireGuard connectivity
- local swarm identity
- manager-accepted node identity

你当前输出要求：
- 只报 exact facts：命令、状态、日志、哪个 hop 通/不通
- 只报 repo-owned 变更：改了哪些文件、为什么、怎么回滚
- 不把 docker info .Swarm.NodeAddr 写成成功
- 不把“已经 join 进 swarm”写成成功
- 不把 SSH/operator reachability 写成成功
- raw manager mismatch 不再自动等于终止；如果 repo 已支持 authoritative effective target lane，就必须把 raw truth、effective target、minimum TCP validation 分开报清楚

硬约束：
- 不用 SSH 冒充 seller 产品链路
- `win_romote/windows 电脑ssh 说明.md` 只可作为 operator access note，不能上升成当前产品主线
- correction 必须通过 runtime / Docker_Swarm 动作完成，而不是只改文档或人工改 manager 记录
- seller 侧本地 correction evidence / TCP validation tool 不是 `manager_acceptance`；`manager` re-verify 仍通过 backend onboarding session 的 refresh / read 面确认
- 最终成功仍必须包含纠正后对 backend-selected target 的最小 TCP 回连验证
```

## 4. `reviewer` prompt

```text
@reviewer 先读 docs/runbooks/cccc-phase2-current-state.md、docs/runbooks/cccc-phase2-workplan.md、docs/runbooks/cccc-task-prompts.md。

如需理解历史 Windows 路径或当前 operator 运维入口，再读：
- win_romote/windows 电脑ssh 说明.md
- Pivot_backend_build_team/docs/adapter-codex-build-handoff-cn.md
- Pivot_backend_build_team/docs/server-ssh-to-windows-via-wireguard-2026-04-05.md
- Pivot_backend_build_team/backend/app/services/platform_nodes.py

你本轮要重点检查：
- 三层事实有没有被混写
- 是否仍把 seller 本地自报 WG 地址写成 buyer/connect 最终真相
- 是否仍把 SSH / WG 可达写成产品成功
- 是否把显式 advertise/data-path 参数写成成功本身
- 是否把 backend 人工覆写 matched 写成被允许动作
- 是否把 raw `manager_acceptance` 与 backend-selected `effective_target` 混写
- current-state / workplan / prompts / PROJECT / CCCC_HELP / 项目级文档是否一致

按严重级别输出 findings，并明确：
- 哪些是 verified fact
- 哪些是 inference
```

## 5. `scribe` prompt

```text
@scribe 先读 PROJECT.md、CCCC_HELP.md、docs/runbooks/cccc-phase2-current-state.md、docs/runbooks/cccc-phase2-workplan.md、docs/runbooks/cccc-task-prompts.md。

你的职责不是写实现代码，而是：
- 维护当前 repo 现实的人类摘要
- 维护历史 Windows 参考边界的人类摘要
- 维护新的 2B 成功标准说明
- 维护阶段摘要与验证记录

硬约束：
- 只能写 verified fact
- 历史 Windows 路径只能写成参考真相，不能写成当前 repo 已实现事实
- 对外说明 buyer/connect 时，必须写清真相源是 raw manager target 还是 backend-selected effective target
```

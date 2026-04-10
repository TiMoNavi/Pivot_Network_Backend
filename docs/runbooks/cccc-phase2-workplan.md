# CCCC Phase 2B Workplan

更新时间：`2026-04-09`

这份文档把当前 `Phase 2B` 固定成 6 个阶段，不允许在 prompt 中自由改序。

## 阶段 1. 一键部署脚本

### 任务内容

定义 Windows 卖家的一键部署入口，覆盖：

- 环境检查
- 环境安装
- 客户端安装

### 改动面

- `Seller_Client/bootstrap/windows/`
- `Seller_Client/scripts/`
- `docs/runbooks/cccc-phase2-current-state.md`
- `docs/runbooks/cccc-task-prompts.md`

### 任务能力边界

- 这一步只负责本地准备与受控依赖安装。
- 不能把“脚本跑完”写成 `join` 成功。
- 不能把“脚本跑完”写成 manager 已按 `WireGuard IP` 识别 worker。

### 完成标准

- 文档明确写清：
  - 启动入口
  - 输入输出
  - 依赖检查
  - 日志位置
  - 失败分层
- `runtime` 能按文档直接知道去哪里改 Windows 部署资产。

### 执行思路建议

- 参考历史 `Pivot_backend_build_team/environment_check/install_windows.ps1` 与 seller 安装器设计。
- 只保留当前 phase2 真正需要的最小面，不把历史整套 seller-client 结构整包搬回。

## 阶段 2. Win 上组网

### 任务内容

把 Windows 卖家接入阶段的网络准备拆成独立阶段，明确它解决的是：

- `WireGuard connectivity`
- Windows 到平台必需网络前提

### 改动面

- `Seller_Client/`
- `wireguard/`
- `docs/runbooks/cccc-phase2-current-state.md`
- `docs/runbooks/cccc-task-prompts.md`

### 任务能力边界

- 不能把“WG 通了”写成“manager 已按 WG IP 认 worker”。
- 不能把 operator SSH / reverse SSH 写成产品成功标准。
- 不能把历史 `wg-seller` watchdog 直接写成当前产品功能。

### 完成标准

- 文档明确区分：
  - `WireGuard connectivity`
  - `local swarm identity`
  - `manager-accepted node identity`
- 文档明确说明 seller/server/buyer 经 `10.66.66.x` 可达，与 manager 识别 worker 地址是两件事。

### 执行思路建议

- 历史 `wg-seller`、watchdog、reverse SSH 只作为运维参考资产引用。
- 当前 phase2 中，网络阶段只负责把“可达性事实”准备好，不提前宣称平台成功。

## 阶段 3. Win 上 `Codex + MCP` 用自然语言帮小白卖家创建容器

### 任务内容

定义 seller 侧“自然语言驱动容器创建”阶段，明确：

- `Codex + MCP` 只调受控工具
- 产出的是本地 runtime / container 就绪事实

### 改动面

- `Seller_Client/seller_client_app/`
- `Seller_Client/tests/`
- `docs/runbooks/cccc-task-prompts.md`

### 任务能力边界

- 不暴露自由 shell
- 不让 `Seller_Client` 直调 Adapter
- 不把 buyer 逻辑带进来
- 不把本地容器成功写成 manager 验收成功

### 完成标准

- 文档明确说明这一步只生成本地 runtime/container 就绪事实。
- 文档明确说明本地容器成功不等于 backend / manager 已复验通过。

### 执行思路建议

- 参考历史 `Pivot_backend_build_team/seller_client/agent_mcp.py` 的本地 Docker/WireGuard 工具思想。
- 收敛到当前 repo 的受控 MCP 表面，不引入自由命令执行。

## 阶段 4. 平台后端创建 join 接入材料

### 任务内容

定义 backend 在卖家接入中的责任：

- 创建 `JoinSession`
- 下发 join-material
- 保存 `expected_wireguard_ip`
- 保存 correction 相关事实

### 改动面

- `Plantform_Backend/backend_app/api/`
- `Plantform_Backend/backend_app/services/`
- `Plantform_Backend/backend_app/schemas/`
- `Plantform_Backend/tests/`
- `docs/runbooks/cccc-phase2-current-state.md`
- `docs/runbooks/cccc-task-prompts.md`

### 任务能力边界

- backend 不负责远程代执行 seller join
- backend 不直接充当 Swarm 控制器
- backend 不能凭人工把 `mismatch` 写成 `matched`

### 完成标准

- 文档明确 backend 当前已有 seller onboarding 基线。
- 如需新增能力，只能是 correction 记录、effective target、复验与最小 TCP validation 支撑，不是重做整套 onboarding。
- 文档明确 `expected_wireguard_ip`、`join-complete`、raw `manager_acceptance`、`effective_target_addr/source` 属于同一条 backend truth chain。

### 执行思路建议

- 继续沿用当前 `inspect -> claim -> inspect` 语义。
- correction 完成后仍回到同一条 backend truth chain 做复验，不单独创造“手工成功”路径。

## 阶段 5. Win 上 `Codex + MCP` 用自然语言帮用户完成 join 流程

### 任务内容

定义卖家端如何在本地执行 join、采集事实并提交：

- `observed_wireguard_ip`
- `observed_advertise_addr`
- `observed_data_path_addr`
- `join-complete`

### 改动面

- `Seller_Client/`
- `Seller_Client/tests/`
- `docs/runbooks/cccc-phase2-current-state.md`
- `docs/runbooks/cccc-task-prompts.md`

### 任务能力边界

- 本地 `docker info .Swarm.NodeAddr` 只算观察事实，不等于成功。
- `join seen by backend` 不等于 `manager-accepted node identity`。
- 不允许把 seller 自报成功误写成平台成功。

### 完成标准

- 文档明确把以下两件事拆开写：
  - backend 已看见真实 `join`
  - manager 已复验通过
- 文档明确 seller 本地观测值、backend truth、manager 复验结果之间的区别。

### 执行思路建议

- 允许引用历史 Windows 路径帮助理解本地 join 控制流。
- 所有对外成功判断都必须回到当前 backend truth。

## 阶段 6. 平台后端或 Docker Swarm 再次纠正 WireGuard IP

### 任务内容

把地址纠正阶段正式写成 `2B` 的关键阶段：

- `runtime / Docker_Swarm` 主导实际 correction
- backend 保存 correction 记录
- backend 复跑 raw `manager` 验收
- 必要时通过正式 backend correction lane 选出 `effective_target`
- 对 backend-selected target 做最小 TCP 回连验证

### 改动面

- `Docker_Swarm/`
- `Seller_Client/`
- `Plantform_Backend/`
- `docs/runbooks/cccc-phase2-current-state.md`
- `docs/runbooks/cccc-task-prompts.md`

### 任务能力边界

- 不能把“人工把 manager 记录改掉”写成成功。
- 必须有对应的 correction 动作与复验证据。
- 不能把显式 `--advertise-addr` / `--data-path-addr` 当成成功本身。
- seller 侧本地 correction evidence / TCP validation tool 不是 `manager_acceptance`；`manager` re-verify 仍通过 backend onboarding session 的 refresh / read 面确认。
- raw `manager` mismatch 只有在 formal backend authoritative lane 已落到 `effective_target` 并继续完成最小 TCP validation 时，才不再是 terminal blocker。

### 完成标准

- backend 看见真实 `join`
- correction 已执行并留证
- backend 完成 raw `manager` re-verify
- `buyer/connect` 目标地址只取 backend 选出的 `effective_target`
- 满足以下两条之一：
  - raw `manager_acceptance` 从 `mismatch` 变为 `matched`，并通过该地址对卖家容器的最小 TCP 探测成功
  - raw mismatch 被保留为 truth，但 backend 通过正式 authoritative lane 写入 `effective_target_addr` / `truth_authority=backend_correction`，并通过该 effective target 对卖家容器的最小 TCP 探测成功

### 执行思路建议

- 把显式 `--advertise-addr` / `--data-path-addr` 写成优先 correction path。
- 若 correction 后 raw `manager` 仍不匹配，先完成 raw re-verify，再决定是否进入 formal backend authoritative lane；不要跳过复验，也不要伪造 matched。

## Reviewer / Scribe 收口要求

### reviewer

- 只按新的 `2B` 成功标准做验收
- findings 优先
- 明确区分 `verified fact` 与 `inference`

### scribe

- 维护 current-state、人类说明、阶段摘要
- 只写 verified fact
- 历史 Windows 路径只能写成参考真相，不写成当前 repo 既成事实

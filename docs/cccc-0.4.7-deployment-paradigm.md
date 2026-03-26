# CCCC 0.4.7 官方部署范式与本项目映射

> 记录日期：2026-03-24
> 目标：把 CCCC `0.4.7` 的官方部署建议，整理成适合本项目后续执行和对照的文档。

## 文档边界

这份文档刻意区分 3 类信息：

- `官方明确`：直接来自官方 README、Docker Deployment、Operations Runbook、Architecture、Release Notes，或官方仓库源码中明确存在的机制。
- `项目映射`：结合本仓库现状，对官方机制在本项目中的落点做的对应说明。
- `推断`：根据官方能力和本项目现状做的工程判断，不把它写成“官方强制要求”。

## 官方版本基线

### 官方明确

- 当前稳定版是 `cccc-pair 0.4.7`。
- PyPI 上 `0.4.7` 的 wheel 上传时间是 `2026-03-23T08:20:48.971786Z`。
- `v0.4.7` 相比 `v0.4.6` 的主要变化，是：
  - `Presentation` 成为正式共享工作面。
  - Chat 与 Presentation 建立引用关系。
  - task workflow 处理更严格。
  - Web 品牌化与交互有一轮整理。
  - 启动路径对 `--host` / `--port` 的处理更一致。

### 推断

`0.4.7` 是一次“工作面与工作流收紧”的升级，不是一次“推翻原有部署模型”的升级。也就是说，官方推荐的基础部署范式仍然是 `daemon + thin ports + CCCC_HOME + working group` 这一套。

## 官方建议部署范式

### 1. 以 daemon 作为唯一控制平面

### 官方明确

- CCCC 的核心是单个 daemon。
- daemon 是 `single writer`，所有状态写入都经过 daemon。
- ledger 是 append-only 的单一事实源。
- Web UI、CLI、MCP、IM bridge 都只是入口，不自己持有业务真相。

### 这意味着什么

- 不能把协作状态散落在多个脚本、多个临时文档树、多个“各自维护的真相源”里。
- 如果一个协作动作需要可恢复、可追踪、可审计，就应该通过 group/actor/message/task/help/presentation 这一套落到 daemon 管辖的状态里。

## 2. 运行态放在 `CCCC_HOME`，repo 只是 scope

### 官方明确

- 默认运行态目录是 `CCCC_HOME=~/.cccc`。
- 关键运行态文件在 `CCCC_HOME` 下，例如：
  - `registry.json`
  - `daemon/ccccd.sock`
  - `daemon/ccccd.log`
  - `groups/<group_id>/group.yaml`
  - `groups/<group_id>/ledger.jsonl`
- 官方架构说明强调：运行态应该留在 `CCCC_HOME`，而不是直接混进 repo。
- Docker 部署时，官方推荐把：
  - `/data` 挂载给 `CCCC_HOME`
  - `/workspace` 挂载给项目目录

### 这意味着什么

- 项目源码和 CCCC 运行态要分层。
- 项目目录负责代码、文档、脚本和业务资产。
- `CCCC_HOME` 负责 group、ledger、prompt override、presentation、runtime state、inbox、blob 等协作运行态。

## 3. working group 是协作主单位

### 官方明确

- working group 是核心组织单位。
- 每个 group 有自己的 ledger、context、state、actors、scope。
- 第一个启用的 actor 自动成为 foreman。
- 官方 best practices 建议：
  - 在项目根放 `PROJECT.md` 作为项目 constitution。
  - 用 group help playbook 作为协作契约。
- 官方源码里存在 `cccc.group_template` 合同与 `group_create_from_template` / `group_template_import_replace` / `group_template_preview` 机制，说明 group template 是官方支持的一等能力。

### 推断

- 官方文档对外更强调 `PROJECT.md + help + working group`，对 group template 的公开叙述没有 README 那么突出。
- 但从官方源码能力看，group template 很适合做“可重复、可移植、项目级”的工作组固化。
- 因此，项目级协作配置采用 group template 是合理的 0.4.x 落地方式。

## 4. Docker 是面向服务器、团队、可复现环境的推荐部署方式

### 官方明确

- Docker Deployment 文档明确把 Docker 容器运行方式描述为适合 servers、teams、reproducible environments。
- 官方镜像内会准备 Python、Node.js 和多个 agent CLI。
- 官方推荐的最小核对命令是：
  - `docker logs <container>`
  - `docker exec <container> cccc doctor`

### 这意味着什么

- 如果目标是多次重启仍可恢复、多人协作时状态不乱、环境可复制，那么 Docker 化运行 CCCC 是官方正路之一。
- 如果只是本机临时单人实验，直接本地安装也可以，但项目长期协作更适合容器或至少固定 wrapper。

## 5. 远程访问默认收紧，不裸露 Web

### 官方明确

- 非本地暴露前，要先在 Web Access 中创建 `Admin Access Token`。
- 官方建议把非本地访问放在 `Cloudflare Access` 或 `Tailscale` 这类边界后面。
- Docker 示例把宿主机端口默认绑在 `127.0.0.1:8848`，刻意先保持 localhost-only。
- 运行手册明确反对直接把 Web UI 裸露到公网。

### 这意味着什么

- 官方部署思路不是“先暴露，再补安全”，而是“先本地或私网，确认 Access Token，再决定是否远程暴露”。

## 6. 运维上强调健康检查、备份、升级前后核验

### 官方明确

- 日常健康检查基线：
  - `cccc doctor`
  - `cccc daemon status`
  - `cccc groups`
- 升级前：
  - 停掉高风险会话。
  - 备份 `CCCC_HOME`。
  - 记录当前版本与 smoke 状态。
- 升级后：
  - 再跑 `cccc doctor`
  - 再跑 `cccc daemon status`
  - 再跑 `cccc mcp`
  - 再做一个小型 end-to-end smoke

### 这意味着什么

- 官方把 CCCC 当成“有状态协作基础设施”，不是一次性脚本。
- 升级、恢复、备份都应该围绕 `CCCC_HOME` 来做。

## 本项目当前如何落这套范式

## 1. 项目把 CCCC 当成协作控制平面，而不是业务运行时

### 项目映射

- 本项目当前唯一主线是：`后端真实接上 Docker Swarm`。
- 当前阶段蓝图明确要求一次只做这一条主线，不把 `Pricing`、`AI Benchmark`、订单闭环等内容混进来。
- 这条主线已经被拆成 8 步阶段任务，保存在 `docs/project_backups/2026-03-24-project-8step-blueprint.md`。

### 作用

CCCC 在这里负责的是：

- 让 8 步主线有可恢复的协作骨架。
- 让 actor 分工、消息流、停点、文档同步有统一控制平面。
- 让“谁在推进哪一步、依据什么事实推进、卡在哪”不只存在于终端滚动输出里。

它现在还不负责替代真正的 Swarm adapter 业务代码。

## 2. 本项目已经把 working group 固化成项目模板

### 项目映射

仓库里的 `CCCC/templates/pivot-backend-build-team.group-template.yaml` 已经把当前项目的协作模型固化为：

- `lead`
- `swarm_cli`
- `backend_adapter`
- `verification`
- `docs_summary`

并固定了：

- `cccc_version: 0.4.7`
- delivery / nudge / transcript 相关 settings
- preamble
- help playbook
- 当前主线边界
- actor ownership
- 对 Docker Swarm 写操作先做安全检查的要求

### 作用

这意味着本项目不是“临时拉几个 agent 聊天”，而是已经把当前阶段的协作 contract 模板化了。后续只要 group 重建或迁移，就可以复现同一套工作组结构。

## 3. 本项目通过 wrapper 把官方 runtime 变成“项目本地运行态”

### 项目映射

- `CCCC/run-cccc.sh` 会把 `CCCC_HOME` 指向 `.cccc/runtime/cccc-home`。
- `.gitignore` 已忽略 `.cccc/runtime/`，所以运行态不会进入版本控制。
- `tests/test_cccc_layout.py` 还专门验证了这件事。

### 推断

这不是官方默认值。官方默认仍然是 `~/.cccc`。

但这是一种合理的项目本地化封装，因为它同时满足了两件事：

- 运行态仍然和 repo 提交历史分离。
- 项目成员进入仓库后可以用统一 wrapper 启动，不依赖每个人各自维护一套 `~/.cccc` 约定。

## 4. 本项目已经把 group 生命周期脚本化

### 项目映射

- `CCCC/cccc-start.sh` 会：
  - 启动 daemon
  - 解析或创建 group
  - attach 项目根目录
  - 同步 group title/topic
  - apply group template
  - 检查并启动 required actors
  - 拉起 Web UI
  - 做 actor health 和 web health 检查
- `CCCC/apply_group_template.py` 直接调用官方 daemon 操作：
  - `group_create_from_template`
  - `group_template_import_replace`
  - `group_template_preview`

### 作用

这说明本项目不是自己模拟一套“伪模板机制”，而是直接调用官方模板能力来管理工作组。

## 5. 本项目当前还没有完全对齐官方 best practices 的地方

### 项目映射

- 仓库根目前没有正式的 `PROJECT.md`。
- 现阶段主要依靠：
  - 备份蓝图
  - group template 中的 preamble/help
  - `docs/cccc-collaboration.md`

### 推断

这套方式已经能工作，但还不是官方 best practices 里最标准的形态。后续如果要继续长期使用 CCCC，建议补一份仓库根 `PROJECT.md`，把：

- Goal
- Constraints
- Architecture
- Current Focus

收口成正式项目宪法。

## 本项目里，这个范式如何作用于 8 步阶段任务

## 步骤 1 到 3：事实建立阶段

### 项目映射

- `swarm_cli` 负责 Docker / Swarm 拓扑、manager / worker、节点标签、join token、inspect 证据。
- `verification` 负责核对“已验证事实”和“推断”。

### 作用

CCCC 在这一阶段的主要价值是：

- 让 CLI 证据不只散落在终端。
- 让节点安全边界、manager 保护规则、当前真实拓扑能被 group 持久记住。

## 步骤 4 到 5：后端接通阶段

### 项目映射

- `backend_adapter` 负责把 backend 真实接上 Docker Swarm，并逐步实现最小后端原语。
- `verification` 负责判断“真实接通”是否只是把 stub 换皮，还是已经满足诚实 contract。

### 作用

CCCC 在这一阶段承担的是“实现过程治理”：

- 控范围
- 保证安全前置检查
- 保证 stub 路径没有被误打碎
- 保证真实能力和文档说法一致

## 步骤 6 到 8：组合链路与验收阶段

### 项目映射

- `lead` 负责把原语组合成链路，并决定下一步 acceptance。
- `docs_summary` 负责把阶段结果同步进 `docs/`，不夸大完成度。
- `verification` 负责真实停点与风险说明。

### 作用

CCCC 在这一阶段的关键价值是：

- 把“已经完成什么”和“还没完成什么”固定在 group 协作状态里。
- 避免出现“口头上说已经接通 Swarm，实际上只有局部 stub 或半成品”的失真。

## 当前最重要的工程判断

### 1. `0.4.7` 新能力现在还没有被本项目充分用起来

### 官方明确

`0.4.7` 最显著的新能力是 `Presentation` 工作面和更严格的 task workflow。

### 项目映射

当前仓库里已经使用了 group template、actor 分工、help/preamble，但还没有明显接上 presentation 的项目级用法。

### 推断

后续如果项目继续深用 CCCC，最适合优先接上的 `0.4.7` 新能力不是“再多起几个 agent”，而是：

- 用 Presentation 挂阶段图、拓扑图、Portainer 截图、验收证据。
- 用更严格的 task workflow 管理 8 步主线，而不是只依赖聊天。

## 2. 本项目当前 Web 绑定策略比官方默认更宽

### 官方明确

官方 Docker 示例默认把宿主机端口绑定到 `127.0.0.1:8848`。

### 项目映射

项目脚本里的默认值是：

- `CCCC_WEB_HOST=0.0.0.0`
- `CCCC_WEB_PORT=8848`

### 推断

如果这台机器不只是个人可信环境，后续应考虑把默认绑定策略收紧，或者至少补上明确的 Access Token / 私网边界操作文档。

## 推荐的下一步收敛

- 补仓库根 `PROJECT.md`，把当前 8 步蓝图压缩成官方 best practices 所需的 constitution。
- 保留当前 group template 方案，因为它已经很好地承接了本项目的阶段分工。
- 继续把 `docs/project_backups/2026-03-24-project-8step-blueprint.md` 作为阶段蓝本，但不要再回退到旧的多层任务文档树。
- 如果后续要长期运行或多人共用，明确写一份“本项目 CCCC 启动/状态/停止/备份/升级/远程访问”操作手册。
- 如果要吃到 `0.4.7` 的增量价值，优先考虑把阶段证据接到 Presentation，而不是只停留在聊天里。

## 参考来源

官方来源：

- PyPI `cccc-pair`: <https://pypi.org/project/cccc-pair/>
- 官方 README: <https://github.com/ChesterRa/cccc>
- Docker Deployment: <https://chesterra.github.io/cccc/guide/getting-started/docker.html>
- Operations Runbook: <https://chesterra.github.io/cccc/guide/operations.html>
- Architecture: <https://chesterra.github.io/cccc/reference/architecture.html>
- `v0.4.7` Release Notes: <https://github.com/ChesterRa/cccc/blob/main/docs/release/v0.4.7_release_notes.md>

官方源码能力：

- `src/cccc/contracts/v1/group_template.py`
- `src/cccc/kernel/group_template.py`
- `src/cccc/daemon/ops/template_ops.py`

本项目本地落点：

- `CCCC/templates/pivot-backend-build-team.group-template.yaml`
- `CCCC/run-cccc.sh`
- `CCCC/cccc-start.sh`
- `CCCC/cccc-control-common.sh`
- `CCCC/apply_group_template.py`
- `docs/cccc-collaboration.md`
- `docs/swarm-adapter-progress.md`
- `docs/project_backups/2026-03-24-project-8step-blueprint.md`

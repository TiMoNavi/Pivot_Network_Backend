# 买家云主机会话架构设计说明

更新时间：`2026-04-11`

## 1. 文档定位

这份文档是 `Buyer_Client`、`Plantform_Backend`、`Docker_Swarm_Adapter`、`WireGuard` 后续买家链路实现的正式规格来源。

本轮只定文档，不做代码实现。

如果需要直接看 `phase4` 的实施分阶段方案，再读：

- `Buyer_Client/docs/phase4-buyer-client-implementation-spec-cn.md`

本文档要解决的不是“买家能不能买算力”这种抽象问题，而是下面这些可直接指导开发的问题：

- 买家产品主语义到底是什么
- 平台前端、本地 buyer client、backend、adapter、wireguard、runtime 各自负责什么
- 买家的完整链路应该怎么走
- 后续每个模块需要增加什么能力
- 实现顺序怎么排
- 每个阶段怎么判断成功

## 2. 核心结论

本项目后续买家架构以以下结论为准：

- 用户产品语义：`云主机会话`
- 内部基础设施语义：`RuntimeSession = runtime bundle`
- 正式连接方式：`WireGuard 优先`
- 正式 shell 入口：`仅本地 buyer client`
- 平台前端继续按“云主机路线”展示和下单
- 一键任务运行是 `RuntimeSession` 内的增强能力，不替代会话本身

换句话说：

- 买家买的不是 seller 裸机器
- 买家也不是直接拿到 seller IP
- 买家买到的是一个可进入远程 shell 的会话
- 这个会话在平台内部由 `runtime service + gateway service + session network + buyer wireguard lease` 承载

## 3. 为什么是“云主机会话”，不是纯任务平台

当前产品与前端现实更适合“云主机会话”路线，原因有 4 个：

1. 你的前端已经按云主机路线准备
2. 你明确要求必须保留“可远程进入容器 shell”的能力
3. 买家不只是想点一次任务，还需要进入环境、看目录、调命令、复查问题
4. `CodeX` 的一键运行更适合定义为“在当前会话里帮用户完成上传和执行”，而不是替代整个会话模型

因此，推荐的层次关系是：

- 用户层：`云主机会话`
- 基础设施层：`runtime bundle`
- 自动化层：`TaskExecution`

其中：

- `RuntimeSession` 是买家真正消费的主对象
- `TaskExecution` 是 `RuntimeSession` 中的一次运行记录

## 4. `Docker Swarm` 语义下如何理解

`Docker Swarm` 底层更偏：

- `service` 表达期望状态
- `task` 是 service 的实际运行实例

所以平台不应该把买家直接暴露给原生 Swarm 术语，而应做一层业务封装：

- `RuntimeSession`
  - 对买家来说是一台可进入 shell 的“云主机会话”
  - 对平台内部来说是一套 `runtime bundle`
- `TaskExecution`
  - 是在当前 `RuntimeSession` 内触发的一次命令执行或项目运行

因此，基础设施承载关系应固定为：

- `RuntimeSession`
  - `runtime service`
  - `gateway service`
  - `session network`
  - `buyer wireguard lease`

而不是让买家直接理解：

- Swarm node
- Swarm task
- seller 实际网络拓扑

## 5. 期待的买家完整链路

下面这条链路是后续实现时必须对齐的完整流程。

### 5.1 平台前端交易链路

1. 买家在平台前端登录
2. 买家浏览 `Offer`
3. 买家创建 `Order`
4. 买家激活订单
5. backend 生成与买家账号绑定的 `AccessGrant`
6. backend 返回：
   - `grant_id`
   - `grant_code`
   - `expires_at`
   - 订单与会话规格摘要

此阶段必须明确：

- `POST /orders/{id}/activate` 只签发 grant
- 不直接创建基础设施会话
- 不直接创建 WireGuard peer
- 不直接给买家返回 seller target

### 5.2 buyer client 会话建立链路

1. 买家启动本地 `Buyer_Client`
2. 买家可以通过两种方式拿到 grant：
   - 登录同账号后拉取 active grants
   - 手工粘贴 `grant_code`
3. buyer client 本地生成 WireGuard keypair
4. buyer client 调用 grant 兑换/创建 session 接口，提交：
   - `grant_id` 或 `grant_code`
   - 本地生成的 `wireguard_public_key`
5. backend 创建 `RuntimeSession`
6. backend 调用 adapter 创建 `runtime bundle`
7. adapter 创建：
   - `runtime service`
   - `gateway service`
   - `session network`
   - buyer `wireguard peer`
8. backend 返回 `RuntimeSession bootstrap`
9. buyer client 写本地 WireGuard 配置并拉起 tunnel
10. buyer client 通过 WireGuard 内的 shell URL 打开远端 shell

此阶段必须明确：

- `AccessGrant` 是准入对象
- `RuntimeSession` 是实际使用对象
- `RuntimeSession bootstrap` 必须包含 shell/workspace/task 接口元数据

### 5.3 会话内项目运行链路

1. 买家在 buyer client 里选择本地项目目录
2. buyer client 使用 runtime 的 workspace 接口上传并解压项目
3. `CodeX MCP` 读取当前会话状态与项目目录
4. `CodeX MCP` 帮用户：
   - 识别项目类型
   - 推荐模板镜像
   - 推荐启动命令
   - 触发任务执行
5. runtime 生成 `TaskExecution`
6. buyer client 读取：
   - task 状态
   - task 日志
   - task 产物
7. 买家可以继续留在当前 shell 中复查、再次执行、下载产物

此阶段必须明确：

- `TaskExecution` 是会话内子能力
- 一次会话里允许多次任务执行
- 任务完成后默认不立即销毁 session

### 5.4 会话关闭与回收链路

1. 买家主动关闭 session，或租期到期
2. backend 将 `RuntimeSession` 标记为回收中
3. backend 调用 adapter 删除 `runtime bundle`
4. adapter 删除：
   - runtime service
   - gateway service
   - session network
   - buyer wireguard peer
5. buyer client 关闭本地 tunnel
6. backend 更新订单、grant、session 终态

## 6. 四个核心对象的关系

后续实现必须固定这 4 个核心对象的分层关系。

### 6.1 `Order`

- 交易对象
- 表达买家买了哪种会话规格、多长租期
- 不直接等于基础设施资源

### 6.2 `AccessGrant`

- 会话准入对象
- 由订单激活后签发
- 绑定 buyer 账号
- 支持手工复制 `grant_code`
- 用于 buyer client 创建或恢复 `RuntimeSession`

### 6.3 `RuntimeSession`

- 买家真正消费的云主机会话
- 对应一套实际的 runtime bundle
- 是 shell、workspace、task 的统一宿主

### 6.4 `TaskExecution`

- 会话内一次运行记录
- 不替代 `RuntimeSession`
- 记录命令、状态、日志摘要、产物索引

## 7. 各模块功能和边界

## 7.1 平台前端

### 负责

- 登录 / 注册
- 浏览 `Offer`
- 下单
- 激活订单
- 展示 grant / session / task 状态
- 引导用户打开本地 buyer client

### 不负责

- 进入正式 shell
- 上传工作区
- 执行命令
- 直接建立 WireGuard

### 结论

平台前端继续保留“云主机路线”，但它是交易与状态面，不是正式数据面入口。

## 7.2 Buyer Client

### 负责

- 本地窗口会话
- 本地状态文件
- 本地 Codex 会话
- MCP 工具面
- 本地 WireGuard keypair 生成与隧道拉起
- 打开远端 shell
- 工作区上传与同步
- 任务触发
- 日志 / 产物拉取

### 不负责

- 直接执行 Docker / Swarm / 服务端 WireGuard 命令
- 直接操作订单数据库
- 绕过 backend 直接改基础设施业务状态

### 结论

buyer client 是正式消费入口，不是“附属工具”。

## 7.3 CodeX / Buyer MCP

### 负责

- 基于当前 `RuntimeSession` 做受控操作
- 自动化用户的一键体验

### 只允许

- 拉取 active grants
- 导入 `grant_code`
- 创建 / 刷新 session
- 拉起 / 关闭 WireGuard
- 打开 shell
- 上传工作区
- 提交任务
- 读取日志
- 下载产物

### 不允许

- 任意本地 shell
- 任意远端命令入口
- 绕过 backend 直接创建基础设施资源

### 结论

CodeX 是 buyer client 的自动化层，不是额外的第二套后门控制面。

## 7.4 Platform Backend

### 负责

- 用户
- 订单
- grant
- runtime session
- task 读模型
- 过期与回收编排
- adapter / wireguard 控制面调用

### 不负责

- 日志和产物大流量代理
- 直接执行 Docker/WireGuard 命令

### 结论

backend 是业务真相面与控制编排面，不是数据平面代理。

## 7.5 Docker Swarm Adapter

### 负责

- 真实创建 / 检查 / 删除 runtime bundle
- 返回 bundle connect metadata
- 驱动 WireGuard peer

### 不负责

- 订单状态
- grant 生命周期
- buyer 账号归属
- session 业务真相

### 结论

adapter 继续只做基础设施控制，不升级成交易系统。

## 7.6 WireGuard

### 负责

- buyer peer apply/remove/inspect
- 返回 lease metadata

### 不负责

- 业务租期判断
- buyer 账号校验
- grant 状态判断

### 结论

WireGuard 只做网络租约事实，不做业务规则。

## 7.7 Managed Runtime / Shell Agent

### 负责

- shell
- workspace
- task
- logs
- artifacts

### 不负责

- 订单
- grant
- session 业务真相

### 结论

runtime 是会话的数据平面，不是交易控制面。

## 8. 明确“套卖家大框架”的复用方案

买家端应整体复用卖家端的大框架，只替换业务语义、MCP 能力和后端接口。

## 8.1 直接复用的层

- 本地 FastAPI 壳
- `state.py` 的 session 文件、heartbeat、job manager 模式
- `codex_session.py` 的会话级 Codex 配置与 MCP 注册方式
- `mcp_http.py` / `mcp_server.py` 的受控工具面形式
- 静态页面骨架
- 本地 API 编排方式

## 8.2 需要替换的层

- `backend.py`
  - 从 seller onboarding API 改成 buyer trade / grant / runtime session API
- `assistant_runtime.py`
  - 从“帮我接入卖家节点”改成“帮我进入会话、上传项目、执行任务”
- `mcp_server.py`
  - 从 join / verify / onboarding 工具改成 grant / wireguard / workspace / task 工具
- `state.py`
  - 从 `onboarding_session` 改成 `current_order`、`current_grant`、`runtime_session`、`task_execution_history`
- `local_system.py`
  - 从 seller 环境修复脚本改成 buyer WireGuard / workspace / session health

## 8.3 不再复用的 seller 专属概念

- onboarding probes
- join-complete
- correction lane
- manager task verification

## 8.4 buyer 端复用卖家框架的原则

不是“照抄 seller 逻辑”，而是：

- 复用 seller 的应用骨架
- 替换 seller 的业务契约
- 保留 buyer 的独立 MCP 能力面和状态模型

## 9. Buyer Client 后续需要增加什么

## 9.1 本地 API 分组

后续 buyer client 本地 API 应按下面几组整理：

- `auth`
- `catalog`
- `orders`
- `grants`
- `runtime-sessions`
- `wireguard`
- `workspace`
- `tasks`
- `assistant`

## 9.2 MCP 工具

后续 buyer MCP 应至少提供：

- `list_active_grants`
- `import_grant_code`
- `create_runtime_session`
- `refresh_runtime_session`
- `wireguard_up`
- `wireguard_down`
- `open_shell`
- `sync_workspace`
- `submit_task_execution`
- `tail_task_logs`
- `list_artifacts`
- `download_artifact`
- `stop_runtime_session`

## 9.3 本地状态对象

后续 buyer client 至少需要维护：

- `current_order`
- `current_grant`
- `runtime_session`
- `wireguard_state`
- `workspace_selection`
- `task_execution_history`

## 10. Backend 后续需要增加什么

## 10.1 保留现有对象

- `Offer`
- `Order`
- `AccessGrant`

## 10.2 新增对象

- `RuntimeSession`
- `RuntimeSessionEvent`
- `TaskExecution`
- `WireGuardLease` 读模型

## 10.3 新接口方向

后续 backend 需要增加或改造这些方向：

- `POST /orders/{id}/activate`
  - 只签发 grant，不直接创建 session
- `GET /me/access-grants/active`
- `POST /access-grants/redeem`
  - 入参必须支持 `wireguard_public_key`
- `POST /access-grants/redeem-by-code`
  - 支持手工导入 `grant_code`
- `GET /runtime-sessions/{id}`
- `POST /runtime-sessions/{id}/heartbeat`
- `POST /runtime-sessions/{id}/stop`
- `POST /runtime-sessions/{id}/close`
- `GET /runtime-sessions/{id}/task-executions`
- `GET /runtime-sessions/{id}/task-executions/{task_id}`

## 10.4 状态机

### `Order`

- `order_created`
- `grant_issued`
- `session_active`
- `completed`
- `expired`

### `AccessGrant`

- `issued`
- `redeemed`
- `exhausted`
- `expired`
- `revoked`

### `RuntimeSession`

- `created`
- `allocating`
- `ready`
- `active`
- `reclaiming`
- `closed`
- `expired`
- `failed`

### `TaskExecution`

- `queued`
- `running`
- `succeeded`
- `failed`
- `cancelled`
- `timeout`

## 10.5 grant-first 原则

后续 backend 设计必须固定这条原则：

- `activate order = issue grant`
- `redeem grant + public key = create runtime session`

而不是：

- `activate order = 直接创建基础设施 session`

## 11. Docker Swarm Adapter 后续需要增加什么

## 11.1 继续保留的主线

继续以：

- `runtime-session-bundles/create`
- `runtime-session-bundles/inspect`
- `runtime-session-bundles/remove`

作为会话承载主线。

## 11.2 `connect_metadata` 必须补齐

后续必须补齐以下字段：

- `wireguard_shell_embed_url`
- `workspace_upload_url`
- `workspace_extract_url`
- `workspace_status_url`
- `task_submit_url`
- `task_status_base_url`
- `task_logs_base_url`
- `artifact_base_url`
- `runtime_contract_version`

## 11.3 inspect 能力必须升级

`inspect_runtime_bundle` 后续不能只看 service 是否 running，还要能表达：

- shell readiness
- workspace readiness
- task API readiness
- 当前 session 对外 bootstrap 是否完整

## 11.4 建议增加 WireGuard peer inspect 只读接口

后续建议 adapter 增加只读接口，用于：

- 按 `runtime_session_id + lease_type` 查询当前 peer
- 给 backend 做 session 恢复与对账

## 11.5 `runtime-images/validate` 要升级

后续必须把当前 runtime contract 升级为 buyer runtime contract v2，并在 validate 中校验：

- shell
- workspace
- task
- logs
- artifacts

## 12. WireGuard 后续需要增加什么

## 12.1 保留

- `apply`
- `remove`
- `get peer`

## 12.2 新增

- `inspect`
  - 按 `runtime_session_id + lease_type` 查 peer

## 12.3 边界保持不变

- 业务租期不写进 WireGuard
- buyer client 必须自己生成本地 keypair
- backend 负责判断能不能兑换会话

## 13. Managed Runtime / Shell Agent 后续需要增加什么

## 13.1 保留现有能力

- shell
- workspace upload
- workspace extract
- workspace status

## 13.2 新增任务数据平面

后续 runtime contract 必须新增：

- `POST /api/tasks`
- `GET /api/tasks/{id}`
- `GET /api/tasks/{id}/logs`
- `GET /api/tasks/{id}/artifacts`
- `POST /api/tasks/{id}/cancel`

## 13.3 必须明确定义

后续实现前必须把这些定清楚：

- 任务日志目录
- 产物目录
- 返回 JSON 结构
- 任务取消语义
- 产物保留策略

## 14. 实现顺序与每步成功标准

下面这组顺序是后续施工的正式推荐顺序。

## Step 1. 重写买家文档为正式规格

### 要做什么

- 把当前买家讨论稿改成“云主机会话架构设计说明”
- 锁定主语义、完整链路、模块边界、复用策略、分步实施顺序

### 成功标准

- 文档主语义改成“云主机会话为主”
- 明确保留 shell 路线
- 明确前端与 buyer client 分工
- 明确订单、grant、runtime session、task execution 的分层关系

## Step 2. 定义 Buyer Client 复用 Seller 框架的映射

### 要做什么

- 用 seller 现有骨架作为 buyer 的迁移模板
- 明确哪些层复用、哪些层替换、哪些概念删除

### 成功标准

- 实现者可以直接照 seller 目录迁移 buyer 目录
- 不需要再自己决定 buyer 应该怎么拆层

## Step 3. 定义 Backend 的双层模型

### 要做什么

- 保留 order / grant
- 新增 runtime session / task execution
- 把激活和兑换拆成两个动作

### 成功标准

- 文档明确 `activate order = issue grant`
- 文档明确 `redeem grant + public key = create runtime session`
- 文档明确 session、grant、task 三者关系

## Step 4. 定义 Adapter 与 WireGuard 的会话承载职责

### 要做什么

- 明确 adapter 只做 bundle 与 connect metadata
- 明确 WireGuard 只做 peer 租约

### 成功标准

- 文档明确 adapter 不碰订单和账号状态
- 文档明确 `runtime bundle` 与 `wireguard lease` 的输出字段
- 文档明确 WireGuard 需要补 inspect，不扩业务判断

## Step 5. 定义 Managed Runtime 契约

### 要做什么

- 把 shell-agent 升级为 buyer runtime contract v2
- 把 task/log/artifact 接口纳入正式契约

### 成功标准

- 文档明确 shell、workspace、task、logs、artifacts 的正式接口面
- 文档明确数据平面由 buyer client 直连 runtime
- 文档明确 backend 只保留 task 读模型摘要

## Step 6. 明确后续正式施工顺序

### 要做什么

把后续施工顺序固定为：

1. 文档定稿
2. Buyer Client 框架平移
3. Backend grant-first 改造
4. RuntimeSession 层落库
5. AdapterClient 接 bundle / wireguard
6. Adapter/runtime contract 升级
7. Buyer client WireGuard + shell
8. Workspace + TaskExecution
9. 回收和过期

### 成功标准

- 每一步都有目标
- 每一步都有验收标准
- 后续工程实现不会出现“先写哪层还没想好”的情况

## 15. 本文档的验收清单

这份文档定稿后，必须满足下面这些要求：

- 另一个工程师不看聊天记录，也能知道买家完整链路是什么
- 能直接回答：buyer client、backend、adapter、wireguard 分别要加什么
- 能直接回答：为什么还能保留云主机 / shell 路线
- 能直接回答：如何复用 Seller_Client 大框架
- 能直接回答：为什么正式连接路径是 WireGuard 优先、本地 client 唯一 shell 入口
- 能直接回答：以后应该先改哪里、后改哪里、每步怎么判断成功

## 16. 本轮默认假设

本轮后续讨论默认采用：

- 文档是单篇中文总设计文档
- 不拆成多篇
- 本轮只写文档，不改 buyer client / backend / adapter / wireguard 代码
- 前端继续保留“云主机路线”
- shell 正式入口不放平台前端，只放本地 buyer client
- `grant_code` 手工复制导入和“同账号在 buyer client 拉取 grant”两种路径都正式支持

## 17. 本轮结论

后续真正要实现的不是：

- “买家直接租到一台卖家机器”

而是：

- “买家通过平台订单拿到会话准入凭证，在本地 buyer client 中建立一个由 runtime bundle 承载的云主机会话，并在这个会话里进入 shell、上传项目、执行任务、查看日志和下载产物”

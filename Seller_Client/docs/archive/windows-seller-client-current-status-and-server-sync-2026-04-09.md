# Windows 卖家本地客户端当前状态、服务器同步与下一步目标

更新时间：`2026-04-09`

## 1. 当前客户端状态

当前 `seller_client` 已经从 Phase 2B 的脚本堆叠，收束成一个可重复运行的 Windows 卖家本地客户端主线：

- 正式 Windows 入口只有两个：
  - `bootstrap/windows/install_and_check_seller_client.ps1`
  - `bootstrap/windows/start_seller_client.ps1`
- 应用主线固定在 `seller_client_app/`
  - 本地 Web 壳：FastAPI + `static/`
  - 本地受控 workflow：环境检查、WG/overlay 检查、标准 join workflow、诊断导出
  - 原生 Codex stdio MCP：已按全局 `~/.codex/config.toml` 的 stdio block 接通
  - MCP 工具面：已能读 session、拉 join material、跑 guided join assessment、清理 join 状态

当前网页端工作区固定为：

- `环境`
- `网络 / WireGuard`
- `Docker / Swarm`
- `接入会话`
- `AI 助手`

## 2. 已验证通过的能力

### 2.1 本地 Web / MCP / 工作流

当前已经真实验证通过：

- 本地 Web 壳可打开、创建 window session、登录/注册卖家、创建 onboarding session
- Web 自然语言入口可调用受控 seller workflow
- 原生 `Codex CLI -> stdio MCP` 在这台 Windows 机器上已真实连通
- `run_guided_join_assessment` 已可由原生 Codex 调用并返回结构化结果
- `clear_join_state` 已做成正式能力，并能从 MCP 与本地 API 调用

### 2.2 当前真实验收 session

当前主要使用并反复验证的 session 是：

- `join_session_10b76165424965b5`

在这条 session 上，已经稳定复现到：

- 本地 Docker Swarm 视角：
  - `LocalNodeState = active`
  - `NodeAddr = 10.66.66.10`
- guided join assessment 视角：
  - `local_join.ok = true`
  - `join_idempotent_reason = already_joined_and_active_with_expected_advertise_addr`
- backend 视角：
  - `effective_target_addr = 10.66.66.10`
  - `effective_target_source = backend_correction`
  - `truth_authority = backend_correction`
- manager raw truth 视角：
  - `manager_acceptance.status = claim_failed`
  - `observed_manager_node_addr = 202.113.184.2`
- minimum TCP validation 视角：
  - 对 `10.66.66.10:8080` 探测失败
  - `reachable = false`

结论很明确：

- 本地 join 已经成立
- backend correction 已经成立
- 但 manager raw truth 还没有收敛到 WireGuard IP
- 所以当前还不能把这条路径判定成“Swarm 层真正完成”

## 3. 新增的关键能力

本轮新增并稳定下来的能力有：

### 3.1 `clear_join_state`

已经补成正式能力：

- Windows 侧受控脚本：`bootstrap/windows/clear_windows_join_state.ps1`
- 本地系统层：`seller_client_app/local_system.py`
- 本地 API：`POST /local-api/runtime/clear-join-state`
- MCP：`clear_join_state`
- Web 按钮：`清理本地 join 状态`

该能力当前支持：

- 检查本地 Docker 是否处于 swarm
- 如果已 join，则执行受控 `docker swarm leave --force`
- 清掉本地 runtime evidence / last assistant run
- 可选刷新或关闭 backend onboarding session
- 可选在清理后立刻重跑一次环境检查

### 3.2 guided join assessment 收束

`run_guided_join_assessment` 现在已经收束为一条高层工具：

- 刷新 backend session
- 读取 join material
- 运行本地环境检查
- 执行标准 join workflow
- 汇总：
  - 本地环境健康
  - join material
  - 本地 join 结果
  - manager raw truth
  - backend authoritative target
  - minimum TCP validation

同时，这条路径已经做了超时收束：

- 不再重复跑第二遍 overlay script
- 标准 join workflow 默认缩短 probe profile

这样原生 Codex 的单次 MCP 调用已经能在当前机器上稳定跑完。

## 4. 当前还没过线的点

当前真正没有解决的主问题不是：

- Web 壳打不开
- Codex 连不上 MCP
- 本地 join 不成立
- backend correction 不成立

当前真正没过线的是：

- Docker Swarm manager 对 Windows worker 的 raw truth 仍稳定指向公网 `202.113.184.2`
- 而不是我们期望的 `10.66.66.10`

这意味着：

- backend 可以“知道应该用 `10.66.66.10`”
- 但 Swarm 自己还没有“按 `10.66.66.10` 识别这个 worker”

## 5. 下一步工作目标

下一步的核心目标已经明确收敛为：

### 5.1 主目标

让 Docker Swarm 的 raw manager truth 收敛到 WireGuard IP。

也就是最终至少要满足：

- manager 看到该 worker 的地址不再是 `202.113.184.2`
- 而是 `10.66.66.10`

### 5.2 工作方向

当前建议继续沿这条方向推进：

1. 保持 Win 客户端现在这套 Web + MCP + controlled workflow 主线不再大改
2. 继续从真实 session 上跑 guided join assessment / clear / retry
3. 集中分析并收敛：
   - Docker Desktop / Swarm 对 worker 地址的稳定判定
   - 是否存在 join 后 manager 侧 claim / identity 复用问题
   - 是否存在可控的 worker 侧地址收敛手段
4. 如果少量后端覆写能形成稳定工作流，可以保留
5. 但不要再大规模改服务层语义

## 6. 如果不覆写 Swarm 里的 WireGuard IP，仅靠后端记录，买家能不能用卖家算力？

当前结论是：

- `有局部希望`
- `但还不能把它当成稳态方案`
- `尤其不能把它当成“Swarm 层已经解决”`

### 6.1 为什么说“有局部希望”

因为 backend 现在已经能记录并输出：

- `effective_target_addr = 10.66.66.10`
- `truth_authority = backend_correction`

这意味着，如果买家客户端后续不是严格依赖 Swarm manager 的 raw node address，而是依赖 backend 返回的 authoritative target，理论上存在一种“平台自定义连接层”：

- backend 告诉买家：去连 `10.66.66.10`
- 买家直接走平台自己的连接策略去访问卖家暴露的能力

这种思路并不要求 manager raw truth 先变成 WireGuard IP 才能“知道目标地址”。

### 6.2 为什么说“还不能当成稳态方案”

因为到目前为止，真实验证结果仍然是：

- backend correction 虽然已建立
- 但对 `10.66.66.10:8080` 的 minimum TCP validation 仍然失败

也就是说，平台“知道应该连哪里”，并不等于“买家现在已经真的连得通”。

另外还要区分两件事：

- `backend 知道卖家有效目标地址`
- `Docker Swarm 自己已经把这个卖家节点当成 WireGuard 节点稳定纳入调度和网络视图`

这两件事不是同一层。

### 6.3 当前更稳妥的判断

当前更稳妥的判断应当是：

- 如果未来买家侧走的是平台自定义直连路径，并且后续 TCP 可达性能打通，那么“即使 raw manager truth 不是 WG IP”也可能形成一条可工作的替代链路
- 但如果目标是“在 Docker Swarm 自己的节点身份与网络真相层面完全成立”，那就不能只靠 backend correction，仍然需要 raw manager truth 收敛

所以，这条问题可以拆成两条路线：

1. `平台可用性路线`
   - backend authoritative target 是否足够让买家连上卖家并消费能力
2. `Swarm 真相路线`
   - manager raw truth 是否最终变成 `10.66.66.10`

当前第一条路线也还没有最终打通，因为最小 TCP 验证仍失败；第二条路线则仍然明确未解决。

## 7. 服务器同步目标

为让服务器侧与本地开发进度保持一致，本次应同步的目标目录是：

- 本地：`D:\AI\Pivot_Client\seller_client`
- 服务器：`/root/Pivot_network/Seller_Client`

同步原则：

- 先备份服务器侧旧目录
- 再覆盖为当前本地客户端目录
- 不同步本地运行时垃圾与机器私有状态，例如：
  - `.venv/`
  - `sessions/`
  - `health/`
  - `exports/`
  - `.pytest_cache/`
  - `__pycache__/`

## 8. 一句话结论

当前 Win 卖家客户端已经具备：

- 可打开的本地 Web 壳
- 可复用的受控 workflow
- 可连通的原生 Codex stdio MCP
- 可运行的 guided join assessment
- 可执行的 clear_join_state

但它还没有让 Docker Swarm manager 的 raw truth 收敛到 WireGuard IP。下一步应继续围绕这个点推进，同时并行验证：如果只依赖 backend authoritative target，买家侧是否有可能绕开 raw manager truth，先把“可用性链路”打通。

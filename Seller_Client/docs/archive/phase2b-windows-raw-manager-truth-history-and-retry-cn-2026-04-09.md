# Phase 2B Windows 路径：raw manager truth 历史、误判来源与 2026-04-09 重试说明

更新时间：`2026-04-09`

## 1. 先给结论

### 1.1 这件事不是“完全修好过又坏了”

截至 `2026-04-09`，本地 repo 留下来的 seller onboarding session 里，没有任何一轮证据表明：

- `manager_acceptance.status = matched`
- 且 `observed_manager_node_addr = 10.66.66.10`

也就是说，**`raw manager truth = 10.66.66.10` 这条最终成功标准，在现有留档里从未真正闭环过。**

所以更准确的说法不是“之前修好了，现在复发”，而是：

1. 曾经修通过的是 `WireGuard reachability`、`本地 NodeAddr = 10.66.66.10`、以及一次真实的官方 WG-target rejoin。
2. 但 manager 最终按 `10.66.66.10` 识别 worker 这件事，并没有在已留档的 session 里真正达标。

### 1.2 真正“曾经解决过”的部分

之前确实解决过三段很关键的链路：

1. `docker-desktop -> 10.66.66.1:2377/7946` 的 WG control-plane TCP 可以恢复稳定。
2. Windows 本地 / Docker Desktop 视角下，`docker info .Swarm.NodeAddr` 可以回到 `10.66.66.10`。
3. 在 `docker swarm leave --force` 卡住时，通过重启 Docker Desktop 用户态进程，可以恢复一次成功的 `leave -> official WG-target join`。

但是这三段都不等于：

- `manager side raw truth = 10.66.66.10`

## 2. 为什么会被误判成“之前已经修好了”

### 2.1 历史上混在一起的三个“成功表象”

过去容易把下面三件事混成一件事：

1. `WireGuard connectivity`
   - server / buyer / seller 能通过 `10.66.66.10` 到达 Windows

2. `local swarm identity`
   - Windows 本机 `docker info .Swarm.NodeAddr = 10.66.66.10`

3. `manager-accepted node identity`
   - manager `docker node inspect` 最终看到的 `Status.Addr`

前两件事以前都真实发生过，但第三件事在留档 session 里没有真正完成。

### 2.2 现有 session 留下来的事实

现有 session 摘要如下：

- [join_session_0421b90ccabe39e2/session.json](d:\AI\Pivot_Client\seller_client\sessions\join_session_0421b90ccabe39e2\session.json)
  - 本地 `NodeAddr = 10.66.66.10`
  - manager `observed_manager_node_addr = 202.113.184.2`
  - `status = mismatch`
- [join_session_dd8e0254f173041a/session.json](d:\AI\Pivot_Client\seller_client\sessions\join_session_dd8e0254f173041a\session.json)
  - 本地 `observed_wireguard_ip / advertise / data-path = 10.66.66.10`
  - manager `observed_manager_node_addr = 202.113.184.2`
  - `status = mismatch`
- [join_session_55a61409c8cf74a1/session.json](d:\AI\Pivot_Client\seller_client\sessions\join_session_55a61409c8cf74a1\session.json)
  - 官方 WG-target rejoin 成功
  - 新 node ref = `bhfprq8z3qf0bq0bk8nv1y115`
  - 本地 `NodeAddr = 10.66.66.10`
  - manager `observed_manager_node_addr = 10.66.66.2`
  - `status = mismatch`

换句话说，历史上最接近成功的一轮，也只是把 manager 看到的地址从公网 `202.113.184.2` 推进到了 `10.66.66.2`，还不是目标 `10.66.66.10`。

## 3. 上次真正有效的恢复动作是什么

### 3.1 不是改 manager listen scope

上次有效推进并不是：

- 改 manager 监听范围
- 改 fake override
- 把 backend effective target 当作 runtime 现场成功

真正有效的是 Windows worker 侧这条恢复链：

1. 先确认 `docker-desktop` 内到 `10.66.66.1:2377/7946` 的 WG control-plane soak 稳定。
2. 如果 `docker swarm leave --force` 卡在 `context deadline exceeded`，不要直接判定 WG 又坏了。
3. 先恢复 Docker Desktop 用户态进程，再等 engine pipe 和 `docker info` 回来。
4. 然后立刻做一次显式 WG 参数的官方 rejoin。
5. 再去看 manager 最终把新 node 记成什么地址。

### 3.2 对应的现成脚本

这条恢复链已经在 repo 里有脚本化入口：

- soak / 运行面检查：
  - [check_windows_overlay_runtime.ps1](d:\AI\Pivot_Client\seller_client\bootstrap\windows\check_windows_overlay_runtime.ps1)
- Docker Desktop 引擎恢复：
  - [recover_docker_desktop_engine.ps1](d:\AI\Pivot_Client\seller_client\bootstrap\windows\recover_docker_desktop_engine.ps1)
- 官方 WG-target rejoin：
  - [rejoin_windows_swarm_worker.ps1](d:\AI\Pivot_Client\seller_client\bootstrap\windows\rejoin_windows_swarm_worker.ps1)
- manager 复核 / stale node 清理：
  - [monitor_swarm_manager_truth.ps1](d:\AI\Pivot_Client\seller_client\bootstrap\windows\monitor_swarm_manager_truth.ps1)
- 恢复 + leave + correction cycle 封装：
  - [recover_and_rejoin_windows_swarm.ps1](d:\AI\Pivot_Client\seller_client\bootstrap\windows\recover_and_rejoin_windows_swarm.ps1)

### 3.3 上次真实成功过的一段现场

`2026-04-08` 的有效推进点是：

1. `docker-desktop` 内 30 秒 soak 全绿。
2. Docker Desktop 用户态进程重启后，`docker swarm leave --force` 成功一次，返回 `Node left the swarm.`。
3. 随后官方 join 成功，返回 `This node joined a swarm as a worker.`。
4. 本地新 node ref 变成 `bhfprq8z3qf0bq0bk8nv1y115`，且本地 `NodeAddr = 10.66.66.10`。
5. manager 当时不再是公网地址，而是看成了 `10.66.66.2`。

这说明：

- 上次真正恢复的是“控制面 + engine + 一次成功 rejoin”
- 没有恢复的是“manager raw truth 最终等于 10.66.66.10”

## 4. 为什么现在看起来像“又复发了”

### 4.1 复发的不是同一个层面

当前看到的“又变回公网地址”更像是两层问题叠加：

1. Docker Desktop engine / swarm identity 仍然不稳定
   - `leave --force` 会间歇性卡成 `context deadline exceeded`
   - 这会导致 node identity / rejoin 节奏重新漂移

2. manager 最终采用的 `Status.Addr` 不是单靠本地 `NodeAddr` 就能锁死
   - 本地 `advertise/data-path/listen` 显式带了 `10.66.66.10`
   - manager 仍可能把 worker 记录成别的地址

因此现在的“复发”不是简单等于：

- `WireGuard 配置脏了`

更准确的描述是：

- `WG control-plane` 目前可以稳定通
- 但 Docker Desktop 的 leave/rejoin 身份闭环仍不稳
- manager 的 raw truth 仍会按它自己看到的控制面地址落点，而不是按本地自报值自动继承

### 4.2 2026-04-09 当前现场

`2026-04-09 01:57 CST` 的当前现场是：

- 本机 `docker info`：
  - `NodeID = 9upsv4qd63ayhlzrlbqyos34k`
  - `NodeAddr = 10.66.66.10`
  - `LocalNodeState = active`
- `docker-desktop -> 10.66.66.1:2377/7946`：
  - 15 次 soak 全部 `open`
- manager 侧通过 [monitor_swarm_manager_truth.ps1](d:\AI\Pivot_Client\seller_client\bootstrap\windows\monitor_swarm_manager_truth.ps1) 看到：
  - node ref = `9upsv4qd63ayhlzrlbqyos34k`
  - hostname = `docker-desktop`
  - `Status.Addr = 202.113.184.2`
  - `Status = Ready`

这再次证明：

- 本地 `NodeAddr = 10.66.66.10`
- 但 manager raw truth 仍可回退到公网 `202.113.184.2`

## 5. 本轮重试应该怎么做

### 5.1 正确目标

本轮唯一合格目标仍然是：

- manager `docker node inspect` 看到的 worker `Status.Addr = 10.66.66.10`

下面这些都只能算中间态，不算最终成功：

- 本地 `docker info` 显示 `NodeAddr = 10.66.66.10`
- `10.66.66.1:2377/7946` soak 全绿
- backend 只写出 `effective_target_addr`

### 5.2 重试顺序

1. 跑 `docker-desktop` soak，确认 `2377/7946` 稳定。
2. 检查当前 manager raw truth，记录当前 node id 和 `Status.Addr`。
3. 尝试 `leave -> official WG-target join`。
4. 如果 `leave --force` 卡住：
   - 用 [recover_docker_desktop_engine.ps1](d:\AI\Pivot_Client\seller_client\bootstrap\windows\recover_docker_desktop_engine.ps1)
   - 重点使用 `-RestartDockerDesktopProcesses`
   - 等 pipe 和 `docker info` 恢复后再重试
5. rejoin 成功后马上看 manager：
   - 如果是 `10.66.66.10`，这轮才算 raw success
   - 如果还是 `10.66.66.2` 或 `202.113.184.2`，说明本轮仍未达到最终标准

### 5.3 这份文档的使用口径

后续讨论时，请固定区分三层：

1. `WG reachable`
2. `local NodeAddr = 10.66.66.10`
3. `manager raw truth = 10.66.66.10`

只有第 3 条成立，才算 Phase 2B 在 Windows Docker worker 路线上真正过线。

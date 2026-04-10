# Phase 2B Windows 卖家接入：当前状态与后续开工说明

更新时间：`2026-04-09 02:56 CST`

## 1. 任务背景

当前做的是 `Phase 2B`，目标不是把文档补齐，也不是只让 backend 看起来可用，而是把 **Windows 卖家沿官方 Docker worker 路线真实接入** 跑通。

这条链路的核心要求是：

1. Windows 卖家本机通过官方 `docker swarm join/rejoin` 加入远端 manager。
2. manager 侧最终把这个 worker 识别成 `WireGuard 地址`，不是公网地址。
3. backend 能读到 fresh join / correction / re-verify 证据。
4. 对最终 target 完成 minimum TCP validation。

当前不允许把 fake override 当作 Windows runtime 现场成功。

## 2. 成功标准

当前唯一硬成功标准仍然是：

- 远端 `docker swarm manager` 看到的这个 Windows worker 的 `Status.Addr = 10.66.66.10`

同时，完整闭环还需要：

- backend 读到 fresh join facts
- runtime / Docker_Swarm 完成 correction 并留证
- backend 再做 re-verify
- 对纠正后的 target 做 minimum TCP validation

下面这些都不算最终成功：

- 本地 `docker info .Swarm.NodeAddr = 10.66.66.10`
- `docker-desktop -> 10.66.66.1:2377/7946` 能通
- backend 只写出了 `effective_target_addr`
- buyer / workflow 能消费 override

## 3. SSH 连接服务器的方式

### 3.1 服务器信息

当前服务器入口是：

```sshconfig
Host TenCent
    HostName 81.70.52.75
    User root
    Port 22
    IdentityFile D:/AI/Pivot_backend_build_team/navi.pem
```

### 3.2 建议的实际连接方式

在这台 Windows 机器上，**不建议直接用原生 Windows `ssh -i D:/.../navi.pem`**，因为 OpenSSH 会经常报：

- `Permissions ... are too open`

当前更稳定的做法是：

1. 从 `WSL Ubuntu` 发起 SSH。
2. 先把 `D:/AI/Pivot_backend_build_team/navi.pem` 复制到 WSL 的 `/tmp/*.pem`。
3. 对临时 key 执行 `chmod 600`。
4. 再用这个临时 key 连 `root@81.70.52.75`。

这套逻辑已经封装在这些脚本里：

- [monitor_swarm_manager_truth.ps1](d:\AI\Pivot_Client\seller_client\bootstrap\windows\monitor_swarm_manager_truth.ps1)
- [swarm_runtime_common.ps1](d:\AI\Pivot_Client\seller_client\bootstrap\windows\swarm_runtime_common.ps1)

## 4. 服务器那边的状态

### 4.1 远端主机状态

`2026-04-09 02:56 CST` 实测：

- 远端 hostname：`VM-0-3-opencloudos`
- 真实后端工作区存在：`/root/Pivot_network/Plantform_Backend`

### 4.2 远端 backend 进程状态

当前线上提供 backend 的不是 compose 容器，而是服务器工作区里的直接 `uvicorn`：

- 进程：`./.venv/bin/python -m uvicorn backend_app.main:app --host 127.0.0.1 --port 8000`
- PID：`3245884`
- 监听：`127.0.0.1:8000`

这说明服务器上的真实后端工作区仍然是可用入口，不是本机那份 `Pivot_backend_build_team`。

## 5. 当前任务现状

### 5.1 本机 Windows / Docker Desktop 当前状态

`2026-04-09 02:56 CST` 实测：

- `docker version` 正常，server 已恢复
- `docker info .Swarm` 当前是：
  - `NodeID = ""`
  - `NodeAddr = ""`
  - `LocalNodeState = inactive`
- 这意味着当前本机 engine 健康，但 swarm 处于 `inactive`，适合下一轮 fresh join

### 5.2 WG control-plane 当前状态

最近一轮实测里，`docker-desktop` 内到 manager 的 WG control-plane 仍然稳定：

- `10.66.66.1:2377` 连续采样 `open`
- `10.66.66.1:7946` 连续采样 `open`
- `ip route get 10.66.66.1` 仍然走 `wg-seller src 10.66.66.10`

所以当前不是单纯的 WG 路由断了。

### 5.3 manager 当前状态

`2026-04-09 02:56 CST` 通过 [monitor_swarm_manager_truth.ps1](d:\AI\Pivot_Client\seller_client\bootstrap\windows\monitor_swarm_manager_truth.ps1) 实测：

- manager leader 节点：`t1p4v4byyo64dyefhd804wlzx`
- 当前唯一匹配到的 `docker-desktop` worker：
  - node id = `9upsv4qd63ayhlzrlbqyos34k`
  - `Status = Down`
  - `Status.Addr = 202.113.184.2`
  - `status_message = heartbeat failure`

所以当前 manager raw truth 仍然是：

- `202.113.184.2`

而不是：

- `10.66.66.10`

### 5.4 backend / session 当前状态

历史上最接近成功的一轮仍然是：

- [join_session_55a61409c8cf74a1](d:\AI\Pivot_Client\seller_client\sessions\join_session_55a61409c8cf74a1\session.json)
  - 官方 WG-target join 成功
  - manager 看到 `10.66.66.2`
  - 但不是 `10.66.66.10`
  - `minimum_tcp_validation.reachable = false`

当前最新 fresh session 是：

- [join_session_c9ec59b0eeef128a](d:\AI\Pivot_Client\seller_client\sessions\join_session_c9ec59b0eeef128a\session.json)
  - `status = probing`
  - `expected_wireguard_ip = 10.66.66.10`
  - `linux_substrate_probe` 已经补成功
  - 还没有完成 fresh join / manager re-verify

## 6. 已完成的工程化改动

本地 seller_client 已经补了几处关键容错：

- [rejoin_windows_swarm_worker.ps1](d:\AI\Pivot_Client\seller_client\bootstrap\windows\rejoin_windows_swarm_worker.ps1)
  - 现在不再把 stderr 直接当作 PowerShell 异常吞掉
  - 能显式留存 `leave/join` 的 stdout/stderr
  - 能识别 Docker 官方返回的 `join will continue in the background`
  - 会对 join 结果做 settle 轮询，而不是看到一次超时就立刻判死
- [recover_docker_desktop_engine.ps1](d:\AI\Pivot_Client\seller_client\bootstrap\windows\recover_docker_desktop_engine.ps1)
  - 现在只有在 engine 真正恢复时才返回成功
  - 不会再把 `API 500 + 空 swarm JSON` 误报成 recover 成功
- [runtime_real_2b.ps1](d:\AI\Pivot_Client\seller_client\runtime_real_2b.ps1)
  - 现在在 rejoin 异常时，可以按条件尝试一次 engine recover 后重试
  - join step 会把 recovery / retry 证据留下来

## 7. 当前阻塞点

当前 stop line 已经非常具体，不是文档问题，不是纯 backend 问题，也不是 manager listen scope 问题。

### 7.1 核心阻塞

核心阻塞仍然是：

- Windows worker 侧 Docker Desktop engine 在 `leave/rejoin` 附近不稳定
- manager raw truth 仍然不按 `10.66.66.10` 收敛，这可能是有多个wireguard 共存  或者本地wireguard 配置问题

### 7.2 已观察到的具体失败模式

已经明确出现过这些模式：

1. `docker swarm leave --force` 间歇性报：
   - `context deadline exceeded`
2. `docker swarm join` 可能报：
   - `Timeout was reached before node joined. The attempt to join the swarm will continue in the background.`
3. join/recover 后 Docker Desktop engine 可能掉进：
   - `request returned Internal Server Error ... dockerDesktopLinuxEngine`
4. manager 侧地址识别出现过三种落点：
   - `202.113.184.2`
   - `10.66.66.2`
   - 但还没有稳定出现 `10.66.66.10`

### 7.3 一个新增教训

当前还有一个很重要的操作性结论：

- 当本机 engine 已经健康且 `LocalNodeState = inactive` 时，不要先强制重启 Docker Desktop 用户态进程

因为最近一轮已经证明：

- 在 `inactive + healthy` 基线上先做 Desktop restart，会把 engine 打进持续的 API 500 恢复期

正确策略应该是：

- `engine healthy + swarm inactive`：直接 join
- `engine unhealthy` 或 `leave/rejoin` 明确卡死：再做 recover

## 8. 后续开工建议

### 8.1 第一优先级

下一轮开工建议从 [join_session_c9ec59b0eeef128a](d:\AI\Pivot_Client\seller_client\sessions\join_session_c9ec59b0eeef128a\session.json) 继续，而不是重新从零开很多新 session。

原因是这条 session 已经具备：

- fresh seller user / auth token
- fresh join material
- `expected_wireguard_ip = 10.66.66.10`
- substrate probe 已通过

下一步最适合直接做：

1. 确认本机 engine 健康，且 `docker info .Swarm.LocalNodeState = inactive`
2. 不先 recover
3. 直接跑官方 WG-target join / correction cycle
4. 再立刻用 manager monitor 复核 raw truth

### 8.2 推荐执行顺序

推荐按这个顺序继续：

1. 先跑一次 [check_windows_overlay_runtime.ps1](d:\AI\Pivot_Client\seller_client\bootstrap\windows\check_windows_overlay_runtime.ps1)
   - 只确认 `2377/7946` soak 稳定
2. 再确认本机：
   - `docker version` 正常
   - `docker info .Swarm.LocalNodeState = inactive`
3. 然后直接跑：
   - [attempt_manager_addr_correction_cycle.ps1](d:\AI\Pivot_Client\seller_client\bootstrap\windows\attempt_manager_addr_correction_cycle.ps1)
   - 使用 `join_session_c9ec59b0eeef128a`
   - `JoinMode = wireguard`
   - `AdvertiseAddress / DataPathAddress / ListenAddress = 10.66.66.10`
4. 如果 join 失败，再根据失败类型决定：
   - `leave/join` 卡死或 engine unhealthy：用 [recover_docker_desktop_engine.ps1](d:\AI\Pivot_Client\seller_client\bootstrap\windows\recover_docker_desktop_engine.ps1)
   - 但不要在 engine 已健康且 inactive 时主动 recover
5. join 后第一时间看 manager：
   - 是否出现新 node id
   - `Status.Addr` 是 `10.66.66.10`、`10.66.66.2` 还是公网

### 8.3 建议补的一处客户端改进

建议后续优先补一处 seller_client 细节：

- 在 onboarding start 时显式把 `expected_wireguard_ip = 10.66.66.10` 带给 backend

因为今天已经出现过：

- fresh session 刚创建时 `expected_wireguard_ip = null`
- 直到手动补了一次 substrate probe，backend 才把它 adopt 成 `10.66.66.10`

这不一定是最终根因，但会给 join 流程增加不必要的漂移。

## 9. 不建议再做的事

当前阶段不建议把精力放在这些方向：

- 再去改 manager listen scope
- 把 fake override 当作 runtime 成功
- 把本机 `NodeAddr = 10.66.66.10` 误判成 raw success
- 在 engine 已健康且 inactive 时先重启 Docker Desktop
- 再把本机那份 `Pivot_backend_build_team` 当作真实后端工作区

## 10. 一句话 handoff

当前真实状态是：

**Windows 本机 WG control-plane 仍然稳定，服务器上的真实 backend 也在线，但 manager raw truth 仍停在公网地址链路，且 Docker Desktop engine 在 leave/rejoin 周边仍不稳定。现在最合理的后续开工点，不是再改文档或 manager 配置，而是在 engine 健康且 swarm inactive 的基线上，从 `join_session_c9ec59b0eeef128a` 继续跑一次官方 WG-target join/correction cycle，并只按 manager `Status.Addr` 是否等于 `10.66.66.10` 来判定成功。**

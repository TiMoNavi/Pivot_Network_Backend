# Windows 历史路径下的 Docker Swarm / WireGuard IP 识别分析

更新时间：`2026-04-08`

## 1. 这份文档回答什么问题

这份文档只回答一个非常具体的问题：

- 在附近的 `Pivot_backend_build_team` 历史实现里，Windows 是怎么接入 `Docker Swarm` 的？
- 这条 Windows 路径能不能正常走到 `WireGuard IP`？
- 如果本地看起来已经是 `10.66.66.10`，为什么 manager 最终不一定按 `10.66.66.10` 识别这个 seller worker？

这不是当前 `WSL Ubuntu Compute` live blocker 的排障记录。

这份文档分析的是一条已经存在过的历史路径：

- `Windows + Docker Desktop`
- `Windows 本机 WireGuard`
- `seller 主机自己执行 docker swarm join`

## 2. 结论先说

### 2.1 这条 Windows 历史路径的接入方式

Windows 这条历史路径不是 adapter 远程 SSH 到 seller 去执行 `docker swarm join`。

正式思路是：

1. adapter / backend 下发 join material
2. seller 主机自己执行 `docker swarm join`
3. manager 再对新加入节点做 claim / label

### 2.2 这条路径的 WireGuard 并不是完全没通

从历史证据看，Windows 上的 `wg-seller` 曾经是打通的，而且不是只有本地自报成功：

- 服务器可以通过 `10.66.66.10:22` SSH 到 Windows
- buyer 历史会话里也把 seller/gateway 目标写成了 `10.66.66.10`

所以不能把这条路径简单总结成“Windows 根本到不了 WireGuard IP”。

### 2.3 真正的问题不在“能不能碰到 WG IP”，而在“manager 最终按什么地址认 worker”

历史 session 里，Windows 本地与 Docker Desktop 侧上报的是：

- `observed_wireguard_ip = 10.66.66.10`
- `observed_advertise_addr = 10.66.66.10`
- `docker info .Swarm.NodeAddr = 10.66.66.10`

但同一个 session 里，manager 验收看到的却是：

- `observed_manager_node_addr = 202.113.184.2`
- `detail = manager_node_addr_mismatch`

这说明：

**Windows 本地能用 WireGuard IP，不等于 manager 最终会按这个 WireGuard IP 识别 seller worker。**

### 2.4 这也是为什么后面会出现显式 `--advertise-addr`

历史材料里已经出现了一个补救脚本，明确把：

- `--advertise-addr 10.66.66.10`
- `--data-path-addr 10.66.66.10`

钉到 `docker swarm join` 上。

它反过来证明：团队已经意识到，单靠裸的 `docker swarm join --token ... 81.70.52.75:2377` 并不能保证 manager 侧最终按 `10.66.66.10` 认这个节点。

## 3. 证据链

### 3.1 Swarm join 是 seller 主机自己执行的

来源：`d:\AI\Pivot_backend_build_team\docs\adapter-codex-build-handoff-cn.md`

关键含义：

- adapter 不代替 seller 执行 join
- seller 主机自己跑 `docker swarm join`
- adapter 只负责下发 join material 和后续 claim

关键片段：

```text
SH -->|docker swarm join| SM
```

```bash
docker swarm join --token <token> <manager_addr>:2377
```

```text
- adapter 不直接把 seller 主机拉进集群
- adapter 只负责发加入材料和认领节点
- seller 主机自己执行 `docker swarm join`
```

### 3.2 历史 join material 本身是裸 join 命令

来源：`d:\AI\Pivot_Client\seller_client\sessions\join_session_0421b90ccabe39e2\session.json`

关键片段：

```json
"manager_addr": "81.70.52.75",
"manager_port": 2377,
"swarm_join_command": "docker swarm join --token SWMTKN-... 81.70.52.75:2377"
```

这说明当时平台下发给 seller 的 join 命令，本身并没有显式带：

- `--advertise-addr`
- `--data-path-addr`

### 3.3 Windows 本机 WireGuard 曾经是通的

来源：`d:\AI\Pivot_backend_build_team\docs\server-ssh-to-windows-via-wireguard-2026-04-05.md`

关键片段：

```ini
[Interface]
Address = 10.66.66.10/32

[Peer]
Endpoint = 81.70.52.75:45182
AllowedIPs = 10.66.66.1/32
PersistentKeepalive = 25
```

```sshconfig
Host win-local-via-wg
  HostName 10.66.66.10
  User 550w
  Port 22
```

```text
- 服务器 `wg0` 已看到 `10.66.66.10/32` 的最新握手
- 服务器到 `10.66.66.10:22` 已可达
- 服务器已可执行 `ssh win-local-via-wg`
```

这部分证据很关键。

它说明历史 Windows 路径下：

- manager/server 到 seller 的 WireGuard 内网地址是曾经打通过的
- 因此不能把后续问题简单归因为“Windows 根本没有 WG 连通性”

### 3.4 buyer 历史会话也确实在消费 seller 的 WireGuard 目标地址

来源：`d:\AI\Pivot_backend_build_team\.cache\buyer-web\codex_jobs\762350d2f1a24c7d990239b83b575bcb\stdout.log`

关键片段：

```json
"network_mode": "wireguard",
"seller_wireguard_target": "10.66.66.10",
"gateway_host": "10.66.66.10",
"connection_status": "connected",
"connection_mode": "wireguard_gateway"
```

这说明 buyer 侧语义也不是“直接连 seller 真实公网 IP”。

buyer 实际消费的是：

- seller 的 `WireGuard target`
- seller 上的 `gateway`
- `wireguard_gateway` 会话链路

### 3.5 Windows 本地 / Docker Desktop 视角下，Swarm NodeAddr 也曾经是 WG IP

来源：`d:\AI\Pivot_Client\seller_client\sessions\join_session_0421b90ccabe39e2\session.json`

关键片段：

```json
"expected_wireguard_ip": "10.66.66.10",
"distribution_name": "Windows + Docker Desktop",
"observed_wireguard_ip": "10.66.66.10",
"observed_advertise_addr": "10.66.66.10",
"observed_data_path_addr": "10.66.66.10"
```

```json
"swarm": {
  "NodeID": "sgwu3bfc8c7uss223tijw2jsm",
  "NodeAddr": "10.66.66.10",
  "LocalNodeState": "active",
  "ControlAvailable": false,
  "RemoteManagers": [
    {
      "Addr": "81.70.52.75:2377"
    }
  ]
}
```

这说明在 seller 本地看来，当时这台 Windows 节点已经是：

- `Swarm active`
- `NodeAddr = 10.66.66.10`
- 远端 manager 是 `81.70.52.75:2377`

也就是说，**Windows 本地这边并不是完全没 join 上。**

### 3.6 但 manager 最终验收看到的不是 WG IP

来源：`d:\AI\Pivot_Client\seller_client\sessions\join_session_0421b90ccabe39e2\session.json`

关键片段：

```json
"manager_acceptance": {
  "status": "mismatch",
  "expected_wireguard_ip": "10.66.66.10",
  "observed_manager_node_addr": "202.113.184.2",
  "matched": false,
  "detail": "manager_node_addr_mismatch"
}
```

这是整条证据链里最关键的一段。

它证明：

- 本地 `NodeAddr` 是 `10.66.66.10`
- 但 manager 最终认到的是 `202.113.184.2`
- 所以“seller 本地看起来是 WG IP”与“manager 最终按 WG IP 认 worker”之间，不是同一件事

## 4. 关键判断

### 4.1 可以确认的事情

从历史材料里，可以确认下面几件事：

1. Windows 历史路径不是完全不可用
2. `WireGuard` 到 `10.66.66.10` 曾经真实可达
3. buyer 会话也曾经通过 `wireguard_gateway` 访问 seller
4. seller 本地的 Docker Swarm 一度把 `NodeAddr` 设成了 `10.66.66.10`

### 4.2 不能误判的事情

但同时也必须明确：

1. 不能因为本地 `NodeAddr = 10.66.66.10`，就判断 manager 一定按 `10.66.66.10` 识别 seller
2. 不能因为 buyer 能通过 WG 到 gateway，就推导出 Swarm control-plane 地址语义已经正确
3. 不能把 “WireGuard 连通” 和 “Swarm 最终地址识别正确” 混成一个问题

## 5. 这条思路对当前架构意味着什么

如果平台目标是：

- buyer 通过平台发放的网络身份进入 seller runtime / gateway
- 平台内部最终以 seller 的专用 overlay IP 识别 worker

那么历史 Windows 路径给出的信息是：

### 5.1 正向意义

- Windows 本机 WireGuard 是有希望成立的
- buyer 通过 `gateway + WireGuard` 访问 seller runtime 的语义是成立过的
- seller 主机本地执行 `docker swarm join` 这条控制流没有问题

### 5.2 负向提醒

- 裸 `docker swarm join --token ... 81.70.52.75:2377` 不足以保证 manager 最终按 overlay / WireGuard IP 识别节点
- 即使 seller 本地 `docker info` 显示 `NodeAddr = 10.66.66.10`，manager 侧仍可能把它落成真实公网地址

## 6. 历史补救方向也已经留了痕迹

来源：`d:\AI\Pivot_Client\seller_client\bootstrap\windows\legacy\root-scripts\rejoin_wireguard.ps1`

关键片段：

```powershell
docker swarm join --token $jm.join_token --advertise-addr 10.66.66.10 --data-path-addr 10.66.66.10 $target
```

这段脚本本身就是一个很强的信号：

- 团队已经意识到要显式钉 `advertise/data-path`
- 真正待解决的问题不是“Swarm 完全 join 不上”
- 而是“join 之后 manager 到底按哪个地址识别 seller worker”

## 7. 一句话总结

这条历史 Windows 路径的真实情况应当表述为：

**Windows + Docker Desktop + 本机 WireGuard 这条链路曾经能够让 seller 本地 join Swarm，并让 server / buyer 通过 `10.66.66.10` 访问 seller；但 manager 最终并没有稳定按 `10.66.66.10` 识别该 worker，因此问题的关键不在于“WG 能不能通”，而在于“Swarm advertise / manager acceptance 是否真正对齐到 WireGuard IP”。**

## 8. 后续如果继续推进，应该怎么用这份结论

后续讨论时，建议固定用下面这套说法：

1. `WireGuard connectivity`
   - 指 seller/server/buyer 是否能经 `10.66.66.x` 互相到达

2. `local swarm identity`
   - 指 seller 本地 `docker info .Swarm.NodeAddr` 显示什么

3. `manager-accepted node identity`
   - 指 manager 最终把 worker 记成什么地址

只有第 3 点最终等于 `seller_overlay_ip`，平台才算真正完成了 “Swarm 按专用非真实 IP 识别 seller” 这件事。

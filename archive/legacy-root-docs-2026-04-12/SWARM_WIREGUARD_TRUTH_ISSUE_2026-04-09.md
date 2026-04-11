# Server Handoff: Swarm / WireGuard Truth Issue

更新时间：`2026-04-09`

## 背景

当前 Windows seller agent 的主线代码已经同步到服务器上的正式 client 目录：

- `/root/Pivot_network/Seller_Client`

当前线上相关目录是：

- seller client: `/root/Pivot_network/Seller_Client`
- backend: `/root/Pivot_network/Plantform_Backend`
- docker swarm / adapter: `/root/Pivot_network/Docker_Swarm`

## 当前问题

Windows seller worker 已经多次成功加入 swarm，但 manager 真相层记录的节点地址仍然稳定显示公网 IP，而不是 WireGuard IP。

当前核心现象：

- worker 本机 `docker info --format '{{json .Swarm}}'`
  - `NodeAddr = 10.66.66.10`
  - `LocalNodeState = active`
- manager 侧 `docker node inspect 1mwnvgqrg72jocqihbkxjrvdl --format '{{json .Status}}'`
  - `Addr = 202.113.184.2`

也就是说：

- worker 本地自报是 `10.66.66.10`
- manager 真相层仍记成 `202.113.184.2`

## 已确认的关键事实

### 1. 当前活动的 WireGuard 环境

服务器当前活跃的 WG 接口只有：

- `wg0 = 10.66.66.1/24`

当前 seller peer：

- `10.66.66.10/32`
- 有真实握手
- `wg show` 里 endpoint 是 `202.113.184.2:5675`

### 2. Docker daemon 所在环境

在 Windows 本机的 `docker-desktop` 环境里，已经能看到：

- `wg-seller = 10.66.66.10/32`
- 到 `10.66.66.1 dev wg-seller` 的路由

所以 `10.66.66.10` 并不是只存在于 Windows 宿主，而是已经进入 Docker daemon 所在环境。

### 3. manager 当前 swarm 控制面

服务器 manager 当前 swarm 信息里仍是：

- `NodeAddr = 81.70.52.75`
- `RemoteManagers[0].Addr = 81.70.52.75:2377`

当前 `dockerd` 监听：

- `*:2377`

这说明 worker 当前实际 join 的控制面入口仍是公网侧 `81.70.52.75:2377`。

### 4. 服务器上存在旧 WG 残留

虽然当前只有 `wg0` 在跑，但服务器还残留了一套旧的 `10.7.x.x` / `wg-home` 环境痕迹：

- `/etc/wireguard/archive/wg-home.conf.disabled`
- `/root/home-server.conf`
- `/root/wg-home-deploy`
- `wg-iptables.service`

其中 `wg-iptables.service` 现在还带着旧规则：

- `10.7.0.0/24`
- `UDP 51820`

这批旧残留目前不像是主根因，但建议纳入排查和清理。

## 已有推断

目前最值得测试的方向是：

- 不再让 worker 通过 `81.70.52.75:2377` 加入 swarm
- 而是尝试把 manager 的 swarm 控制面入口切到 WireGuard
- 也就是让 worker 走 `10.66.66.1:2377`

需要注意：

- WireGuard 的 peer endpoint 仍可能显示公网 IP，这本身不等于 Swarm 失败
- 真正要观察的是：
  - worker 本地 `NodeAddr`
  - manager `docker node inspect ... .Status.Addr`
  - backend / tcp validation / overlay 实际可达性

## 建议你在服务器上继续核查的事项

1. manager 的 swarm 控制面是否可以安全迁移到 `10.66.66.1:2377`
2. `docker node inspect ... .Status.Addr` 是否是 Docker 官方明确承诺等于 `advertise-addr`
3. 当前 Docker Desktop + swarm 场景下，`Status.Addr` 是否可能继续偏向公网出口
4. 是否需要：
   - clean leave
   - manager `node rm`
   - manager 切 WG control plane
   - worker 重新 join 到 `10.66.66.1:2377`
5. 是否应先清理服务器上的旧 `10.7.x.x` WireGuard 残留规则，避免干扰判断

## 本次同步说明

本地当前版本已作为正式 seller agent 同步目标，应该以服务器目录为准：

- `/root/Pivot_network/Seller_Client`

不应再使用：

- `/root/Pivot_network/Pivot_backend_build_team/seller_client`

该误同步目录已经删除。

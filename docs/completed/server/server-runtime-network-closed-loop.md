# 服务器侧完成态

## 结论

截至 `2026-03-26`，腾讯云服务器 `81.70.52.75` 已经承担了当前平台第一阶段的四个核心角色：

- Docker Swarm manager
- 私有镜像仓库入口
- WireGuard `wg0` hub
- 平台后端通过 SSH 操作的远端控制面

## 当前服务器侧实际承担的内容

### 1. Swarm manager

服务器当前是远端唯一 manager。

真实参数：

- host: `81.70.52.75`
- swarm manager port: `2377`

当前本机 `docker-desktop` 已真实加入为 worker，并且实际承载过：

- seller smoke service
- buyer runtime service

### 2. WireGuard hub

这台服务器上有多套 WireGuard，但当前项目使用的是 **Swarm / runtime 这套 `wg0`**。

真实参数：

- interface: `wg0`
- server address: `10.66.66.1/24`
- endpoint: `81.70.52.75:45182`
- server public key: `puGAoUTF0vyha+32vxQ+BBVOWXlCOUzhFoNe5tJ9hyo=`

当前阶段明确约束：

- seller 接入只走 `wg0`
- buyer session WireGuard 也只走 `wg0`
- 不使用服务器上另外两套 WireGuard

### 3. registry / Portainer 相关入口

服务器端已部署并验证过：

- registry
- Portainer

当前 seller registry 路线仍以 MVP 方式工作：

- registry 地址主要还是 `81.70.52.75:5000`
- seller 本地通过导入证书建立 trust

这仍然是过渡方案，不是最终域名证书方案。

## 从开始制作以来做过的主要修改

### 1. Swarm manager 初始化与验证

已完成：

- manager 初始化
- worker join token 获取
- manager overview 获取
- 远端 `node ls / service ls` 拉取

平台后端不是盲写假数据，而是通过 SSH 读取这台真实 manager 的信息。

### 2. seller peer 自动写入

seller onboarding 过程中，后端通过 SSH 自动把 seller peer 写入服务器 `wg0`。

真实效果是：

- seller 本地得到 `wg-seller`
- server `wg0` 上出现 seller peer
- seller 能 `ping 10.66.66.1`

### 3. buyer peer 按租期写入与撤销

buyer session WireGuard 现在也走这台服务器。

在租期开始时：

- 后端将 buyer peer 写入服务器 `wg0`

在 stop 或过期时：

- 后端将 buyer peer 从 `wg0` 撤销

### 4. stale peer 问题与修复

真实联调时发现：

- `wg0` 上同一 `AllowedIPs` 可能残留旧 peer
- 这会导致 buyer 能打到 hub，但 server 不知道该把 `10.66.66.10/32` 转发给哪个 seller peer

后续已经补成：

- 同一 `AllowedIPs` 的旧 peer 自动清理后再写入新 peer

这次修复后，buyer -> seller 的直连验证才完全成立。

## 真实验证过什么

### 1. seller -> server

真实确认过：

- seller `wg-seller` 能打到 `10.66.66.1`
- server `wg0` 上有 seller peer
- seller worker 加入 Swarm

### 2. buyer -> server -> seller

真实确认过：

- buyer lease 获取 `10.66.66.138/32`
- seller 在 `wg0` 中地址为 `10.66.66.10/32`
- buyer `ping 10.66.66.1` 成功
- buyer `Test-NetConnection 10.66.66.10 -Port 22` 成功
- `InterfaceAlias = wg-buyer`
- `SourceAddress = 10.66.66.138`

这证明 buyer 是通过当前项目使用的 `wg0` 这套内网直连 seller。

### 3. 租期结束回收

真实确认过：

- stop buyer lease 后，本地 `wg-buyer` 已卸载
- 服务器 `wg0` 中 buyer peer 已消失

## 当前边界

服务器侧当前仍有以下现实情况：

- `wg0` 上还存在一些历史空 peer，需要后续统一清理
- 服务器域名和证书还没买下来，registry 仍然是 IP + 本地证书 trust 的过渡态，这个需要格外注意！
- manager 仍以单节点 control-plane 方式运行
- 还没有独立的 buyer websocket gateway / 终端 gateway

## 当前推荐理解

服务器侧已经不是“先搭起来再说”的实验环境，而是：

- 当前 seller / buyer 第一阶段闭环的真实运行底座

后续继续做交易、GPU、交互式终端时，仍然会继续复用这台服务器侧的 `wg0 + manager + registry` 结构。

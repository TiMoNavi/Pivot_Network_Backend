# Pivot Network 卖家接入正式网络架构（Overlay Identity 路线）

## 文档定位

这份文档用于统一 Pivot Network 在卖家接入网络问题上的正式口径。

它描述的是平台的目标架构与正式语义，不是一次性的排障记录，也不是对多种路线的开放式讨论。

本文档面向内部产品、架构与工程协作，核心目的是统一下面这几个判断：

- 平台不把卖家的真实公网 IP 或局域网 IP 当成正式网络身份。
- 平台正式识别的是卖家节点的专用 `overlay IP`。
- 平台默认卖家接入方案是 `Windows seller agent + overlay identity`。
- `Docker Desktop` 不是正式默认 compute 路线。
- `WSL mirrored` 不是当前应当写成正式依赖的入站方案。
- 买家访问卖家时，语义应当是“进入平台编排出的 seller runtime/gateway 会话网络”，而不是“直接连卖家真实机器 IP”。
- `Docker Swarm` 最终必须把 seller worker 识别为 `seller_overlay_ip`，而不是 `seller_real_ip`。

## 背景与目标

Pivot Network 的业务目标，不是把卖家的真实电脑网络暴露给买家，而是把卖家提供的算力包装成一个平台可调度、可租赁、可回收的运行时资源。

在这个模型下，买家真正需要连接的是：

- 某个 seller 提供的 runtime
- 这个 runtime 对应的 gateway
- 以及平台在会话期内发放的访问网络身份

平台真正需要稳定识别的是：

- 哪个 seller 节点加入了平台
- 这个 seller 节点在调度系统中的正式网络身份是什么
- `Docker Swarm` 最终把这个 worker 认成了哪个地址

因此，平台的网络目标不是“暴露卖家真实 IP”，而是“给 seller compute 一个平台可控、可验证、可在控制面和调度面统一使用的专用网络身份”。

这个正式身份就是 `seller_overlay_ip`。

## 为什么不能把真实 IP 当正式身份

卖家是普通个人电脑用户，网络环境复杂且不可控。平台不能把成功率建立在卖家自己理解并维护网络拓扑的前提上。

真实网络地址存在下面这些系统性问题：

- 卖家公网 IP 可能根本不存在，设备常常处于多层 NAT 后。
- 局域网地址没有全局意义，同一个 `192.168.x.x` 或 `10.x.x.x` 在不同卖家机器上会重复出现。
- 家宽、校园网、公司网、热点、双路由、软路由、VPN、旁路由都会让真实地址与真实可达性脱钩。
- 卖家机器切换网络、重启路由器、运营商重新分配地址后，真实 IP 会变化。
- 很多卖家无法自行处理端口映射、防火墙、Hyper-V、WSL、虚拟网卡和复杂路由。

因此，平台必须把“真实网络地址”从正式身份里剥离出去。

平台可以观察 `seller_real_ip`，但不能依赖它作为：

- seller 节点身份
- buyer 访问目标
- Swarm worker 正式识别地址

## 三类地址语义

为了避免后续设计和实现混词，本文档固定使用下面三类地址概念。

### `seller_real_ip`

卖家的真实网络地址，包括但不限于：

- 公网 IP
- 局域网 IP
- NAT 后地址
- 宿主机在本地网络里的真实地址

平台可以把它作为诊断信息、可观测信息或临时连通性证据，但不把它作为正式网络身份。

### `seller_overlay_ip`

平台分配给 seller compute 的专用网络地址。

它的语义是：

- 平台内部正式身份
- seller 节点在会话网络中的稳定逻辑地址
- `Docker Swarm` 最终应识别和采用的 worker 地址

它不要求等于卖家的真实公网或局域网地址。

### `buyer_access_path`

买家进入 seller runtime 的访问路径。

它表示：

- 买家通过平台发放的网络配置进入会话网络
- 买家最终到达的是 seller side gateway/runtime

它不等价于“直接访问 `seller_real_ip`”。

## 正式架构结论

### 默认卖家接入方案

平台默认卖家接入方案是：

`Windows seller agent + overlay identity`

这意味着：

- 卖家默认不需要先理解 Linux、WSL、Docker Desktop、Hyper-V 或局域网映射。
- 卖家默认不需要让外部直接打进自己真实机器的网络地址。
- 卖家侧默认是一个 Windows 原生 seller agent，负责出站接入平台控制链路。
- 平台内部通过 `seller_overlay_ip` 标识这个 seller compute。

### 高级 compute 模式

平台可以保留 Linux/容器运行时能力，作为高级 compute 模式。

这类能力可以用于：

- 更强的隔离
- 标准化 Linux runtime
- 原生 Docker Engine / Swarm worker 执行

但它不应当成为所有卖家默认必须具备的前提条件。

换句话说：

- Linux compute 是高级能力
- 不是基础卖家接入的门槛

### 关于 Docker Desktop

`Docker Desktop` 可以用于开发、试验或某些临时路径验证，但它不是平台正式默认 compute 路线。

文档和实现都不应把“走 Docker Desktop”写成卖家接入的正式要求。

### 关于 WSL mirrored

`WSL mirrored` 当前不应被写成正式依赖的入口网络方案。

原因不是它绝对不能工作，而是平台不能把正式网络成功率建立在一个对普通卖家不可解释、对复杂网络环境不稳定、且当前已暴露平台级不确定性的入站路径上。

它可以继续作为实验路径、验证路径或高级模式中的实现选项，但不应写成正式默认入口依赖。

## 组件职责

### `seller agent`

卖家侧默认运行在 Windows 上的本地代理。

职责是：

- 主动连接平台控制面
- 进行本机环境探测和能力上报
- 获取 join material 或其他本地执行材料
- 执行卖家侧本地动作
- 回传运行状态、会话状态与网络证据

### `backend`

平台业务控制面。

职责是：

- 管理 seller、buyer、订单、会话与鉴权
- 生成 seller onboarding 会话与 join material
- 管理节点归属关系与平台读模型
- 协调 adapter、WireGuard 和 Swarm 的业务生命周期

### `swarm adapter / manager`

平台基础设施控制面。

职责是：

- 管理 `Docker Swarm`
- 管理节点 claim、inspect 和 runtime/gateway 编排
- 管理 seller/buyer 对应的网络租约和底层编排动作

它不是卖家或买家的正式前端入口。

### `wireguard / overlay network`

平台的专用 overlay 网络层。

职责是：

- 为 seller compute 分配专用 overlay 地址
- 为 buyer 会话发放访问会话网络所需的身份材料
- 为 runtime/gateway 提供统一的会话网络语义

平台正式识别的 seller 地址是这个 overlay 中的 `seller_overlay_ip`。

### `gateway/runtime`

买家真正消费的不是 seller 主机网络，而是平台编排出的 seller side `gateway/runtime`。

职责是：

- 承载买家访问入口
- 承载会话期内的运行时资源
- 接受平台发放的会话级访问路径

### `buyer client`

买家侧消费入口。

职责是：

- 接收平台发放的会话连接能力
- 进入 seller runtime 对应的会话网络
- 在租期内访问 seller side gateway/runtime

## 控制面与数据面

平台必须明确区分控制面和数据面。

### 控制面

控制面默认走 seller 主动发起的出站链路。

正式语义是：

- seller agent 主动连接平台
- seller agent 获取 join material 或其他执行材料
- seller agent 执行本地动作
- seller agent 上报状态、网络证据和运行结果

平台默认要求控制链路是“出站可用”的，而不是要求外部能直接打进卖家真实网络。

### 数据面

数据面不是“买家直接访问 seller_real_ip”。

正式语义是：

- 平台为 buyer 发放会话访问网络能力
- buyer 通过 `gateway + WireGuard/overlay session` 进入 seller side runtime
- buyer 到达的是平台编排出的会话网络终点

这里不应把“平台代理”写成唯一正式数据面。

平台代理、会话网关、overlay session、运行时入口都可以是数据面具体实现的一部分，但正式语义应保持一致：

买家访问的是平台编排出的 seller runtime/gateway 会话网络。

## Swarm 地址语义

`Docker Swarm` 侧必须遵守与平台一致的地址语义。

正式要求是：

- seller 节点加入 `Swarm` 后，manager 最终应识别为 `seller_overlay_ip`
- 不能把 `seller_real_ip` 当成正式 worker 地址
- 后续执行实现中，应把 `swarm advertise address` 钉到 `seller_overlay_ip`

这件事非常关键，因为平台控制面、节点归属、会话网络和 buyer 访问语义都依赖这个地址统一。

如果 `Swarm` 最终认的是卖家真实公网 IP 或局域网 IP，那么就意味着：

- 平台地址语义和调度语义不一致
- seller 节点正式身份不稳定
- buyer 会话网络与调度网络之间会出现错位

因此，`Swarm` 的正式识别地址必须与 `seller_overlay_ip` 对齐。

## 路线取舍

### 不作为正式默认路线的内容

下面这些内容不应被写成平台默认卖家接入前提：

- 要求卖家理解 `WSL`
- 要求卖家理解 `Docker Desktop`
- 要求卖家理解 `Hyper-V`
- 要求卖家自行处理局域网映射、端口映射、防火墙和复杂网络拓扑
- 要求外部必须能直接打进卖家真实网络地址

### 平台正式默认路线

平台正式默认路线应写成：

- `Windows seller agent`
- seller 主动建立出站控制链路
- 平台内部为 seller 分配并识别 `seller_overlay_ip`
- buyer 通过平台发放的会话网络路径进入 seller runtime/gateway

### 可以保留但不应阻塞主线的路线

下面这些路线可以作为高级模式、实验模式或后续扩展能力保留：

- Linux compute
- 原生 Docker Engine
- Swarm worker 深度接入
- 更强隔离的容器/虚机方案

但这些内容不应阻塞基础卖家接入主线。

## 买家访问语义

平台在所有文档和实现中，应当统一使用下面这句语义：

**买家连接的是平台编排出的 seller runtime/gateway 会话网络，而不是卖家真实主机网络地址。**

这句话决定了：

- 平台不以卖家真实 IP 为正式身份
- buyer 不直接消费 seller 真实网络拓扑
- seller 的正式调度身份应当是 `seller_overlay_ip`

## 固定表述

为了避免前后混词，后续文档与实现统一采用下面这些说法：

- `正式网络身份` = `seller_overlay_ip`
- `真实网络地址` = 卖家公网/LAN/NAT 地址
- `默认卖家接入方案` = `Windows seller agent + overlay identity`
- `高级 compute 模式` = Linux/容器运行时
- `buyer 访问路径` = `gateway + WireGuard/overlay session`
- `Swarm 正式识别地址` = `seller_overlay_ip`

后续文档中避免直接使用这些含混表述作为结论：

- “买家直接连卖家电脑”
- “卖家节点就是公网 IP”
- “走 Docker Desktop”
- “走代理”
- “走 WireGuard”

这些词如果必须出现，也应写成完整解释句，而不是单独当作架构结论。

## 最终结论

Pivot Network 在卖家接入网络问题上的正式口径应当是：

- 平台默认不依赖卖家真实 IP 作为正式身份
- 平台默认不要求外部能直接打进卖家真实网络地址
- 平台默认要求 seller agent 走出站可用的控制链路
- 平台内部以 `seller_overlay_ip` 标识 seller compute
- buyer 访问的是 seller runtime/gateway 会话网络
- `Docker Swarm` 最终必须把 seller worker 识别为 `seller_overlay_ip`

如果 Linux compute 在某些机器上暂时无法稳定成立，它不应阻塞基础卖家接入主线。

平台应先保证：

- 普通卖家可接入
- 网络语义可统一
- 调度身份可稳定
- buyer 会话访问语义可闭环

在这个前提下，再逐步增强高级 compute 能力，而不是反过来让高级 compute 成为所有卖家的统一门槛。

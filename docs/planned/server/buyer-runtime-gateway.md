# 买家运行时接入：服务器侧规划

## 目标

服务器侧需要解决的不是“把镜像给买家”，而是：

- 如何把 seller 节点上的 runtime 安全地、限时地提供给买家使用

这里的 server 侧职责应包括：

- runtime service 编排
- session gateway 编排
- 连接中继
- 网络隔离
- 会话回收

## 推荐的服务器侧结构

建议把买家接入拆成 4 层：

1. `Swarm manager`
2. `runtime service`
3. `session gateway`
4. `relay / access hub`

### 1. Swarm manager

职责：

- 决定把 runtime 下发到哪个 seller node
- 创建 / 删除 session 对应 service
- 保证 session 生命周期和 service 生命周期绑定

### 2. runtime service

这是买家真正要使用的镜像实例。

约束建议：

- 一次 session 对应一个独立 runtime
- runtime 运行在 seller node 上
- runtime 不直接暴露公网端口

### 3. session gateway

这个组件建议与 runtime session 绑定。

作用：

- 代理日志
- 代理 exec
- 代理 port-forward
- 管控会话级访问权限

它可以是：

- sidecar service
- 或 runtime 内嵌 agent

但职责必须明确：

- **对买家暴露有限控制面**
- **不直接暴露 seller 节点 Docker daemon**

### 4. relay / access hub

这是为了解决网络阻碍必须要有的一层。

职责：

- 接 buyer-Agent 的出站连接
- 接 seller 节点侧 gateway 的出站连接
- 做中继和鉴权

## 为什么服务器侧必须有 gateway

如果没有 gateway，买家端会直接撞上几个问题：

- 不知道 seller 节点是否可达
- 不知道怎么把本地工具安全地连到远端容器
- 很容易走向“直接暴露 Docker API”

所以 server 侧应该明确提供：

- 受限 session 入口

而不是：

- 原始主机入口

## 推荐的最小接入模式

### 模式 A：Relay 默认模式

建议第一阶段默认走：

- buyer-Agent <-> relay
- session gateway <-> relay

双方都主动出站：

- 对买家网络更友好
- 对 seller 网络更友好
- 不要求任何一侧暴露公网入站

### 模式 B：临时 WireGuard 模式

后续可让 buyer-Agent 也临时加入 WireGuard hub。

适合：

- 低延迟
- 持续 shell
- 更多端口转发

但建议晚于 relay 模式实现。

## runtime service 的最小编排建议

manager 收到 buyer 会话创建请求后：

1. 选择 seller node
2. 拉起 runtime service
3. 拉起 session gateway
4. 将两者放入同一个 session 网络
5. 记录 session_id -> service_name / node / gateway 信息

service 命名建议：

- `runtime-<session_id>`
- `gateway-<session_id>`

## session gateway 应提供的最小能力

第一阶段建议只提供：

- `exec`
- `logs`
- `stdin/stdout` 流
- 端口转发
- 文件上传 / 下载

不建议第一阶段提供：

- 原始 Docker daemon
- seller 主机 shell
- 跨 session 的容器控制

## 网络阻碍与端口策略

这是 server 侧必须正面处理的重点。

### 当前判断

买家和 seller 两边都不能假设有公网入站，所以：

- 不应依赖买家直接入站 seller
- 不应依赖 seller 直接暴露 runtime 到公网

### 当前推荐

- server relay 使用 `443`
- session gateway 和 buyer-Agent 都主动连到 relay
- relay 再做 session 粒度路由

## 认证与连接码在服务器侧怎么落

后端给出的是：

- `connect_code`

server 侧真正执行的则是：

- 将 `connect_code` 兑换成 `session_token`
- 将 `session_token` 绑定到 relay / gateway 通道

也就是说：

- 连接码只负责“开始接入”
- 长连接本身靠 session token

## 清理策略

server 侧必须把 cleanup 做成一等能力。

最小要求：

- 会话超时自动停 runtime service
- buyer 主动断开可提前 stop
- gateway 失联后做回收
- 清理 session overlay network

## 监控建议

服务器侧至少要能看到：

- session 是否创建成功
- runtime service 是否 running
- gateway 是否连上 relay
- buyer 是否已经连接
- session 是否已经 idle / expired

## 和当前 seller 模块的衔接

当前 seller 模块已经具备：

- WireGuard 接入
- 节点注册
- 节点进入 Swarm
- 节点可承载 smoke service

所以 server 下一步不是再重做 seller 侧，而是：

- 在 manager 上新增“面向 buyer session”的 runtime 编排层

## 当前推荐路线

建议顺序：

1. 先做 `RuntimeAccessSession -> runtime service + gateway`
2. 再做 relay
3. 再做 buyer-Agent
4. 最后才考虑 buyer WireGuard

## 关于证书的现实情况

当前 seller 侧 registry 相关链路仍然处于过渡态：

- 临时通过本地导入证书建立信任
- 还没有切到正式域名 + 公网可信证书

对于 buyer runtime 接入，这个问题更敏感，因为 relay / gateway 最终应尽量走：

- 标准 HTTPS
- 正式域名
- 公网可信证书

所以 server 侧 buyer relay 最终不应继续沿用“本地导证书”思路，而应尽快转向：

- `panel/api/relay` 正式域名
- 标准 TLS

## 一句话结论

如果买家要“像云服务器一样连接并使用 seller 节点上的镜像运行时”，服务器侧最合理的最小结构是：

- **Swarm runtime service + session gateway + relay**

而不是：

- **直接暴露 seller 节点 Docker daemon**

# 买家运行时接入规划

## 问题范围

当前这一步先不做：

- 交易
- 钱包
- 余额
- 浏览列表
- 推荐系统

当前只聚焦一个最小问题：

- 买家如何在本地拿到“某个 Docker 镜像在卖家机器上的一段时间使用权”

这里的“使用权”不应该理解成：

- 把镜像所有权给买家
- 让买家随意把镜像永久拉回自己电脑

而应该理解成：

- 平台在卖家节点上启动该镜像对应的运行时
- 平台把这个运行时的一段时间访问权授予买家
- 买家通过本地工具接入这个运行时

## 核心判断

### 1. 不建议让浏览器直接承担买家接入

原因很直接：

- 浏览器不适合处理本地 Docker 工具接入
- 浏览器不适合处理本地端口转发
- 浏览器不适合处理 WireGuard / 本地证书 / 临时 tunnel
- 浏览器也不适合长期维持一个稳定的“本地 docker 风格会话”

### 2. 建议明确引入最小 `buyer-Agent`

如果买家要“像云服务器一样连接并使用”，最小 buyer-Agent 是值得做的。

它不一定一开始就是复杂桌面应用，可以先是：

- 本地守护进程
- 或本地 CLI + 小型本地服务

作用：

- 接收平台返回的连接码
- 向平台后端兑换会话配置
- 在本地建立连接、端口转发、临时隧道
- 为买家提供统一入口

## 推荐的最小模型

### 推荐模型：不是“交付镜像”，而是“交付运行时会话”

买家点击平台上的：

- “连接到这台机器”

平台后端做的不是直接给 registry pull 权限，而是：

1. 选择目标 seller node
2. 选择目标 image
3. 创建一个短期 `RuntimeAccessSession`
4. 下发一个短期 `connect_code`
5. buyer-Agent 用这个 `connect_code` 在本地兑换真实接入参数

所以买家拿到的是：

- 一个会话
- 一个连接码
- 一组临时接入参数

而不是：

- 一个永久镜像授权

## 为什么不建议先做“买家本地 pull 镜像”

如果买家只是把镜像拉回本地跑，会立即破坏当前项目的 seller 侧算力模型：

- 计算不再发生在 seller 节点
- 时间使用权很难回收
- 镜像很容易被永久复制
- 平台失去会话结束控制

因此第一阶段更合理的定义是：

- 买家获得“远端运行时会话”的使用权

而不是：

- 买家获得“镜像文件”的所有权

## 最小业务对象

平台后端建议新增这些对象：

### `RuntimeAccessSession`

字段建议：

- `id`
- `buyer_user_id`
- `seller_node_id`
- `image_artifact_id`
- `status`
- `started_at`
- `expires_at`
- `ended_at`
- `access_mode`
- `network_mode`
- `connect_code_hash`
- `session_token`

### `RuntimeGateway`

字段建议：

- `session_id`
- `service_name`
- `relay_mode`
- `published_ports`
- `gateway_endpoint`
- `ssh_enabled`
- `ws_enabled`

### `ConnectCode`

字段建议：

- `session_id`
- `code`
- `expires_at`
- `redeemed_at`
- `redeemed_by`

## 后端最小接口建议

### 1. 创建接入会话

```text
POST /api/v1/buyer/runtime-sessions
```

输入：

- `seller_node_id`
- `image_artifact_id`
- `requested_duration_minutes`

输出：

- `session_id`
- `connect_code`
- `expires_at`

### 2. 兑换连接码

```text
POST /api/v1/buyer/runtime-sessions/redeem
```

输入：

- `connect_code`

输出：

- `session_token`
- `access_mode`
- `network_mode`
- `relay_endpoint`
- `wireguard_bundle`（可选）
- `local_tool_hint`

### 3. 查询会话状态

```text
GET /api/v1/buyer/runtime-sessions/{session_id}
```

输出：

- `status`
- `remaining_seconds`
- `node_summary`
- `gateway_summary`

### 4. 结束会话

```text
POST /api/v1/buyer/runtime-sessions/{session_id}/stop
```

## 建议的买家接入模式

### 模式 A：Relay 模式，作为默认 MVP

buyer-Agent 本地通过：

- `HTTPS`
- `WebSocket`

主动连平台后端或 server relay。

优点：

- 最适合 NAT / 校园网 / 家宽 / 企业网络
- 不要求买家或卖家开放入站端口
- 部署最简单

缺点：

- 流量要经过 server relay
- 延迟略高

### 模式 B：Buyer WireGuard 模式，作为下一阶段

buyer-Agent 通过连接码兑换一份临时 WireGuard profile，然后加入平台 hub。

优点：

- 网络路径更直接
- 适合端口转发、长连接、交互式 shell

缺点：

- 本地接入更复杂
- buyer 端也要处理本地网络与权限

### 当前建议

第一阶段先做：

- buyer-Agent + Relay

后续再补：

- buyer-Agent + 临时 WireGuard

## 买家在本地“怎么用”

### 推荐先做：本地命令行或本地小工具接入远端运行时

例如：

```text
pivot connect <connect_code>
```

连接成功后，buyer-Agent 可以提供：

- `pivot shell`
- `pivot logs`
- `pivot ports`
- `pivot cp`

这更像：

- 一台临时云主机
- 一个临时开发容器

### 不建议第一阶段直接暴露原始 Docker Daemon

原因：

- 原始 Docker API 权限太大
- 很难只限制到一个 session 容器
- 会把 seller 节点暴露成“远端 Docker 主机”

如果以后一定要兼容本地 Docker 语义，更合适的方式是：

- buyer-Agent 暴露一个受限的 session proxy
- 只代理当前 session 容器允许的操作

而不是：

- 直接让买家连 seller 的 Docker daemon

## 最小的 buyer-Agent 职责

buyer-Agent 第一阶段只需要做：

1. 接收连接码
2. 向后端兑换 session
3. 建立 relay 或 WireGuard
4. 提供本地 shell / exec / logs / port-forward
5. 在会话到期后自动断开

明确不需要一开始就做：

- 完整桌面 GUI
- 复杂文件管理器
- 镜像管理后台
- 多会话并发管理

## 网络阻碍的处理建议

买家接入复杂的真正原因不在 Docker，而在网络：

- 买家大概率在 NAT 后
- seller 也大概率在 NAT 后
- 不能假设双方都有公网入站
- 不能要求浏览器直接打本地或远端 Docker

所以这里应坚持：

- **所有关键连接都由 buyer-Agent / seller-Agent 主动出站**

这意味着平台设计应偏向：

- relay
- hub
- 反向连接

而不是：

- 直接要求买家入站到 seller 节点

## 当前推荐路线

如果只做最小能用版本，我建议顺序是：

1. 平台后端新增 `RuntimeAccessSession + connect_code`
2. server 侧新增 session gateway / relay 通道
3. buyer-Agent 做连接码兑换和本地 shell/port-forward
4. 把 session stop / timeout / cleanup 补齐

## 一句话结论

买家不应直接“获得镜像”，而应获得：

- **某个 seller 节点上、由某个 image 启动出来的临时运行时会话**

而这个会话最合理的本地接入方式是：

- **buyer-Agent + 连接码兑换 + relay 优先**

# Pivot Backend Build Team

这是一个面向“容器使用权 / 算力使用权交易”的多部件系统仓库。

当前系统不是单一后端，而是由四个主要部件组成：

- 平台后端：负责账号、节点、镜像商品、定价、订单、许可证、运行时会话、WireGuard、Swarm 联动
- 卖家客户端：负责把卖家机器接入平台，进入 WireGuard 和 Swarm，并发布可租用镜像
- 买家客户端：负责在本地代表买家使用平台资源，创建运行时会话，拉起 `wg-buyer`，执行代码或进入容器
- 平台前端：负责注册、登录、容器列表、容器详情、下单、许可证查看

这个 README 的目标不是讲实现细节，而是让人快速理解：

- 这个系统有哪些部件
- 每个部件负责什么
- 它们怎么协作
- 现在已经做到什么程度

## 当前系统是怎么工作的

可以把当前系统理解成四层。

### 1. 服务器侧

服务器当前承担平台的底座能力：

- Docker Swarm manager
- WireGuard hub
- Docker registry
- 被平台后端通过 SSH 控制的远端执行面

当前项目实际使用的 WireGuard 是服务器上的 `wg0` 这套。
卖家节点和买家租期内的 `wg-buyer` 都接到这套 `wg0` 上。

### 2. 平台后端

平台后端是整个系统的控制中枢。

它当前负责：

- 用户注册、登录
- 卖家节点令牌发放
- 节点注册、节点心跳、镜像登记
- 卖家镜像商品发布与 probe
- 价格源抓取与商品定价
- 买家钱包、账本、小时级用量扣费
- 买家订单与许可证 token 签发
- buyer runtime session 创建、续期、停止、状态查询
- seller / buyer WireGuard 凭证发放
- Swarm overview 和 worker join token

### 3. 卖家客户端

卖家客户端运行在卖家自己的机器上。

它当前负责：

- 安装器
- 本地 seller-Agent
- 本地 seller 网页控制面
- 登录平台
- 申请节点注册令牌
- 注册节点并持续发送心跳
- 拉取 CodeX runtime bootstrap
- 生成并激活 `wg-seller`
- 确保本机加入平台 Swarm
- 配置 registry trust
- 推送镜像到 registry，并向平台汇报镜像
- 将镜像发布为平台可售商品

一句话说，卖家客户端的职责是：

- 把“卖家机器”变成“平台可调度、可定价、可租用的节点”

### 4. 买家客户端

买家客户端运行在买家自己的机器上。

它当前负责：

- 本地 buyer CLI
- 本地 buyer 网页控制面
- 通过平台创建 runtime session
- 上传单文件代码、目录 / zip、GitHub 仓库后执行
- 创建 shell session
- 在容器内执行 `exec`
- 拉起 `wg-buyer`
- 在租期内通过 WireGuard 直接访问 seller 节点

一句话说，买家客户端的职责是：

- 把“买家本地操作”转换成“平台控制下的 seller 侧临时运行时使用”

### 5. 平台前端

`frontend/` 是一个最小平台前端。

它当前负责：

- 注册
- 登录
- 查看可租用容器商品
- 查看容器商品详情
- 查看钱包余额与流水
- 下单
- 查看订单
- 查看许可证 token

这里要注意：

- 平台前端当前不会直接启动 buyer runtime
- 它的下单行为本质上是“签发订单和许可证”
- 后续再由买家本地客户端拿许可证去做实际使用

## 主要目录说明

### `backend/`

平台后端。

关键职责：

- 平台 API
- 定价与计费
- buyer runtime session
- Swarm / WireGuard / registry 相关控制逻辑

如果你想看“平台到底有哪些核心能力”，先看这里。

### `seller_client/`

卖家本地客户端。

关键职责：

- 卖家机器接入平台
- 卖家本地网页控制面
- `wg-seller`
- Swarm worker 加入
- 镜像 push / report

如果你想看“卖家如何把自己的机器接入平台”，看这里。

### `buyer_client/`

买家本地客户端。

关键职责：

- runtime session 创建
- shell / exec
- archive / GitHub 执行
- `wg-buyer`
- 本地 buyer 网页控制面

如果你想看“买家如何实际使用 seller 的容器运行时”，看这里。

### `frontend/`

最小平台前端。

关键职责：

- 用户入口页面
- 商品列表、详情、下单、许可证查看

当前由后端直接静态挂载：

- `/platform-ui`

### `docs/`

文档目录。

其中最重要的是：

- `docs/completed/`

这里记录的是已经做完并且验证过的内容。

推荐先看：

- [docs/completed/client/seller-client-closed-loop.md](docs/completed/client/seller-client-closed-loop.md)
- [docs/completed/client/buyer-client-closed-loop.md](docs/completed/client/buyer-client-closed-loop.md)
- [docs/completed/platform-backend/platform-backend-closed-loop.md](docs/completed/platform-backend/platform-backend-closed-loop.md)
- [docs/completed/server/server-runtime-network-closed-loop.md](docs/completed/server/server-runtime-network-closed-loop.md)

## 当前已经跑通的闭环

### 卖家闭环

已经真实跑通：

- 卖家从 0 开始接入平台
- 卖家节点注册成功
- `wg-seller` 激活成功
- 节点进入平台 `wg0` 内网
- 节点加入 Docker Swarm
- 远端 manager 能调度 smoke service 到卖家节点

### 买家运行闭环

已经真实跑通：

- 买家提交代码
- 代码在 seller 节点的容器里运行
- 输出回传给 buyer 本地

### 买家直连 seller 闭环

已经真实跑通：

- buyer session 获得 `wg-buyer`
- buyer 进入平台 `wg0`
- buyer 通过 `wg-buyer` 直接打到 seller 节点 `10.66.66.x`

### 定价与计费 v1

后端现在已经有：

- 节点级镜像商品 `ImageOffer`
- 官方价格源归一化
- 商品探测与时价生成
- buyer wallet
- 小时级 ledger
- usage charge
- 订单与许可证 token

当前这是后端闭环，已经有测试覆盖，但还没有做完整支付产品。

### 平台前端最小闭环

平台前端现在已经能：

- 注册、登录
- 看商品
- 看详情
- 下单
- 拿许可证

## 当前的产品边界

虽然系统已经跑通了多条关键链路，但当前还不是完整生产产品。

目前仍然属于“可运行、可联调、可继续扩展”的阶段。

还没有完成的典型内容包括：

- 真正的支付与充值
- 完整交易撮合与风控
- GPU 商品完整产品化
- 真正交互式网页终端
- 端口转发
- buyer 客户端直接消费平台前端签发的许可证 token
- 生产级监控、审计、运维控制面

## 当前建议的人类理解方式

不要把这个系统理解成“一个网站 + 几个脚本”。

更准确的理解是：

- 服务器是平台底座
- 后端是调度与计费中枢
- 卖家客户端负责把卖家机器接入平台
- 买家客户端负责实际使用 seller 侧运行时
- 平台前端负责用户操作入口、商品展示和许可证签发

也就是说，平台前端负责“交易入口”，本地客户端负责“实际执行”。

## 当前常见入口

### 启动后端

在 `backend/` 下运行：

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 平台前端

后端启动后直接访问：

```text
http://127.0.0.1:8000/platform-ui
```

### 卖家本地网页

```powershell
python seller_client\agent_server.py
```

默认地址：

```text
http://127.0.0.1:3847
```

### 买家本地网页

```powershell
python buyer_client\agent_server.py
```

默认地址：

```text
http://127.0.0.1:3857
```

## 推荐阅读顺序

如果是第一次接手这个仓库，建议按这个顺序读：

1. 先读本 README，知道系统部件和职责
2. 再读 `docs/completed/` 下的四份闭环文档
3. 再看 `backend/` 的 API 路由
4. 再看 `seller_client/` 和 `buyer_client/`

这样会比直接从代码文件切进去更容易建立全局认识。

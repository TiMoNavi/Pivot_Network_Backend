# Pivot Network 后端代码评估报告

更新时间：`2026-04-05`

## 1. 评估范围

这次我把“整个后端代码”按实际调用链分成两部分一起评估：

1. `Backend/`
   平台主后端，负责用户、业务状态、数据库、审计、平台接口。
2. `Docker_Swarm/Docker_Swarm_Adapter/`
   基础设施适配器，负责实际调用 Docker Swarm 和 WireGuard。

如果只看 `Backend/`，会低估系统真实能力，因为它的很多核心动作都依赖 Adapter。

---

## 2. 一句话结论

这不是一个只有脚手架的空项目，而是一套已经接上真实数据库和真实 Swarm/WireGuard 适配器的“可运行原型后端”。

截至 `2026-04-05`，我能确认：

- 主平台后端可以启动，数据库迁移已经到 `head`，健康检查和就绪检查正常。
- Adapter 可以启动，健康检查正常，而且只读的 Swarm 查询接口在当前机器上可用。
- 代码主线已经覆盖 `auth -> seller -> buyer -> runtime session -> platform maintenance`。

但我也必须明确说明：

- 它更像“内部可跑的原型 / Phase 1 平台后端”，还不是安全、完整、可公网发布的正式交易平台。
- 核心写路径虽然代码已落地，但我这次没有对真实 Swarm 做破坏性写操作验证，所以不能把“全链路生产可用”直接下结论。
- 当前存在明显的安全和业务边界问题，尤其是权限设计、价格体系、access code 生命周期和 Adapter 异常处理。

---

## 3. 这套后端的功能和作用

### 3.1 平台主后端 `Backend/` 的作用

它是整个平台的业务控制层，负责：

- 用户注册、登录、登出、当前用户查询
- 基于 bearer token 的会话鉴权
- 按角色区分 `buyer`、`seller`、`platform_admin`
- 维护平台数据库中的业务主数据
- 维护 Swarm 同步后的读模型
- 对接 Adapter，并把基础设施动作包装成平台工作流接口
- 提供平台管理视图和维护接口
- 记录 activity 和 operation log
- 提供 runtime session 刷新、回收、access code 回收 worker

### 3.2 Adapter 的作用

它是基础设施执行层，负责：

- 读取 Swarm 总览、节点、服务、任务状态
- 提供节点 join material、claim、availability、remove
- 校验 runtime image
- 探测节点能力
- 创建 / 查询 / 删除 runtime session bundle
- 管理 WireGuard peer

### 3.3 实际架构关系

真实调用链是：

`Client -> Platform Backend -> Docker Swarm Adapter -> Docker Swarm / WireGuard`

也就是说：

- 平台后端负责“业务状态机”
- Adapter 负责“基础设施读写”
- PostgreSQL 负责“平台业务状态 + 同步读模型”

---

## 4. 已经实现的功能清单

### 4.1 `auth`

已实现：

- 注册
- 登录
- 登出
- `/auth/me`
- session token 发放、哈希存储、过期校验、撤销

### 4.2 `seller`

已实现：

- 查询平台 runtime base image
- 查询 runtime contract
- 申请节点接入材料
- 查询 seller 自己的节点
- 查看节点 claim 状态
- 上报 seller image
- 记录 image artifact / image offer / capability snapshot

### 4.3 `buyer`

已实现：

- 查看 catalog offers
- 创建订单
- 签发 access code
- 兑换 access code
- 创建 runtime session
- 查询 runtime session
- 获取 connect material
- 停止 runtime session

### 4.4 `platform_admin`

已实现：

- 平台 overview
- Swarm overview 透传
- 手动触发 swarm sync
- 节点列表 / 节点详情
- activity 列表
- 订单列表
- runtime session 列表 / 详情 / 手动刷新
- operation log 列表
- 手动触发 runtime refresh / runtime reaper / access code reaper

### 4.5 `swarm sync`

已实现：

- 把 `cluster / node / node labels / service / task` 同步入库
- 记录 `swarm_sync_runs`
- 记录 `swarm_sync_events`
- 记录操作日志

### 4.6 `runtime session`

已实现：

- session 建档
- 调用 Adapter 创建 runtime bundle
- 同步 gateway endpoint
- 同步 wireguard lease
- 查询 connect material
- 停止 session
- session 刷新
- session 过期回收

### 4.7 `workers`

已实现：

- runtime refresh worker
- runtime session reaper
- access code reaper
- 既支持手动 API 触发，也支持内建后台任务

但默认配置下它们不会自动启动，见后文“能力边界”。

---

## 5. 我对“能否正常运行”的判断

## 5.1 已完成的实际验证

我在当前机器上做了以下验证：

### 平台主后端 `Backend/`

- `python -m compileall Backend/backend_app` 通过
- `Backend/tests/test_health.py` 通过
- PostgreSQL 可连接，`ping_database()` 返回正常
- Alembic 当前版本为 `0005_runtime_session (head)`
- `GET /api/v1/ready` 返回 `200`
- `GET /` 返回 `200`

### Adapter `Docker_Swarm_Adapter`

- `python -m compileall Docker_Swarm/Docker_Swarm_Adapter/app` 通过
- `GET /health` 返回 `200`
- 当前机器上 `docker` 可用
- 当前机器上 Swarm 状态为 `active`
- 当前机器上 WireGuard 配置可读
- 在正确加载环境变量后，`GET /swarm/overview` 返回 `200`
- 在正确加载环境变量后，`GET /swarm/nodes` 返回 `200`

### 当前环境下的结论

在 `2026-04-05` 这台机器上，这套系统的“启动 + 数据库 + 基础健康检查 + Adapter 只读基础设施查询”是可以正常工作的。

---

## 5.2 我对运行性的最终判断

### 可以确认正常运行的部分

- 平台主 API 框架本身可运行
- PostgreSQL 连接和 Alembic 迁移链可运行
- 健康检查 / 就绪检查可运行
- Adapter 进程可运行
- Adapter 与当前机器上的 Docker Swarm / WireGuard 的只读集成可运行

### 不能直接下“完全正常”结论的部分

我没有执行下面这些真实写操作，因为它们会直接修改当前 Swarm / WireGuard 状态：

- 节点 claim / availability / remove
- runtime bundle create / remove
- WireGuard peer apply / remove

因此更准确的结论应该是：

> 这套后端已经达到“主服务可跑、读链路已验证、写链路代码完整”的状态；
> 但“对真实基础设施的全链路写操作完全可用”这件事，本次评估只能给出代码级判断，不能给出完整实测背书。

---

## 6. 能力边界在哪里

这部分很重要。它回答的是“这套后端能做什么，不能做什么”。

### 6.1 已经具备的边界

它已经不是单纯用户系统，而是一个“算力平台控制层原型”：

- 可以做用户身份和角色管理
- 可以把 Swarm 状态同步成平台数据库读模型
- 可以把 seller 镜像上报成 offer
- 可以让 buyer 下单、兑换 access code、创建 runtime session
- 可以通过 Adapter 间接驱动 runtime + gateway + wireguard
- 可以做 session 刷新、过期清理、操作审计

### 6.2 当前还没有真正做完的边界

#### 1. 没有完整的价格和交易闭环

代码里虽然有 `current_billable_price`、`OfferPriceSnapshot`、`issued_hourly_price` 这些字段，但实际业务流里没有真正的价格计算和结算引擎：

- seller 上报镜像时不会计算价格
- offer 可能是 `offer_ready`，但价格仍然是 `None`
- buyer 下单时 `issued_hourly_price` 可能直接写入 `None`
- 没有支付、钱包、扣费、退款、账单

所以它更像“资源申请 / 凭证发放系统”，还不是完整商业交易系统。

#### 2. 远端节点能力验证不完整

Adapter 的 `validate_runtime_image()` 和大部分校验逻辑，是在 Adapter 所在主机本地执行的：

- `docker pull`
- `docker image inspect`
- `docker run`

这意味着：

- 它更偏向“管理节点本地验证”
- 对真正远端 compute node 的镜像可拉取性、GPU 可见性、运行时差异，并没有完全覆盖
- `probe_node()` 对远端节点只能拿到 `docker node inspect` 级别信息，缺少真正的远程主机深度探测

#### 3. 默认没有自动后台维护

虽然 worker 已经实现，但默认配置 `BACKEND_ENABLE_BUILTIN_WORKERS=false`。

这意味着如果不手动调用 maintenance API，或者不显式开启内建 worker：

- runtime session 不会自动刷新
- 过期 session 不会自动回收
- 过期 access code 不会自动清理

#### 4. 没有 HA / 分布式调度设计

当前 worker 是“进程内后台任务”，适合单实例后端。

如果未来后端跑多副本：

- 可能会重复执行 maintenance job
- 没有分布式锁
- 没有队列系统
- 没有独立 scheduler

#### 5. 没有完整的平台前端 / Windows 客户端闭环

仓库里已经有平台 API，但：

- seller client / buyer client 不是本目录的主体
- 平台管理 UI 不是这里的重点
- 更接近“后端控制面已成型，客户端产品面未完成”

---

## 7. 关键风险和明显问题

下面这些不是“以后可以优化的小问题”，而是我认为当前最需要正视的点。

### 7.1 高风险：可以直接自注册成 `platform_admin`

`Backend/backend_app/services/auth_service.py` 允许公开注册角色：

- `seller`
- `buyer`
- `platform_admin`

而 `/auth/register` 是公开接口。

这意味着任何知道接口的人，理论上都可以直接注册管理员账号。这是当前最严重的安全问题之一。

### 7.2 高风险：`/users` 接口完全未鉴权

`Backend/backend_app/api/routes/users.py` 中：

- `GET /users/` 无鉴权
- `POST /users/` 无鉴权

而且 `UserCreate.role` 没有限制死角色范围。

这意味着：

- 任意调用者都能列出用户
- 任意调用者都能创建用户
- 理论上还能直接创建 `platform_admin`

如果这个服务对外开放，目前的权限模型基本不安全。

### 7.3 高风险：Adapter 不可达时，后端并不会稳定转成业务错误

`Backend/backend_app/clients/adapter/client.py` 只捕获了 `httpx.TimeoutException`，没有捕获连接失败类异常。

我实际验证了：当 Adapter 指向一个不可连接地址时，会直接抛出 `ConnectError`，而不是统一包装成 `AdapterClientError`。

这会导致：

- Adapter 宕机 / 地址错误 / 拒绝连接时
- 后端部分接口会抛出未预期异常
- 很可能返回 `500`，而不是稳定的 `502/504`

### 7.4 业务问题：access code 不是严格一次性

当前逻辑是：

- access code 兑换后状态变成 `redeemed`
- 创建 runtime session 时，只检查“这个 access code 当前是否已有活动 session”

这意味着：

- 如果旧 session 已结束
- 同一个 `redeemed` access code 仍然可能再次创建新 session

也就是说，access code 更像“可重复使用的 session 凭证”，而不是严格单次消费券。

### 7.5 业务边界问题：offer 可以 ready，但没有价格闭环

当前 `seller image report -> offer_ready` 的判断只看：

- validation
- probe

不看：

- 价格是否已计算
- 计费模型是否有效
- 库存 / 配额是否足够

所以它可以完成“技术可运行性筛选”，但还没有完成“商业可售性筛选”。

### 7.6 测试覆盖很薄

`Backend/tests/` 当前只有一个健康检查测试。

没有看到覆盖以下关键流程的自动化测试：

- 注册 / 登录 / 鉴权
- swarm sync
- seller image report
- buyer order / access code
- runtime session create / stop
- worker reaper / refresh

这意味着“代码看起来闭环”和“长期维护稳定”之间还有明显距离。

### 7.7 文档存在时间差

`Backend/README.md` 认为主线已经落地，`Backend/docs/platform-backend-implementation-plan.md` 还把后端描述成 scaffold 阶段。

从源码来看，实际状态更接近：

- 已不是空 scaffold
- 但也还没到 production-ready

文档需要统一口径。

---

## 8. 最终判断

## 8.1 如果你的问题是：“它现在到底是什么？”

我的判断是：

> 它是一套已经具备真实后端骨架、真实数据库、真实 Swarm Adapter 接口、并且主业务流已经落地的 Phase 1 平台后端原型。

不是 demo，也不是只画表不写逻辑的设计稿。

## 8.2 如果你的问题是：“它能不能正常运行？”

我的判断是：

> 可以运行，而且当前环境下基础运行已经被我实际验证通过。

更具体地说：

- 平台后端能跑
- 数据库能连
- 迁移是通的
- Adapter 能跑
- Adapter 的只读查询是通的

但如果把“正常运行”定义成“能安全地对公网开放并承接正式业务”，那答案是：

> 还不能。

主要原因不是“代码完全没写完”，而是：

- 安全边界还不够
- 商业交易能力还不完整
- 写路径没有在本次评估中做真实破坏性验证
- 自动化测试覆盖明显不足

## 8.3 如果你的问题是：“能力边界在哪里？”

我的判断是：

> 它现在最适合的定位，是内部环境 / 小范围受控环境下的算力平台控制后端。

它已经能做：

- 平台用户与角色
- Swarm 状态同步
- seller 镜像上报成 offer
- buyer 订单、access code、runtime session
- 适配器驱动 runtime / gateway / wireguard
- 审计与维护

它暂时还不能完整承担：

- 正式商业计费系统
- 高安全等级公网平台
- 多副本高可用后台调度
- 对远端 compute node 的强一致能力验证

---

## 9. 建议优先级

如果下一步要继续推进，我建议优先做这 5 件事：

1. 立刻封住权限漏洞
   禁止公开注册 `platform_admin`，并给 `/users` 全量加鉴权。
2. 修复 Adapter 连接错误的统一异常包装
   保证 Adapter 不可用时后端稳定返回业务错误。
3. 重新定义 access code 生命周期
   明确它是“一次性消费”还是“可重复使用凭证”。
4. 把价格逻辑真正接上
   至少保证 `offer_ready` 前已有有效价格。
5. 补关键集成测试
   至少覆盖 `auth / seller report / buyer order / runtime session / swarm sync / workers`。

---

## 10. 总结

这套后端的真实状态，不应该再叫“后端骨架”，而应该叫：

> “已经可跑、主线闭环、但仍处在原型到生产之间的后端控制面系统”。

如果目的是继续开发，它的基础已经够用了。

如果目的是立即上线对外提供正式服务，它还需要先补安全、测试和交易闭环。

# Pivot Network 当前项目 Brief

更新时间：`2026-04-11`

## 当前项目结论

当前 repo 已经不再是“只有卖家接入、没有商品化”的阶段，也还没有进入“买家 runtime 会话正式闭环已经落地”的阶段。

当前真实状态应按下面这条主线理解：

- 卖家本地接入主线已经存在并可运行
- backend 已经能把 `verified` seller 节点自动商品化成真实 `Offer`
- 买家产品主语义已经定为 `云主机会话 / RuntimeSession`
- buyer 侧正式实现还没有完成，当前仍以文档规格为准

换句话说，项目已经具备：

- `Seller_Client -> verified node -> backend assessment -> listed offer`

但还没有完全具备：

- `listed offer -> order -> access grant -> runtime session -> shell / task / artifacts`

## 当前阶段定位

当前项目阶段应固定理解为：

- `phase3` 末期
  - 核心是验证平台上架逻辑
  - 也就是验证 `verified node -> assessment -> listed offer`
- `phase4`
  - 买家客户端设计与实施规格
  - 收口 `grant-first + RuntimeSession + WireGuard + shell/workspace/task`
- `phase5`
  - 卖家、平台、买家三段联调闭环
  - 验证 `seller node -> offer -> order -> grant -> runtime session`

## 当前代码真相

### Seller 侧

- `Seller_Client` 继续是正式卖家入口
- seller 本地执行 `docker swarm join`
- seller client 不直连 adapter
- seller 接入完成标准仍然是 manager 侧确认 worker `Ready` 且存在可执行或运行中的 task

### Backend 侧

- `Plantform_Backend` 已保存 seller onboarding 真相
- backend 已新增 capability assessment 与 offer commercialization
- `verified` onboarding session 现在可以自动触发：
  - capability assessment
  - `compute_node_id` 幂等 upsert offer
  - assessment 失败时自动下架已有 listing

### Buyer 侧

- `Buyer_Client/` 目录已经恢复为当前 repo 的正式买家端目录
- buyer 主语义已经固定为：
  - `Order`
  - `AccessGrant`
  - `RuntimeSession`
  - `TaskExecution`
- 当前 buyer 仍以文档规格为主，不应误判为 runtime 会话链已经实现完成

## 当前项目级闭环目标

当前项目后续必须跑通的完整闭环固定为：

1. 卖家在本地 `Seller_Client` 登录并创建 onboarding session
2. 卖家本地准备 WireGuard、执行 join、提交 probes / `join-complete`
3. backend 生成 seller onboarding 真相，并把 session 推到 `verified`
4. backend 对 `verified` 节点做 capability assessment
5. backend 按 `compute_node_id` 生成或更新真实 `listed` offer
6. 买家在平台前端浏览真实 offer、创建 order、激活订单
7. backend 签发 `AccessGrant`
8. 买家在本地 `Buyer_Client` 拉取或导入 grant
9. buyer client 生成 WireGuard keypair，兑换 grant 创建 `RuntimeSession`
10. backend 调 adapter 创建 runtime bundle 与 buyer WireGuard lease
11. buyer client 通过 WireGuard 进入 shell，上传项目、执行任务、查看日志、下载产物

这条链的产品层语义固定为：

- seller 卖的是可售算力节点
- buyer 买的是云主机会话，不是 seller 裸机器 IP

## 当前已完成与未完成边界

### 已完成

- seller onboarding 主线
- backend seller truth chain
- backend verified-node 商品化
- `/offers` 对接真实自动生成 offer 的代码主线
- buyer 产品语义与闭环目标文档定稿

### 未完成

- buyer `grant-first` 正式实现
- `RuntimeSession` 落库与状态机
- adapter runtime bundle connect metadata 补齐
- buyer client 的 WireGuard / shell / workspace / task 正式能力
- seller 到 buyer 的完整运行态闭环联调

## 当前固定口径

- `docker swarm join` 永远由 seller 主机本地执行
- backend 负责 seller onboarding 与商品真相
- adapter 负责基础设施控制，不负责交易真相
- `verified node -> offer` 现在属于 backend 正式职责
- buyer 正式消费对象是 `RuntimeSession`，不是 seller target 或 seller IP
- `activate order = issue grant`
- `redeem grant + wireguard public key = create runtime session`

## 当前推荐读文顺序

1. `docs/runbooks/current-project-state-and-execution-guide.md`
2. `PROJECT.md`
3. `架构说明.md`
4. `个人算力交易平台MVP技术方案.md`
5. `Seller_Client/docs/current-seller-onboarding-flow-cn.md`
6. `Plantform_Backend/README.md`
7. `Buyer_Client/docs/current-buyer-purchase-flow-cn.md`
8. `Docker_Swarm/Docker_Swarm_Adapter/README.md`

## 当前实施优先级

1. 在 `phase3` 末期继续验证平台上架逻辑并稳定 seller 商品化主线
2. 进入 `phase4`，补 buyer 实施规格，收口 runtime session / task contract
3. 在 backend 落 `grant-first + runtime session` 模型
4. 在 buyer client 落 WireGuard / shell / workspace / task
5. 进入 `phase5`，做 seller 到 buyer 的完整闭环联调

# CCCC Phase 4 Current State

更新时间：`2026-04-11`

这份文档只写当前 `phase4 / phase5` 的已确认事实、阶段起点和当前缺口。

## 1. 当前阶段起点

当前项目不再是 `phase2 seller Windows 接入纠偏` 阶段。

当前阶段起点应固定理解为：

- `phase3` 末期 seller 真实 join 与商品化已经进入验证阶段
- `phase4` 进入 buyer 客户端实施
- `phase5` 准备 seller、platform、buyer 三段联调闭环

## 2. 当前 repo 已确认事实

### Seller / Platform 侧

当前 repo 已有：

- `Seller_Client` 正式 seller 本地入口
- `Plantform_Backend` seller onboarding truth chain
- `Plantform_Backend` verified-node 商品化
- `Docker_Swarm_Adapter` 的：
  - `join-material`
  - node inspect / claim
  - `nodes/probe`
  - `runtime-images/validate`
  - runtime bundle create / inspect / remove
  - WireGuard peer apply / remove

### Buyer 侧

当前 repo 已有：

- 正式 `Buyer_Client/` 目录
- 买家主语义文档：
  - `Order`
  - `AccessGrant`
  - `RuntimeSession`
  - `TaskExecution`

当前 repo 仍未完成：

- buyer `grant-first` 正式接口闭环
- `RuntimeSession` 状态机
- buyer WireGuard / shell / workspace / task 正式链

## 3. phase4 固定起跑线

`phase4` 的起跑线不是 seller onboarding 初期，而是：

- seller 真实 join 已成立
- seller 节点已被 backend 验收
- seller 节点在 assessment 可售时已能生成真实 offer

如果这条起跑线不成立，`phase4` 不应继续推进 buyer 端实现。

## 4. 当前最大缺口

当前最大缺口不在 seller onboarding，而在 buyer 会话链：

1. 交易骨架到 runtime session 之间还没接通
2. grant 还不能真实兑换会话
3. Buyer_Client 还没成为正式 shell / workspace / task 入口
4. Windows buyer 本地链路还没有实施和验证

## 5. 当前 WireGuard 纪律

固定遵守：

- manager control-plane 地址继续使用 `10.66.66.1`
- seller 节点继续使用 seller onboarding 验收出来的 seller 地址
- buyer runtime lease 不能复用 seller / manager 地址

默认推荐：

- buyer runtime lease：`10.66.66.200 - 10.66.66.250`

## 6. 当前 operator 远控 Windows 边界

Windows 远控当前只作为 operator 实施与验证入口。

首选入口：

- `ssh win-local-via-reverse-ssh`

备用入口：

- `ssh win-local-via-wg`

它们不等于产品成功标准。

## 7. phase5 最终成功标准

最终必须做到：

- 买家在 Windows 本地启动 `Buyer_Client`
- 在网页中通过 `CodeX` 自然语言描述任务
- 自动建立 runtime session、拉起 buyer WireGuard、打开 seller runtime shell
- 自动或半自动把工作区传递到 runtime，并完成 task
- 买家既能访问 seller 容器 shell，又能完成 task

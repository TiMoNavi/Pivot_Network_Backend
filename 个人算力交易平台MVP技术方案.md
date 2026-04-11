# 个人算力交易平台 MVP 技术方案

更新时间：`2026-04-12`

## 当前文档定位

这份文件现在保留为“项目目标摘要”，不再承担阶段实施计划。

如果你要看当前真正有效的内容，优先读：

1. `PROJECT.md`
2. `docs/runbooks/current-project-state-and-execution-guide.md`
3. `docs/tutorials/seller-buyer-e2e-guide-cn.md`
4. `项目名词说明.md`

## 当前 MVP 已完成到哪里

当前 MVP 已经完成并验证：

- seller 接入
- seller 节点商品化成真实 offer
- buyer 通过 grant 建立 runtime session
- buyer 通过 WireGuard 进入 shell / workspace / task
- 一轮真实稳定性测试（3 条 bounded 场景）

## 当前还没定义什么

当前没有新的既定 `Stage8`。

如果后续要继续推进，建议重新定义新的范围，例如：

- 运维产品化
- 自动化回归
- 更强的 session 生命周期能力
- 监控 / 告警 / 审计

## 历史提醒

这份文件不再按旧 `phase3 / phase4 / phase5` 节奏描述当前实施状态。
旧的阶段性讨论应视为历史背景，而不是当前作战文档。

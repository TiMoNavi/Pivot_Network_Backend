# Plantform Backend

更新时间：`2026-04-12`

`Plantform_Backend` 当前已经不是 seller onboarding 的早期骨架，而是完成并验证过的正式业务真相面。

## 当前已完成并验证的能力

- seller onboarding session 真相链
- `verified -> capability assessment -> listed offer`
- `order -> access grant -> runtime session`
- buyer `RuntimeSession` 读取与生命周期接口
- 与 `Docker_Swarm_Adapter` 的 runtime bundle / WireGuard 协同
- 真实 buyer/runtime 链路支撑
- 稳定性场景下的业务真相与状态读取

## 当前后端在整体系统里的职责

后端负责：

- 账号与会话
- seller onboarding 真相
- manager acceptance / effective target / truth authority
- offer / order / access grant / runtime session 业务真相
- 编排 adapter 与 WireGuard 的业务语义

后端不负责：

- 远程代执行 seller 机器上的 join
- 直接充当 buyer 的数据平面
- 直接替代 buyer / seller 本地客户端

## 当前推荐阅读

1. `/root/Pivot_network/PROJECT.md`
2. `/root/Pivot_network/docs/runbooks/current-project-state-and-execution-guide.md`
3. `/root/Pivot_network/项目名词说明.md`
4. `/root/Pivot_network/docs/tutorials/seller-buyer-e2e-guide-cn.md`

## 历史提醒

`Plantform_Backend/docs/` 里的旧阶段说明已经归档。
如果需要看历史设计材料，请到：

- `/root/Pivot_network/Plantform_Backend/docs/archive/legacy-backend-docs-2026-04-12/`

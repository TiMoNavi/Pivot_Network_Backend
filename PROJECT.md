# Pivot Network 当前项目 Brief

更新时间：`2026-04-12`

## 当前结论

当前这轮项目范围已经完整收口，状态应固定理解为：

- seller 接入主线已实现并验证
- backend 商品化主线已实现并验证
- buyer 本地客户端主线已实现并验证
- Windows 本地 buyer 真链路已实现并验证
- 一轮基于真实链路的稳定性测试已完成并通过

当前 repo 已经具备并验证过下面这条真实产品链：

- `Seller_Client -> verified seller node -> listed offer -> order -> access grant -> runtime session -> WireGuard -> shell / workspace / task`

## 当前不是哪种状态

当前已经不再是：

- 只做到 seller bootstrap / 商品化验证的中间态
- 只做到 buyer 规格文档、但正式实现未落地的中间态
- 需要靠旧阶段 runbook 才能理解当前系统状态的时期

当前也还没有定义新的 `Stage8`。

## 已验证能力

### Seller 侧

- 本地 Web 客户端
- 登录 / 注册 seller 账号
- 创建 onboarding session
- 通过 MCP / AI 助手执行接入
- manager 侧基于真实 task 的完成标准
- backend `verified -> assessment -> listed offer`

### Buyer 侧

- 本地 Web / Local API
- active grant 拉取与 attach
- grant code 导入
- same-session `RuntimeSession` create / refresh
- `WireGuard` up / down
- shell 打开
- workspace sync / status
- task submit / logs readback
- Web 自然语言入口驱动 Buyer_Client + MCP

### 稳定性结论

当前真实链路已完成 3 条有界稳定性场景：

1. `same-session` 重编排扰动：
   - 会真实降级
   - 不会自动恢复到可用态
   - 基础设施恢复后，buyer 仍需一次显式 `runtime-sessions/refresh`

2. `runtime service 1 -> 0 -> 1` 的短时中断：
   - 会造成明确的临时不可用
   - 基础设施恢复后，buyer 自动恢复
   - 不需要手工 refresh / retry

3. `gateway -> runtime VIP` 的有界丢包：
   - 是部分退化，不是全挂
   - `runtime/current` 仍可读
   - `workspace/status` 会在 `200 / 502` 之间抖动
   - 抽样 task 仍可能成功
   - 故障解除后自动恢复

## 当前正式入口

### Seller

- 代码目录：`Seller_Client/`
- Windows 启动入口：`Seller_Client/bootstrap/windows/start_seller_client.ps1`

### Buyer

- 代码目录：`Buyer_Client/`
- Windows 启动入口：`Buyer_Client/bootstrap/windows/start_buyer_client.ps1`
- Linux 本地入口：`cd Buyer_Client && python -m uvicorn buyer_client_app.main:app --host 127.0.0.1 --port 8902`

## 当前推荐阅读顺序

如果是第一次进入仓库，当前推荐顺序固定为：

1. `docs/runbooks/current-project-state-and-execution-guide.md`
2. `PROJECT.md`
3. `项目名词说明.md`
4. `docs/tutorials/seller-buyer-e2e-guide-cn.md`
5. `Seller_Client/README.md`
6. `Buyer_Client/README.md`
7. `Seller_Client/docs/current-seller-onboarding-flow-cn.md`
8. `Buyer_Client/docs/current-buyer-purchase-flow-cn.md`
9. `Plantform_Backend/README.md`
10. `Docker_Swarm/Docker_Swarm_Adapter/README.md`

## 当前活跃范围

当前用户新开的工作已经不再是功能实现，而是：

- 项目文件夹整理
- 当前文档更新
- 过时状态文档 / 证据日志归档 / 清理
- 新手可直接照做的 seller / buyer 端到端教程

如果后续还要继续推进，不是默认进入新的阶段，而是需要重新定义新的 scope。

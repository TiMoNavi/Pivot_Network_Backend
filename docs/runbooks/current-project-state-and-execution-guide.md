# Pivot Network 当前项目状态与执行总览

更新时间：`2026-04-12`

## 1. 当前项目一句话结论

当前 seller、platform、buyer 三段真实链路已经全部跑通，Windows 本地 buyer 也已跑通，并且稳定性测试已经完成 3 条真实扰动场景。

当前项目应理解为：

- 真实产品链已完成并验证
- 当前没有新的已定义阶段
- 当前活跃工作是文档整理、教程产出和后续新 scope 定义

## 2. 当前已验证的真实链路

当前已验证主链：

1. 卖家通过 `Seller_Client` 登录并创建 onboarding session
2. 卖家通过 MCP / AI 助手完成受控接入
3. backend 将节点推进到 `verified`
4. backend 自动做 capability assessment 并创建 / 更新真实 `listed offer`
5. 买家创建 order、激活订单、拿到 active grant
6. `Buyer_Client` 绑定 grant、创建 / 刷新 `RuntimeSession`
7. buyer 通过 `WireGuard` 进入 shell
8. buyer 同步工作区、执行任务、查看日志

## 3. 当前 buyer / seller 各自做到哪里

### Seller

当前 seller 已经不是探索态，而是正式入口：

- Web 壳
- 登录 / 注册
- onboarding session
- MCP / AI 助手编排 join
- manager 侧 task 验证
- backend 商品化触发

### Buyer

当前 buyer 也不是“只有规格文档”的状态，而是已经实现并验证：

- Local API / 本地状态
- active grant 拉取与 attach
- grant code 导入
- `RuntimeSession` create / refresh
- `WireGuard` up / down
- shell / workspace / task
- Web 自然语言入口驱动 Buyer_Client + MCP

## 4. 稳定性测试结论

### Scenario 1: same-session 重编排

- 会导致真实降级
- 不会自动恢复到完整可用态
- 基础设施恢复后，buyer 仍需一次显式 `runtime-sessions/refresh`

### Scenario 2: runtime 短时中断

- 会造成明确的临时不可用
- 基础设施恢复后，buyer 自动恢复
- 不需要手工 refresh / retry

### Scenario 3: 网络不稳定

- 属于部分退化，不是全挂
- `runtime/current` 仍可读
- `workspace/status` 会在 `200 / 502` 之间抖动
- 抽样 task 仍可继续成功
- 故障解除后自动恢复

## 5. 当前正式入口

### Seller

- Windows：`Seller_Client/bootstrap/windows/start_seller_client.ps1`
- 文档：`Seller_Client/README.md`

### Buyer

- Windows：`Buyer_Client/bootstrap/windows/start_buyer_client.ps1`
- Linux：`cd Buyer_Client && python -m uvicorn buyer_client_app.main:app --host 127.0.0.1 --port 8902`
- 文档：`Buyer_Client/README.md`

## 6. 当前最推荐的文档入口

1. `docs/tutorials/seller-buyer-e2e-guide-cn.md`
2. `PROJECT.md`
3. `项目名词说明.md`
4. `Seller_Client/README.md`
5. `Buyer_Client/README.md`
6. `Seller_Client/docs/current-seller-onboarding-flow-cn.md`
7. `Buyer_Client/docs/current-buyer-purchase-flow-cn.md`

## 7. 当前文档区怎么理解

- `docs/tutorials/`
  - 给新手直接照着做
- `docs/runbooks/`
  - 只保留当前项目总览与少量协作入口说明
- `docs/runbooks/archive/legacy-cccc-stage-plans-2026-04-12/`
  - 旧阶段作战文档与 handoff
- `docs/runbooks/archive/evidence-logs-2026-04-12/`
  - Stage1-Stage7 的历史证据日志，不再当作当前入口

## 8. 当前没有什么

当前没有现成的 `Stage8`。

如果后续还要继续推进，应重新定义 scope，而不是默认按旧阶段文档继续往下跑。

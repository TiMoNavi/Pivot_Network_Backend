# Phase 4 买家客户端实施规格

更新时间：`2026-04-11`

## 1. 文档定位

这份文档是 `phase4` 的买家客户端实施规格。

它的输入前提不是“从零开始讨论 buyer 是什么”，而是：

- `phase3` 末期 seller 已真实 join
- backend 已能把 `verified` seller 节点商品化成真实 offer
- `Buyer_Client/docs/current-buyer-purchase-flow-cn.md` 已锁定买家主语义

它的输出目标是：

- 明确 `phase4` 买家客户端怎么实现
- 明确 `phase5` 联调闭环前的阶段门槛

## 2. 当前阶段定位

当前整体项目阶段固定为：

- `phase3` 末期
  - seller 真实 join 与平台上架验证
- `phase4`
  - 买家客户端实施
- `phase5`
  - 卖家、平台、买家闭环联调

## 3. 最终成功标准

`phase5` 最终成功标准固定为：

- 买家可以在 Windows 本地启动 `Buyer_Client`
- 买家可以在网页内通过 `CodeX` 自然语言描述任务
- 系统可以建立 buyer `RuntimeSession`
- 买家可以访问 seller runtime 容器的 shell 终端
- 买家可以把任务传递并完成

必须明确：

- 买家消费对象是 `RuntimeSession`
- 买家不是直接拿 seller 裸 IP
- operator 远控 Windows 只用于实施与验证，不替代产品成功标准

## 4. WireGuard 网段纪律

`phase4 / phase5` 必须固定遵守下面这条 WireGuard 纪律：

- manager control-plane 地址继续使用 `10.66.66.1`
- seller 节点继续使用 seller onboarding 真相链确认过的 seller 地址
- buyer runtime lease 不允许复用 manager / seller 地址

当前默认建议 buyer runtime lease 使用独立高位区间：

- `10.66.66.200 - 10.66.66.250`

固定约束：

- seller onboarding truth 只用于 seller 节点验收
- buyer runtime lease 只用于 buyer session 进入 runtime bundle
- 两条 lane 不允许混写

## 5. 分阶段实施策略

## 阶段 1. 卖家真实 join 和上架正常

### 能力边界

- 只验证 seller join、backend 验收、assessment、offer 上架
- 不进入 buyer session

### 成功标准

- seller 真实 join 成功
- backend session 进入 `verified`
- assessment 可售
- `/offers` 能看到真实 `listed` offer

## 阶段 2. 买家注册和下单正常

### 能力边界

- 只做到 buyer 注册、登录、浏览 offer、创建 order、激活订单
- `POST /orders/{id}/activate` 只签发 grant
- 不创建 runtime session

### 成功标准

- buyer 可以看到 seller 真实上架的 offer
- buyer 可以创建 order
- buyer 激活订单后拿到：
  - `grant_id`
  - `grant_code`
  - `expires_at`

## 阶段 3. 买家下发的凭证正常，可以在不做代码的情况下真实接入和使用

### 能力边界

- 允许使用 `curl`、简单脚本、手工 `wg-quick`
- 不要求 Buyer_Client 代码已完成
- 但必须是真实 grant、真实 runtime bundle、真实 WireGuard、真实 shell

### 成功标准

- 用真实 `grant_id` 或 `grant_code`
- 提交 buyer 本地生成的 `wireguard_public_key`
- 成功兑换出 `RuntimeSession`
- 手工拉起 buyer WireGuard
- 真实访问 seller runtime shell
- 至少完成一次最小 task 使用验证

## 阶段 4. 在 Linux 做客户端和 MCP 正常

### 能力边界

- 正式实现 Buyer_Client 本地 API、状态文件、backend client、MCP 工具
- 正式实现 Linux 本地 WireGuard up/down
- 先不要求网页自然语言完整体验
- 先不要求 Windows buyer 端

### 成功标准

- Linux 上 Buyer_Client 可启动
- buyer 可导入或拉取 grant
- 可创建 / 刷新 `RuntimeSession`
- 可打开 seller runtime shell
- MCP 工具可完成：
  - grant 导入
  - session 创建
  - workspace 上传
  - task 提交

## 阶段 5. 在网页内，用自然语言描述端到端测试正常

### 能力边界

- 允许网页内自然语言触发 buyer MCP
- 允许自动完成 grant / session / wireguard / shell / workspace / task
- 仍以 Linux 为首个完整自然语言落点
- 还不把 Windows 远控写成最终产品成功

### 成功标准

- 买家在网页内通过自然语言描述目标
- 系统能自动完成：
  - grant 选择或导入
  - runtime session 建立
  - buyer WireGuard 拉起
  - seller runtime shell 打开
  - workspace 同步
  - task 提交和结果读取

## 阶段 6. 远控 Win，在 Win 那边操作正常

### 能力边界

- 允许通过 `reverse SSH` 或 `win-local-via-wg` 进入 Windows
- 远控只用于 deployment、diagnostics、verification
- 真正的产品链必须仍然是 Windows 本地 Buyer_Client

### 成功标准

- operator 可以远控进入 Windows
- Windows 本地 Buyer_Client 可运行
- Windows 本地可拉起 buyer WireGuard
- Windows 本地可访问 seller runtime shell
- Windows 本地网页中通过 `CodeX` 自然语言描述，可以传递并完成 task

## 6. 实施切片

### Buyer_Client 本地能力

至少实现：

- `auth`
- `catalog`
- `orders`
- `grants`
- `runtime-sessions`
- `wireguard`
- `workspace`
- `tasks`
- `assistant`

### Buyer_Client 本地状态

至少维护：

- `current_order`
- `current_grant`
- `runtime_session`
- `wireguard_state`
- `workspace_selection`
- `task_execution_history`

### Buyer MCP 工具

至少包括：

- `list_active_grants`
- `import_grant_code`
- `create_runtime_session`
- `refresh_runtime_session`
- `wireguard_up`
- `wireguard_down`
- `open_shell`
- `sync_workspace`
- `submit_task_execution`
- `tail_task_logs`
- `list_artifacts`
- `download_artifact`
- `stop_runtime_session`

### Backend 必要配套

至少包括：

- `POST /orders/{id}/activate`
  - 只签发 grant
- `GET /me/access-grants/active`
- `POST /access-grants/redeem`
- `POST /access-grants/redeem-by-code`
- `GET /runtime-sessions/{id}`
- `POST /runtime-sessions/{id}/heartbeat`
- `POST /runtime-sessions/{id}/stop`
- `POST /runtime-sessions/{id}/close`

### Adapter / Runtime 必要配套

至少包括：

- runtime bundle create / inspect / remove
- buyer WireGuard peer apply / remove / inspect
- shell URL
- workspace upload / extract / status
- task submit / status / logs / artifacts

## 7. 验收顺序

`phase4` 的正式验收顺序固定为：

1. seller 真实 join 与上架
2. buyer 注册与下单
3. grant 手工可用
4. Linux buyer client + MCP
5. Linux 网页自然语言端到端
6. Windows 远控验证与 Win 本地自然语言端到端

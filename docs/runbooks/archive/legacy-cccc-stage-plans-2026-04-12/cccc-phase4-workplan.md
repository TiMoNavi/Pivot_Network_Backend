# CCCC Phase 4 / Phase 5 Workplan

更新时间：`2026-04-11`

这份文档把当前 `phase4` 与 `phase5` 固定成 6 个阶段。

每个阶段都必须写清：

- 能力边界
- 成功标准

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

## 阶段 3. 买家凭证正常，可以在不做客户端代码的情况下真实接入和使用

### 能力边界

- 允许使用 `curl`、简单脚本、手工 `wg-quick`
- 不要求 Buyer_Client 代码已完成
- 但必须是真实 grant、真实 runtime bundle、真实 shell

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

## 统一硬约束

- `phase4` 从 seller 真实 join 和真实上架之后开始
- 不把 SSH/operator reachability 写成产品成功
- 不把 buyer 退回成 seller target / seller IP 模型
- 不让 buyer client 绕过 backend 直接建 runtime bundle
- buyer WireGuard lease 必须和 seller / manager 地址分 lane

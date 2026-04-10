# Pivot Seller Client

当前请先读：

- `docs/current-seller-onboarding-flow-cn.md`
  - 当前卖家接入主线
  - 当前权威地址、MCP 执行面、完成标准
- `docs/phase1-bootstrap-contract.md`
  - 安装 / bootstrap contract
- `docs/seller-overlay-connectivity-architecture-cn.md`
  - Overlay / WireGuard 架构说明

Windows 卖家本地客户端当前正式入口收束成：

- `bootstrap/windows/install_and_check_seller_client.ps1`
  - 安装 / 环境检查 / 半自动修复入口
- `bootstrap/windows/start_seller_client.ps1`
  - 本地 Web 客户端启动入口

应用主线位于 `seller_client_app/`：

- `main.py`
  - 本地 FastAPI Web 壳
- `local_system.py`
  - 环境检查、半自动修复、诊断包导出、标准 Windows workflow 调用
- `mcp_server.py`
  - session-scoped MCP server
- `backend.py`
  - 本地客户端到后端的统一 API 边界

当前公开工作区固定为 5 个：

- `环境`
- `网络 / WireGuard`
- `Docker / Swarm`
- `接入会话`
- `AI 助手`

当前自然语言接入默认走 MCP 编排，而不是旧的本地执行 workflow。

当前卖家接入的最终成功标准是：

- manager 侧看到 worker `Ready`
- manager 侧确认该 worker 上存在可执行或运行中的 task

当前 seller 侧在项目节奏里应理解为：

- 已处于 `phase3` 末期
- 当前 seller 相关工作的重点不再是扩展新的接入语义
- 而是验证 seller 节点在 backend 侧通过验收后，能够稳定触发平台上架逻辑

当前 repo 代码里，卖家节点一旦在 backend 侧进入 `verified`，backend 还会继续做两件后置动作：

- 对该节点做 capability assessment
- 在 assessment 可售时按 `compute_node_id` 自动生成或更新真实 offer

也就是说，seller client 当前负责的是：

- 帮卖家把节点稳定接入并交给 backend 验收

而不是：

- 直接操作商品化规则或 buyer runtime 会话

历史排障脚本不会继续作为正式入口使用。需要保留的旧脚本会归档到 `bootstrap/windows/legacy/`，实验性内部 runner 只作为受控实现细节保留。

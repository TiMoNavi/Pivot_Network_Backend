# Seller Windows Host App

这个目录描述 seller v2 中 `Windows Host` 的正式职责。

负责：

- 本地网页控制台
- PowerShell 启动入口
- seller 登录与会话操作
- Windows host 安装与检查
- 文件选择
- 日志展示
- Codex / MCP 宿主
- 调用 WSL Ubuntu bootstrap / sync / join / claim / report

不负责：

- 作为正式 seller compute node
- 直接运行 runtime 容器
- 直接以 Windows Docker 执行 `build / join / push`

当前实际 Python 代码仍主要位于 `seller_client_app/`。
这是当前仓库的过渡状态，不代表 Windows 重新成为正式 compute substrate。

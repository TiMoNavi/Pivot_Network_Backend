# 买家云主机会话当前实现与架构说明

更新时间：`2026-04-12`

## 1. 文档定位

这份文档同时承担两件事：

- 解释当前 buyer 链路的架构语义
- 说明当前已经实现并验证到哪里

它不再是“只定文档、不做代码”的纯规格文档。

如果你是第一次使用系统，先读：

- `/root/Pivot_network/docs/tutorials/seller-buyer-e2e-guide-cn.md`

如果你要看历史 `phase4` 实施规格，请去归档目录：

- `Buyer_Client/docs/archive/legacy-stage-docs-2026-04-12/phase4-buyer-client-implementation-spec-cn.md`

## 2. 核心结论

当前买家链路已经按下面这些结论实现并验证：

- 用户产品语义：`云主机会话`
- 内部基础设施语义：`RuntimeSession = runtime bundle`
- 正式连接方式：`WireGuard 优先`
- 正式 shell 入口：`仅本地 buyer client`
- Web 自然语言入口会驱动同一条 `Buyer_Client + MCP + runtime bundle` 链

当前已完成的真实验证包括：

- Linux 本地 buyer + MCP + 自然语言链路
- Windows 本地 buyer 完整接入链路
- 三条 bounded 稳定性场景

## 3. 当前已验证的 buyer 完整链路

下面这条 buyer 主线当前已经真实跑通：

1. buyer 登录
2. 拉取 active grants
3. attach active grant 或导入 grant code
4. create / refresh `RuntimeSession`
5. `WireGuard` up
6. 打开 shell
7. 同步 workspace
8. 提交 task
9. 回读日志与结果

## 4. 当前 buyer 侧能力边界

当前 buyer 负责：

- 本地窗口会话
- 本地状态文件
- backend client
- MCP 工具面
- 本地 `WireGuard` keypair 与 tunnel 管理
- shell / workspace / task 使用
- Web 自然语言驱动

当前 buyer 不负责：

- 绕过 backend 直接改基础设施业务状态
- 直接操作订单数据库
- 直接执行 seller 侧 Docker / Swarm 管理命令

## 5. 仍然建议阅读这份文档的场景

如果你要看：

- 为什么 buyer 消费对象是 `RuntimeSession`
- 为什么 seller 不是 buyer 的裸 IP
- 为什么 `TaskExecution` 只是会话内能力而不是主对象
- buyer / backend / adapter / wireguard 的职责分层

那么继续读本文件的后续章节即可。

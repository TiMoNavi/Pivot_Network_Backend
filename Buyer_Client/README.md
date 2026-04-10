# Buyer Client

当前 `Buyer_Client` 是面向 Pivot Network 买家侧的本地客户端目录。

当前以文档定稿为准，先不继续扩买家端实现代码。

当前推荐的正式方向是：

- 登录 buyer 账号
- 浏览 `offers`
- 创建 `order`
- 激活订单并获取绑定账号的 `AccessGrant / grant_code`
- 在本地 buyer client 中兑换并创建 `RuntimeSession`
- 通过 `WireGuard` 进入正式 shell
- 在当前会话里上传项目目录、执行任务、查看日志与下载产物

详细流程见：

- [docs/current-buyer-purchase-flow-cn.md](/root/Pivot_network/Buyer_Client/docs/current-buyer-purchase-flow-cn.md)

当前 `phase4` 的实施规格见：

- [docs/phase4-buyer-client-implementation-spec-cn.md](/root/Pivot_network/Buyer_Client/docs/phase4-buyer-client-implementation-spec-cn.md)

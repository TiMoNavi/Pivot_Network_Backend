# Platform UI

最小平台前端静态页面，目录放在 `frontend/`，由后端直接挂载：

- 路径：`/platform-ui`

当前提供：

- 注册
- 登录
- 钱包余额查看
- 容器商品列表
- 容器商品详情
- 下单签发许可证
- 订单列表
- 许可证查询

页面不直接启动 buyer runtime。
它的下单行为只会向后端创建 `BuyerOrder` 并拿到 `license_token`，后续由本地客户端拿这个 token 去做实际运行。

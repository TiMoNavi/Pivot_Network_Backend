# 当前卖家流程说明

更新时间：`2026-04-12`

## 1. 当前主线结论

当前 Windows `seller_client` 的正式接入主线已经固定为：

1. 卖家在本地启动 Web 客户端
2. 卖家登录或注册 backend 账号
3. 创建 fresh onboarding session
4. 由网页自然语言入口或 MCP 工具执行接入
5. 以 manager 侧真实 task 可执行作为完成标准

现在不再把“本地 `docker info` 显示 `LocalNodeState=active`”当成最终成功标准。

当前最终成功标准只有一个：

- manager 侧可以确认这台 worker 处于 `Ready`
- manager 侧可以确认这台 worker 上存在可运行或已运行中的 swarm task

当 backend 侧 session 进入 `verified` 后，backend 现在还会继续：

- 对该节点做 capability assessment
- 在 assessment 可售时按 `compute_node_id` 自动创建或更新真实 offer
- 在 assessment 不可售时自动下架已有 listing

因此当前 seller 侧在整体项目节奏中，应理解为：

- seller onboarding 主线已经通过
- 平台商品化主线已经通过
- seller -> buyer 端到端闭环已经通过
- 当前 seller 相关工作的重点不再是补主功能，而是配合稳定性 / 运维性验证

## 2. 当前权威地址与边界

当前 seller client 应按下面这组权威事实工作：

- backend 公网入口：`https://pivotcompute.store`
- swarm manager 公网地址：`81.70.52.75`
- swarm manager WireGuard 地址：`10.66.66.1`
- 当前权威 join target：`10.66.66.1:2377`
- seller client 与 adapter 的边界：`seller client -> backend -> adapter`

seller client 不应直连 adapter，也不应再把 `81.70.52.75:2377` 当成 swarm join target。

## 3. 当前正式入口

当前 Windows 正式入口只有两类：

- 安装 / 检查：`bootstrap/windows/install_and_check_seller_client.ps1`
- 启动本地 Web：`bootstrap/windows/start_seller_client.ps1`

当前新手教程入口：

- `/root/Pivot_network/docs/tutorials/seller-buyer-e2e-guide-cn.md`

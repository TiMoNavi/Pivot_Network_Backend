# 当前卖家流程说明

更新时间：`2026-04-11`

## 1. 当前主线结论

当前 Windows `seller_client` 的正式接入主线已经固定为：

1. 卖家在本地启动 Web 客户端。
2. 卖家登录或注册 backend 账号。
3. 创建 fresh onboarding session。
4. 由网页自然语言入口或 MCP 工具执行接入。
5. 以 manager 侧真实 task 可执行作为完成标准。

现在不再把“本地 `docker info` 显示 `LocalNodeState=active`”当成最终成功标准。

当前最终成功标准只有一个：

- manager 侧可以确认这台 worker 处于 `Ready`
- manager 侧可以确认这台 worker 上存在可运行或已运行中的 swarm task

但当前 repo 代码里，seller onboarding 的平台效果已经不再止于“接入成功”。

当 backend 侧 session 进入 `verified` 后，backend 现在还会继续：

- 对该节点做 capability assessment
- 在 assessment 可售时按 `compute_node_id` 自动创建或更新真实 offer
- 在 assessment 不可售时自动下架已有 listing

因此当前 seller 侧在整体项目节奏中，应理解为：

- 已处于 `phase3` 末期
- 当前重点是验证平台上架逻辑是否稳定
- 后续重点会转向 `phase4` 买家客户端设计与 `phase5` 端到端闭环联调

## 2. 当前权威地址与边界

当前 seller client 应按下面这组权威事实工作：

- backend 公网入口：
  - `https://pivotcompute.store`
- swarm manager 公网地址：
  - `81.70.52.75`
  - 仅用于 SSH / 外网访问语境
- swarm manager WireGuard 地址：
  - `10.66.66.1`
- 当前权威 join target：
  - `10.66.66.1:2377`
- seller client 与 adapter 的边界：
  - `seller client -> backend -> adapter`

seller client 不应直连 adapter，也不应再把 `81.70.52.75:2377` 当成 swarm join target。

## 3. 当前正式入口

当前 Windows 正式入口只有两类：

- 安装 / 检查：
  - `bootstrap/windows/install_and_check_seller_client.ps1`
- 启动本地 Web：
  - `bootstrap/windows/start_seller_client.ps1`

应用主线固定在 `seller_client_app/`：

- 本地 Web 壳：
  - `seller_client_app/main.py`
- 本地脚本能力包装层：
  - `seller_client_app/local_system.py`
- MCP 执行面：
  - `seller_client_app/mcp_server.py`
  - `seller_client_app/mcp_fastmcp.py`
- 自然语言助手路由：
  - `seller_client_app/assistant_runtime.py`

## 4. 当前自然语言接入方式

网页里的自然语言接入请求现在默认走 MCP 编排，不再走旧的本地执行 workflow。

卖家或 AI 可以直接说：

- `帮我接入`
- `帮我加入 swarm`
- `Help me join swarm and verify manager-side task execution.`

当前 join 类自然语言请求会优先触发 MCP 工具链，典型顺序是：

1. `list_script_capabilities`
2. `refresh_onboarding_session`
3. `read_join_material`
4. `prepare_machine_wireguard`
5. `execute_guided_join`
6. `verify_manager_task`

如果 backend token 已过期，但本地已有有效 session 证据，流程会退化成：

- 基于现有 session 读取 join material
- 检查本地 WireGuard / swarm 连通性
- 直接从 manager 侧验证 task 执行

也就是说，接入验证的最后一跳始终是 manager 真相层，而不是本地自报。

## 5. 当前机器前提

每台卖家机器都必须提供自己的 WireGuard 配置。

当前支持的正式位置是：

- 标准缓存路径：
  - `.cache/seller-zero-flow/wireguard/wg-seller.conf`
- 或环境变量：
  - `SELLER_CLIENT_WG_CONFIG_PATH`

当前脚本不会再默认复用别的机器遗留的 legacy 私钥或旧 `wg-seller.conf`。

如果这份机器专属 WireGuard 配置不存在，当前流程应当明确报：

- `missing_machine_wireguard_config`

而不是继续假装可以 join。

## 6. 当前标准卖家流程

### 6.1 从零开始

1. 运行 `install_and_check_seller_client.ps1`
2. 运行 `start_seller_client.ps1`
3. 打开本地网页
4. 登录或注册卖家账号
5. 创建 fresh onboarding session
6. 直接在 AI 助手里说“帮我接入”
7. 等待 MCP 完成：
   - WireGuard 配置准备
   - 环境检查
   - join material 读取
   - guided join
   - manager task execution 验证

### 6.3 接入完成后的平台效果

在当前 repo 代码里，如果 backend 最终把 session 写成 `verified`，平台后续会自动进入：

1. capability assessment
2. offer commercialization

因此当前 seller 流程的完整平台语义应理解为：

- seller client 负责把节点接到 backend 真相链
- backend 负责把已验收节点商品化

seller client 本身不直接调用 assessment 接口，也不直接管理 offer。

### 6.2 失败后重试

如果需要从零重来，当前正式清理入口是：

- `cleanup_join_state`
- `stop_local_service_and_cleanup`

推荐顺序：

1. 清理本地 join 状态
2. 不复用旧 onboarding session
3. 创建 fresh session
4. 再执行自然语言接入

## 7. 当前 MCP 能力命名

当前 AI-facing 的规范能力名已经收束为：

- `inspect_environment_health`
- `repair_environment_health`
- `inspect_overlay_runtime`
- `inspect_network_path`
- `prepare_machine_wireguard`
- `execute_join_workflow`
- `execute_guided_join`
- `verify_manager_task`
- `verify_local_service_content`
- `cleanup_join_state`
- `stop_local_service_and_cleanup`

如果需要先发现当前受支持能力，可先调用：

- `list_script_capabilities`

## 8. 当前推荐阅读顺序

当前活动文档建议按这个顺序读：

1. 本文 `current-seller-onboarding-flow-cn.md`
2. `phase1-bootstrap-contract.md`
3. `seller-overlay-connectivity-architecture-cn.md`

旧的 2026-04-09 handoff / 分析 / 状态追踪文档已经降级到 `docs/archive/`，不再作为当前卖家流程入口。

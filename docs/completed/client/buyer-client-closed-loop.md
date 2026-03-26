# 买家客户端完成态

## 结论

截至 `2026-03-26`，买家客户端已经完成第一阶段闭环：

- 指定 seller 节点
- 创建临时 runtime session
- 上传代码或项目到 seller Docker 容器执行
- 获取执行结果
- 创建 shell 型会话并在容器内 `exec`
- 为租期内 session 下发 buyer 专属 WireGuard 凭证
- 本地拉起 `wg-buyer`
- 通过 WireGuard 直接打到 seller 节点

## 这条线最终做成了什么

买家本地现在具备：

- buyer CLI
- buyer 本地网页控制面
- 代码执行 session
- shell session
- 目录 / zip 上传
- GitHub 仓库下载后执行
- session 续期
- `wg-buyer` bootstrap / disconnect

对应关键文件：

- `buyer_client/agent_cli.py`
- `buyer_client/agent_server.py`
- `buyer_client/web/index.html`
- `buyer_client/README.md`
- `buyer_client/terminal-design.md`

## 从开始制作以来做过的主要修改

### 1. buyer CLI

`buyer_client/agent_cli.py` 先从最小 `run-code` 做起，后续补成以下命令面：

- `run-code`
- `run-archive`
- `run-github`
- `start-shell`
- `exec`
- `stop`
- `renew`
- `wireguard-bootstrap`
- `wireguard-disconnect`

这意味着买家不再只是“一次性提交一段代码”，而是已经有 session、租期和网络凭证这套概念。

### 2. buyer 本地网页

`buyer_client/agent_server.py` 和 `buyer_client/web/index.html` 补成了本地 buyer 控制面。

页面职责明确限制为：

- 只与本地 buyer 进程通信
- 再由本地 buyer 进程与平台后端交换必要数据
- 页面本身不直接碰 Docker、WireGuard、seller 节点或远端主机

页面当前支持：

- 单文件代码执行
- 本地目录 / zip 执行
- GitHub 仓库执行
- shell session 创建
- 当前 session 容器内 `exec`
- lease renew
- 当前 session 的 `wg-buyer` bootstrap
- 当前 session 的 `wg-buyer` disconnect

### 3. 运行模型从“任务型”演进到“租期型”

最初 buyer 路线偏任务型。
后续明确切换为“租一个 runtime session 一段时间”：

- session 有 `expires_at`
- 可续期
- 到期自动回收
- 租期内允许持续 shell / exec / 上传代码 / 跑命令 / 看日志

### 4. buyer WireGuard

这部分是后来补上的关键增量。

buyer 现在不是只靠 relay/polling 间接使用 seller。
对于租期内 session，平台可下发 buyer 专属 WireGuard 凭证，buyer 本地拉起 `wg-buyer` 后，直接进入 `wg0` 这套平台内网。

## 真实验证过什么

### 1. buyer 最小代码执行闭环

已真实跑通过：

- buyer 提交 Python 代码
- seller 节点容器执行
- 结果回传
- buyer 本地网页看到输出

真实输出示例：

```text
hello from buyer runtime
42
```

### 2. shell / exec

已真实跑通过：

- 创建 shell session
- 定位到 seller 上的 runtime 容器
- 执行 `python -V`

真实输出示例：

```text
Python 3.12.13
```

### 3. archive / GitHub

已补齐并真实验证 session 能创建和完成：

- 本地目录 / zip 路线
- GitHub 仓库下载后运行路线

### 4. buyer WireGuard 直连 seller

已完成真实验证，而且验证的是正确的 `wg0` 这套网段，不是服务器上另外几套 WireGuard。

真实验证链路：

- fresh backend `8015`
- fresh seller 注册到该 backend
- seller 已在 `wg0` 中拥有 `10.66.66.10/32`
- buyer 创建 shell lease
- buyer 获得 `10.66.66.138/32`
- 本地拉起 `wg-buyer`
- `ping 10.66.66.1` 成功
- `Test-NetConnection 10.66.66.10 -Port 22` 成功

关键结果是：

- `InterfaceAlias = wg-buyer`
- `SourceAddress = 10.66.66.138`
- `TcpTestSucceeded = True`

这说明 buyer 已经通过 `wg-buyer -> wg0 -> seller` 直连 seller。

## 当前边界

买家客户端当前完成的是第一阶段闭环，不是最终开发环境产品。

还没做完的内容：

- 真正交互式网页终端
- 端口转发
- 文件下载回传
- IDE 级长连接体验
- 私有 GitHub 仓库认证
- GPU runtime 使用入口

## 当前推荐理解

买家客户端当前不是“拿到 seller 宿主机 SSH”，而是：

- 拿到一个受平台约束的 runtime session
- 必要时进入该 session 对应的容器
- 必要时在租期内加入平台 WireGuard 内网

这条边界已经比较接近后续可产品化的方向。

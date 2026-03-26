# Buyer Web Terminal 设计说明

## 当前状态

当前 `buyer` 本地网页已经支持：

- 单文件代码执行
- 本地目录 / zip 执行
- GitHub 仓库执行
- shell session 创建
- 当前 session 容器内单次 `exec`

这意味着现在已经有：

- buyer 本地网页
- buyer 本地进程
- seller 节点上的 runtime session
- 本地 buyer 进程到容器的命令代理

但当前还没有的是：

- 真正交互式网页终端

## 什么叫“真正交互式网页终端”

这里说的不是：

- 一个输入框执行一次命令
- 返回 stdout / stderr

而是：

- 网页里有一个持续存在的终端面板
- 用户可以连续输入命令
- 能看到实时输出
- 支持窗口尺寸变化
- 未来能兼容更复杂的 TUI 程序

也就是更接近：

- VS Code terminal
- 浏览器里的 xterm

## 为什么当前没有直接做它

当前已经做出来的是：

- shell session
- 单次 `exec`

这是为了先把最小 buyer 闭环跑通。

真正交互式终端比单次 `exec` 多出一整层终端系统问题：

- TTY / PTY 分配
- 输入输出流持续桥接
- WebSocket
- 重连
- 会话生命周期
- shell 进程回收

所以它不是一个简单表单功能，而是一个独立能力。

## 是否能做

可以做。

而且不是从零造轮子，现成组件很多。

## 现成方案

### 前端

推荐：

- `xterm.js`
- `xterm-addon-fit`
- `xterm-addon-web-links`

这是浏览器终端的常见组合。

### 本地 buyer 进程

推荐：

- `WebSocket`
- 真正的 shell/pty 进程桥接

Windows 上的现实选择通常是：

- `ConPTY`
- 或 `pywinpty`

### 容器侧

当前最小方案可以继续利用：

- `docker exec`

但从“单次命令”升级为：

- 持续交互式 shell

## 当前推荐的第一阶段实现

第一阶段不建议先做 seller 远端的复杂 relay 终端。

更稳的路径是：

- 先做 **buyer 本地网页 -> buyer 本地进程 -> 本地 runtime 容器 shell**

也就是：

1. 在 buyer 网页内嵌 `xterm.js`
2. buyer 本地进程新增 `WebSocket /api/terminal/{local_id}`
3. buyer 本地进程为当前 session 创建一个交互式 shell 进程
4. buyer 本地进程把终端输入输出桥接到网页

这里的“shell 进程”第一阶段可以是：

- 本地调用 `docker exec -it <container> sh`

## 为什么这个方案最适合当前阶段

因为当前 buyer/seller 验证仍然是在：

- 当前本机 buyer 本地网页
- 当前本机 seller worker 容器

这意味着当前 buyer 本地进程可以直接看到 runtime 容器。

所以本阶段最小终端不需要先引入：

- seller 远端 session gateway
- 双向 relay
- 复杂终端代理网络层

## 第二阶段再演进什么

如果以后 buyer 和 seller 真正物理分离，当前本地 `docker exec` 路线就不够了。

那时应升级到：

- seller 节点侧 `session gateway`
- buyer 本地网页 <-> buyer 本地进程 <-> 后端/relay <-> session gateway <-> runtime container

也就是说：

- 第一阶段：本地 buyer terminal
- 第二阶段：远程 relay terminal

## 为什么不建议第一阶段直接上“标准 SSHD 终端”

前面已经讨论过，原因包括：

- 多一套攻击面
- 多一套认证面
- 多一套长期服务
- 容器镜像被污染
- 会话控制更难

所以即使以后要做 VS Code 风格体验，优先级也应是：

- 先做 PTY / shell gateway

而不是：

- 先做 `sshd + 密码`

## 真终端实现时要处理的几个点

### 1. 生命周期

要定义：

- shell session 何时创建
- 网页关闭后 shell 是否保留
- session stop 时 shell 如何回收

### 2. 终端尺寸

需要支持：

- rows / cols resize

否则网页终端体验很差。

### 3. 输出缓冲

需要支持：

- 连续输出
- 大输出裁剪
- 最近 N KB 缓存

### 4. 安全边界

必须保证：

- 只连当前 buyer 的 runtime container
- 不能跨 session
- 不能落到 seller 宿主机

## 当前建议顺序

如果下一步开始做，建议按这个顺序：

1. `xterm.js` 页面壳子
2. buyer 本地 `WebSocket` 终端桥接
3. 本地 `docker exec -it` 持续 shell
4. resize
5. 断线重连策略

## 一句话结论

真正交互式网页终端：

- **能做**
- **有现成前端组件**
- **当前阶段最合适的路线是 buyer 本地 Web + WebSocket + 本地 runtime 容器 shell**

而不是一开始就做：

- seller 远程 SSH
- seller 宿主机 shell
- 标准 SSHD 暴露

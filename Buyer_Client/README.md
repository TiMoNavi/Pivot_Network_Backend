# Buyer Client

当前 `Buyer_Client/` 是买家本地客户端的**正式入口目录**。

如果你是第一次接触项目，建议先读：

1. `/root/Pivot_network/docs/tutorials/seller-buyer-e2e-guide-cn.md`
2. `/root/Pivot_network/Buyer_Client/docs/current-buyer-purchase-flow-cn.md`

这份 README 只解决一件事：

- 新人如果要复现 buyer 客户端，应该先跑什么、再跑什么、什么算成功

## 1. 买家端当前正式入口

### Linux

启动命令：

```bash
cd /root/Pivot_network/Buyer_Client
python -m uvicorn buyer_client_app.main:app --host 127.0.0.1 --port 8902
```

### Windows

启动命令：

```powershell
powershell -ExecutionPolicy Bypass -File ".\bootstrap\windows\start_buyer_client.ps1"
```

默认本地页面地址：

- `http://127.0.0.1:8902/`

## 2. buyer 端和 seller 端的区别

seller 端有比较明确的“环境检查脚本 / 网络检查脚本”。

buyer 端当前**没有单独独立出来的环境检查脚本**。
它的检查逻辑是集成在主链里的：

- 能不能登录
- 能不能拉到 active grant
- 能不能 create / refresh `RuntimeSession`
- 能不能 `WireGuard` up
- 能不能打开 shell
- 能不能 sync workspace / submit task

所以对 buyer 来说，真正的“检查”方式就是把主链走一遍。

## 3. 新人最短操作顺序

### 第一步：启动 buyer 页面

按你的操作系统运行上面的启动命令。

如果浏览器没自动弹出，就手工打开：

- `http://127.0.0.1:8902/`

### 第二步：登录 buyer

在“登录与当前链路”区域：

- 输入 buyer 的 email / password
- 点击 `登录 Buyer`

### 第三步：拉取并绑定当前 grant

按顺序点击：

1. `拉取 Active Grants`
2. `绑定首个 Active Grant`

如果你手里只有 `grant_code`，也可以：

1. 把 `grant_code` 填到 `Grant Code` 输入框
2. 点击 `导入 Grant Code`

### 第四步：创建 / 刷新 RuntimeSession

有两种走法：

#### 推荐走法：自然语言

在“自然语言驱动”区域输入：

```text
使用当前 active grant 建立 runtime session，拉起 WireGuard，打开 shell，同步当前工作区，执行 `pwd` 并返回结果。
```

然后点击：

- `执行自然语言流程`

#### 手动走法

按顺序点击：

1. `手动创建 / 刷新 Session`
2. `手动拉起 WireGuard`
3. `手动打开 Shell`
4. `手动同步工作区`

## 4. 工作区和任务怎么用

### 4.1 先保存工作区路径

在 `Workspace 路径` 输入框里填本地目录，例如：

- Linux：`/root/Pivot_network`
- Windows：`D:\AI\Pivot_Client\buyer_client`

然后点击：

- `保存工作区路径`

### 4.2 同步工作区

点击：

- `手动同步工作区`

### 4.3 执行任务

推荐通过自然语言让它执行。

如果你只是做最小验证，最常见的成功命令是：

```text
echo test-ok && pwd && ls -1
```

## 5. buyer 端成功标准怎么判断

### 5.1 会话建立成功

至少要看到：

- `create / refresh` 返回同一条真实 `runtime_session_id`
- `runtime_session.status = ready`
- `runtime_bundle_status = running`

### 5.2 数据面成功

至少要看到：

- `wireguard_up` 成功
- `/health` 可读
- shell URL 可打开

### 5.3 使用面成功

至少要看到：

- `workspace/status = 200`
- `/workspace` 下能看到同步后的文件
- task 返回 `exit_code = 0`
- 日志回读与任务输出一致

## 6. 当前已经真实验证过什么

当前 buyer 侧已经真实通过：

- Linux 本地 buyer 链路
- Windows 本地 buyer 链路
- Web 自然语言链路（Linux 路径）
- 三条稳定性场景：
  1. same-session 重编排
  2. runtime 短时中断
  3. 网络不稳定下的部分退化

## 7. 常见问题

### 7.1 buyer 能像 SSH 一样操作“买到的服务器”吗

可以，但准确说法是：

- 用户是在浏览器里像用远程终端一样操作
- 但操作对象是 `RuntimeSession` 的 shell
- 不是直接 SSH 到 seller 宿主机

### 7.2 如果想看带截图版本

请直接看：

- `/root/Pivot_network/docs/tutorials/seller-buyer-e2e-guide-cn.md`

### 7.3 如果想看 buyer 当前详细语义

请看：

- `/root/Pivot_network/Buyer_Client/docs/current-buyer-purchase-flow-cn.md`

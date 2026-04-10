# Windows 电脑ssh 说明

更新时间：2026-04-08

## 用途边界

这份说明只定义 Windows 主机的 operator 运维入口，用于 deployment、diagnostics、verification。

- 当前 operator 入口优先使用 **反向 SSH**。这种方式是 Windows 主动连到服务器，比单独依赖 WireGuard 更稳定。
- `SSH / reverse SSH / WireGuard` 可达，不等于 `Phase 2B` 成功。
- 不能用服务器上的 SSH 会话去冒充 seller 产品链路；`docker swarm join`、correction 和最小 TCP validation 仍应由 Windows 主机本地 runtime 按正式流程执行并留证。
- 当前正式成功标准仍固定为：
  1. backend 看见真实 `join`
  2. `runtime / Docker_Swarm` 完成 correction 并留证
  3. backend 复验后 `manager_acceptance = matched`
  4. 纠正后的目标地址对卖家容器最小 TCP 回连成功

## 服务器怎么连 Windows

当前 operator 首选命令：

```bash
ssh win-local-via-reverse-ssh
```

等价命令：

```bash
ssh -p 22220 -i /root/.ssh/id_ed25519_windows_local 550w@127.0.0.1
```

服务器上也保留了两个辅助脚本：

```bash
/root/Pivot_network/connect_windows_reverse_ssh.sh
/root/Pivot_network/check_windows_reverse_ssh.sh
```

## 当前已验证状态

- 服务器 `127.0.0.1:22220` 监听正常
- `ssh win-local-via-reverse-ssh whoami` 返回 `550w\550w`
- 登录后默认目录是 `C:\Users\Administrator`
- 建议的工作区是 `D:\AI\Pivot_Client`

## 连上之后在哪个文件夹操作

连上后先执行：

```cmd
cd /d D:\AI\Pivot_Client
```

如果是 PowerShell：

```powershell
Set-Location 'D:\AI\Pivot_Client'
```

## 相关路径

Windows 主工作区：

```text
D:\AI\Pivot_Client
```

当前脚本与仓库目录：

```text
D:\AI\Pivot_backend_build_team
```

反向 SSH 运行脚本：

```text
D:\AI\Pivot_backend_build_team\scripts\run_reverse_ssh_tunnel.ps1
```

反向 SSH 安装脚本：

```text
D:\AI\Pivot_backend_build_team\scripts\install_reverse_ssh_tunnel_task.ps1
```

反向 SSH 日志：

```text
D:\AI\Pivot_Client\logs\reverse-ssh-tunnel.log
```

## 保活方式

- 本地已有正在运行的反向 SSH 进程
- 当前用户登录时会通过 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\PivotClientReverseSSHTunnel` 自动拉起
- 如果需要 Windows 重启后、用户未登录也能尽快恢复入口，在本机管理员 PowerShell 里执行：

```powershell
powershell -ExecutionPolicy Bypass -File "D:\AI\Pivot_backend_build_team\scripts\install_reverse_ssh_tunnel_task.ps1"
```

## WireGuard 备用入口

WireGuard 链路恢复后可以尝试：

```bash
ssh win-local-via-wg
```

但如果你的目标只是 operator access，仍然优先使用：

```bash
ssh win-local-via-reverse-ssh
```

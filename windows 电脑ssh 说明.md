# Windows 电脑ssh 说明

更新时间：2026-04-11

当前推荐入口是 **反向 SSH**。这台 Windows 主动连服务器，服务器再通过本机回环端口回连 Windows，通常比单独依赖 WireGuard 更稳定。

## 当前状态

2026-04-11 已现场验证：

- Windows 本机 `sshd` 是 `Running`
- Windows 本机 `22` 端口在监听
- 服务器本机 `127.0.0.1:22220` 在监听
- 服务器执行 `ssh win-local-via-reverse-ssh whoami` 返回 `550w\550w`
- 服务器验证工作区返回 `D:\AI\Pivot_Client`

## 服务器怎么连 Windows

首选命令：

```bash
ssh win-local-via-reverse-ssh
```

等价命令：

```bash
ssh -p 22220 -i /root/.ssh/id_ed25519_windows_local 550w@127.0.0.1
```

服务器上的辅助脚本：

```bash
/root/Pivot_network/connect_windows_reverse_ssh.sh
/root/Pivot_network/check_windows_reverse_ssh.sh
```

## 连上之后在哪个文件夹操作

建议先进入工作区：

```cmd
cd /d D:\AI\Pivot_Client
```

如果进入的是 PowerShell：

```powershell
Set-Location 'D:\AI\Pivot_Client'
```

## Windows 侧启动 SSH 的命令

管理员 PowerShell：

```powershell
Set-Service -Name sshd -StartupType Automatic
Start-Service sshd
Get-Service sshd
Get-NetTCPConnection -LocalPort 22 -State Listen
```

如果机器还没安装 OpenSSH Server，可以先执行：

```powershell
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
```

## Windows 侧启动反向 SSH 隧道的命令

临时启动一条反向隧道：

```powershell
powershell -ExecutionPolicy Bypass -File "D:\AI\Pivot_backend_build_team\scripts\run_reverse_ssh_tunnel.ps1"
```

安装登录/开机保活：

```powershell
powershell -ExecutionPolicy Bypass -File "D:\AI\Pivot_backend_build_team\scripts\install_reverse_ssh_tunnel_task.ps1"
```

当前用户登录兜底自启动项：

```text
HKCU\Software\Microsoft\Windows\CurrentVersion\Run\PivotClientReverseSSHTunnel
```

## 服务器侧日常检查

检查服务器回环端口：

```bash
ss -lnt '( sport = :22220 )'
```

检查是否能回连 Windows：

```bash
ssh win-local-via-reverse-ssh whoami
```

检查工作区路径：

```bash
ssh win-local-via-reverse-ssh 'cmd /c "cd /d D:\AI\Pivot_Client && cd"'
```

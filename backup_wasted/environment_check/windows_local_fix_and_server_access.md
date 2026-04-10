# Windows 本地修复与服务器访问信息说明

更新时间：`2026-04-06`

## 1. 这份说明是干什么的

这份文档给 Windows 侧人工修复时使用，目标是：

- 说明为什么当前 `windows_seller_host_install_and_check.ps1` 需要优先在 Windows 本地运行
- 说明如何从 Windows 侧访问当前服务器
- 说明服务器的工作目录、背景情况和当前阶段的真实状态
- 给出 Windows 本地修复的建议顺序

## 2. 当前背景

当前 seller agent v2 的正式路径已经切到：

- `Windows`
  - 控制台
  - 第一次运行脚本
  - 本地 Codex / MCP 宿主
- `WSL Ubuntu`
  - seller compute
  - Docker Engine
  - WireGuard
  - Swarm worker

目前已经验证过：

- Windows 到服务器的 WireGuard / SSH 链路可用
- 服务器到 Windows 的 WireGuard / SSH 链路可用
- `seller-client` 和 `environment_check` 已经同步到 Windows 工作区
- Windows 上 `seller_client_app` 的 `compileall` 已通过

但当前还有一个很重要的现实问题：

> `windows_seller_host_install_and_check.ps1` 在 `-Mode check` 下可以正常产出 JSON，
> 但 `-Mode all` 通过远程 SSH 驱动时不够稳定；
> 因此当前阶段建议你直接在 Windows 本地桌面会话里执行修复和安装。

也就是说：

- 这个脚本的正式使用方式应该是：**在 Windows 本地管理员 PowerShell 中运行**
- 而不是长期依赖远程 SSH 会话直接驱动完整安装

## 3. 服务器信息

当前服务器信息：

- 主机名：`VM-0-3-opencloudos`
- 当前账号：`root`
- 当前仓库工作目录：`/root/Pivot_network`
- 服务器公网 IP：`81.70.52.75`
- 服务器 WireGuard 地址：`10.66.66.1/24`

Host TenCent
    HostName 81.70.52.75
    User root
    Port 22
    IdentityFile D:/AI/Pivot_backend_build_team/navi.pem

当前仓库根目录：

```text
/root/Pivot_network
```

这也是我当前修改代码和文档时使用的工作目录。

## 4. Windows 当前工作区

推荐 Windows 工作区：

```text
D:\AI\Pivot_Client
```

当前 seller v2 staging 目录：

```text
D:\AI\Pivot_Client\seller_client_v2_stage
```

当前脚本目录：

```text
D:\AI\Pivot_Client\seller_client_v2_stage\environment_check
```

当前 seller client 目录：

```text
D:\AI\Pivot_Client\seller_client_v2_stage\seller-client
```

## 5. Windows 侧如何访问这台服务器

如果你已经有 Windows 到这台服务器的 SSH 权限，优先使用你平时稳定可用的登录方式。

当前服务器公网地址是：

```text
81.70.52.75
```

常见登录形式示例：

```powershell
ssh root@81.70.52.75
```

如果你平时使用的不是 `root`，请把用户名替换成你的实际服务器账号。

登录后，建议先进入仓库目录：

```bash
cd /root/Pivot_network
```

## 6. 服务器如何访问 Windows

这条链路已经打通，服务器上可直接登录 Windows：

```bash
ssh win-local-via-wg
```

当前 alias 配置位于：

```text
/root/.ssh/config
```

对应内容是：

```sshconfig
Host win-local-via-wg
  HostName 10.66.66.10
  User 550w
  Port 22
  IdentityFile /root/.ssh/id_ed25519_windows_local
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
```

这表示：

- 服务器通过 WireGuard 地址 `10.66.66.10`
- 以用户 `550w`
- 登录 Windows

## 7. 为什么建议在 Windows 本地修复

当前已经观察到：

- 远程 `check` 模式可以正常产出 JSON
- 但 `all` 模式在 SSH 驱动下不够稳定
- `wsl -d Ubuntu -- ...` 在远程链路里也可能卡住

因此现在更合理的操作方式是：

1. 在 Windows 本地桌面会话里打开 **管理员 PowerShell**
2. 直接运行第一次安装脚本
3. 本地观察脚本输出和 JSON 报告
4. 如果 Ubuntu 依赖仍有阻塞项，再在 Windows 本地继续人工修复

这样能绕开：

- SSH 会话环境差异
- WSL 在远程上下文中的交互/输出问题
- 远程安装时 stdout/stderr 不稳定的问题

## 8. 当前已知阻塞项

当前最近一次 `check` 结果显示，Windows 侧已通过：

- 管理员权限
- PowerShell
- Python 3.11+
- WSL2
- Ubuntu 发行版
- Backend 连通性
- Codex CLI

当前 Ubuntu 侧阻塞项是：

- `ubuntu_python3`
- `ubuntu_venv`
- `ubuntu_docker_cli`
- `ubuntu_dockerd`
- `ubuntu_wireguard`
- `ubuntu_workspace_root`

这意味着当前最需要修的是 Ubuntu compute 基础依赖，而不是 Windows seller console 本体。

## 9. Windows 本地建议修复顺序

推荐顺序如下。

### 第一步：本地运行第一次脚本

在 Windows 本地管理员 PowerShell 中执行：

```powershell
powershell -ExecutionPolicy Bypass -File D:\AI\Pivot_Client\seller_client_v2_stage\environment_check\windows_seller_host_install_and_check.ps1 -Mode all
```

如果你只想先重新检查：

```powershell
powershell -ExecutionPolicy Bypass -File D:\AI\Pivot_Client\seller_client_v2_stage\environment_check\windows_seller_host_install_and_check.ps1 -Mode check
```

### 第二步：看 JSON 结果

脚本会在 `environment_check` 目录下生成类似文件：

```text
seller-windows-host-check-YYYYMMDD-HHMMSS.json
```

优先看这些域：

- `windows_host_checks`
- `ubuntu_compute_checks`
- `network_checks`
- `platform_checks`
- `assistant_checks`

### 第三步：如果 Ubuntu 依赖仍失败，手工确认

在 Windows 本地执行：

```powershell
wsl -d Ubuntu -- bash -lc "whoami"
wsl -d Ubuntu -- bash -lc "which python3 && python3 --version"
wsl -d Ubuntu -- bash -lc "python3 -m venv /tmp/pivot-venv-check && test -d /tmp/pivot-venv-check && echo venv-ok"
wsl -d Ubuntu -- bash -lc "which docker && which dockerd && which wg"
wsl -d Ubuntu -- bash -lc "mkdir -p /opt/pivot/workspace && echo workspace-ok"
```

如果这些命令在 Windows 本地都正常，而脚本仍失败，说明脚本本身还有问题。

### 第四步：修完后再回到 seller client

Ubuntu 基础依赖就绪后，再进入 seller client 正式链路：

- Windows host install/check
- Ubuntu bootstrap
- 标准容器拉取与验证
- Ubuntu 宿主执行 `docker swarm join`
- 检查 `NodeAddr`
- `compute-ready`
- `claim node`

## 10. 当前要点结论

- 服务器工作目录：`/root/Pivot_network`
- Windows staging 工作区：`D:\AI\Pivot_Client\seller_client_v2_stage`
- 服务器访问 Windows：`ssh win-local-via-wg`
- Windows 访问服务器：使用你的正常 SSH 入口，目标服务器公网 IP 是 `81.70.52.75`
- 当前脚本应优先在 **Windows 本地管理员 PowerShell** 中运行
- 当前主要修复目标不是 seller client 本体，而是 Ubuntu compute 基础依赖链路

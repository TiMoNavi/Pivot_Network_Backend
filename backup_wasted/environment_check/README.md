# Seller Windows Host Environment Check

这个目录承接 seller v2 的 Windows host 安装与检查流程。

正式脚本：

- `windows_seller_host_install_and_check.ps1`

## 目标

这个流程只面向 seller 的 `Windows Host`，用于确认它是否满足：

- 控制台运行
- 第一次 seller host 安装
- WSL Ubuntu 可进入
- Ubuntu 基础依赖就绪
- Codex / MCP 宿主能力
- Backend HTTPS 控制面访问

它 **不** 把 `Docker Desktop` 当成 seller 正式依赖。

## 默认检查项

阻塞项：

- Administrator privilege
- PowerShell
- Python 3.11+
- WSL2
- Ubuntu distribution
- Ubuntu Python 3 / venv
- Ubuntu docker.io / dockerd
- Ubuntu wireguard-tools
- Ubuntu workspace root
- Codex CLI
- Backend health reachability

非阻塞网络项：

- Ubuntu WireGuard interface
- Ubuntu -> manager SSH
- Ubuntu -> Swarm manager port

## 运行方式

```powershell
powershell -ExecutionPolicy Bypass -File D:\AI\Pivot_Client\seller_client_v2_stage\environment_check\windows_seller_host_install_and_check.ps1
```

支持的模式：

- `-Mode check`
- `-Mode install`
- `-Mode all`

默认模式是 `all`，会执行：

1. 检查
2. 对可自动处理的缺失项尝试安装或引导
3. 再次检查

## 结果输出

脚本会输出：

- 终端摘要
- JSON 报告文件

JSON 结果按域分开：

- `windows_host_checks`
- `ubuntu_compute_checks`
- `network_checks`
- `platform_checks`
- `assistant_checks`
- `checks`

每条结果都包含：

- `title`
- `category`
- `status`
- `blocking`
- `detail`
- `hint`

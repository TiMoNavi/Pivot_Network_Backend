# Pivot Seller Client

`seller-client/` 是 Pivot Network 的卖家本地控制台。它的唯一正式架构是：

- `Windows Host`
  - 控制台
  - 启动入口
  - 文件选择
  - 日志展示
  - Codex / MCP 宿主
- `WSL Ubuntu Compute`
  - WireGuard compute peer
  - Docker Engine
  - Swarm worker
  - seller runtime image build / push

seller compute 已经不再以 Windows 主机或 Docker Desktop 作为正式底座。

## 权威设计文档

完整 seller v2 链路说明见：

- [docs/windows-console-wsl-ubuntu-compute.md](docs/windows-console-wsl-ubuntu-compute.md)

这份文档定义了：

- 为什么必须从 Windows compute 迁到 WSL Ubuntu
- seller onboarding 正式链路
- bootstrap / policy / runtime contract
- Windows host 安装检查流程
- Ubuntu bootstrap / join / claim / build / report
- 旧路径删除清单

## 当前目录结构

```text
seller-client/
├── seller_client_app/
├── windows_host_app/
├── ubuntu_compute_assets/
├── bootstrap/
│   ├── windows/
│   └── ubuntu/
├── docs/
├── scripts/
└── tests/
```

当前分工：

- `seller_client_app/`
  当前仍承载本地 FastAPI、浏览器 UI、状态管理、Codex/MCP、Ubuntu 调用封装
- `windows_host_app/`
  Windows 控制台职责说明
- `ubuntu_compute_assets/`
  Ubuntu compute 侧职责说明
- `bootstrap/windows/`
  Windows 正式入口
- `bootstrap/ubuntu/`
  Ubuntu bootstrap 辅助脚本

## 本地开发

```bash
cd /root/Pivot_network/seller-client
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
python -m uvicorn seller_client_app.main:app --host 127.0.0.1 --port 8901
```

打开：

`http://127.0.0.1:8901/`

## Windows 正式入口

```powershell
bootstrap\windows\start_seller_console.ps1
```

Windows seller host 的正式安装与检查流程见：

- [/root/Pivot_network/environment_check/README.md](/root/Pivot_network/environment_check/README.md)
- [/root/Pivot_network/environment_check/windows_seller_host_install_and_check.ps1](/root/Pivot_network/environment_check/windows_seller_host_install_and_check.ps1)

## 官方链路摘要

1. Windows 启动 seller console。
2. Windows 执行 seller host 安装/检查流程。
3. seller 登录 `Backend` 并创建 onboarding session。
4. Windows 拉取 `bootstrap-config` 与 `ubuntu-bootstrap`。
5. Windows 调起 `WSL Ubuntu` bootstrap。
6. Windows 同步 build context 到 Ubuntu。
7. Ubuntu 以 WireGuard IP 加入 Swarm。
8. Windows 回写 `compute-ready` 并发起 claim。
9. Ubuntu 执行 `build / tag / push`。
10. Windows 发起 `image report`。

## 当前仓库状态

仓库里仍有少量过渡实现尚未删除，但它们不再代表 seller 官方正式路径。

如果文档与旧兼容代码冲突，以 [docs/windows-console-wsl-ubuntu-compute.md](docs/windows-console-wsl-ubuntu-compute.md) 为准。

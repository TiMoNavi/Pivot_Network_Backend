# Pivot Buyer Client

`buyer-client/` 是 Pivot Network 的买家本地控制台。

buyer 的正式形态仍然是：

- `Windows` 本地应用
- 公网 HTTPS 控制面
- 本机 WireGuard 临时隧道
- 本地工作区打包与同步

buyer **不需要** 自己的 WSL Ubuntu compute，也 **不依赖** seller 的 Windows 主机。
buyer 只依赖：

- `Backend`
- 本机 WireGuard
- seller Ubuntu compute 产出的 runtime / gateway 元数据

## 当前目标

- 登录并获取 catalog
- 创建订单并兑换 access code
- 创建 runtime session
- 获取 buyer runtime bootstrap-config 与 connect material
- 拉起 session 级 WireGuard 隧道
- 在本地 UI 内嵌 shell 页面
- 把本地工作区同步到 runtime 工作目录

## 本地开发

```bash
cd /root/Pivot_network/buyer-client
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
python -m uvicorn buyer_client_app.main:app --host 127.0.0.1 --port 8902
```

打开 `http://127.0.0.1:8902/`。

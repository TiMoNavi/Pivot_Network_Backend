# Seller Ubuntu Compute Assets

这个目录承载 seller v2 中 `WSL Ubuntu Compute` 的正式职责说明。

Ubuntu compute 负责：

- 安装 `docker.io`
- 安装 `wireguard-tools`
- 建立 compute peer
- 以 Ubuntu WireGuard IP 加入 Swarm
- 接收 Windows 同步过来的 build context
- 执行 seller runtime image `build / tag / push`
- 运行 seller runtime

这部分能力之所以必须落在 Ubuntu，而不是 Windows Docker Desktop，是因为平台需要 seller compute node 在 Swarm 数据面上稳定暴露 Ubuntu 的 WireGuard 地址。

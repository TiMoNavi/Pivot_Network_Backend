# Portainer

这个目录单独承接 Portainer 的部署资产，避免继续和 `Docker_Swarm/` 的业务与 benchmark 资产混放。

当前文件：

- `compose.portainer.yml`：Portainer CE 与全局 agent 的 Swarm stack 定义
- `deploy-portainer.sh`：复用 `Docker_Swarm/scripts/common.sh` 的部署脚本

常用命令：

```bash
cd /root/Pivot_network/Portainer
./deploy-portainer.sh
```

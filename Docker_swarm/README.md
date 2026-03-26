# Docker Swarm

这个目录放项目的单机 Docker Swarm 部署资产和架构说明：

- [CURRENT_SETUP.md](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/CURRENT_SETUP.md)：完整架构说明，包含 Docker Swarm / Portainer / Registry / `swarm_adapter` 的当前状态与连接关系
- [TASK_3_CLI_EVIDENCE.md](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/TASK_3_CLI_EVIDENCE.md)：任务 3 的最小 CLI 真实链路、验证命令与诚实停点
- `compose.swarm.yml`：业务 stack，固定把 `backend`、`db`、`redis`、`worker` 调度到 manager
- `compose.portainer.yml`：Portainer CE 控制台 stack
- `compose.benchmark.yml`：轻量 benchmark 验证 stack，只调度到 compute 节点
- `benchmark_worker/`：本地 benchmark worker 镜像定义与脚本
- `scripts/`：初始化、构建、部署、状态查看和 worker join 命令脚本
- `scripts/label-control-plane.sh`：把 manager 节点标成平台控制平面
- `scripts/label-compute-node.sh`：安全认领 seller 节点为 compute，拒绝 manager/control-plane、重复 compute id 和 owner 冲突
- `scripts/inspect-node.sh`：输出单个节点的 role、availability、平台标签与当前任务
- `scripts/set-node-availability.sh`：只允许对非 control-plane worker 做 `active|drain`，并在 `drain` 前拦截仍有 replicated workload 的节点
- `scripts/configure-registry-access.sh`：把 Docker daemon 配成信任 manager registry
- `scripts/print-compute-node-onboarding.sh`：打印 seller 节点接入步骤
- `scripts/create-local-seller-node.sh`：在本机创建一个低占用 seller worker，用于验证加入规则
- `scripts/remove-local-seller-node.sh`：移除本机 seller worker 验证节点
- `scripts/build-benchmark-image.sh`：构建并推送 benchmark worker 镜像
- `scripts/deploy-benchmark-stack.sh`：部署 benchmark 验证 stack

实现细节：

- `build-backend-image.sh` 会自动启动一个 manager LAN 可访问的轻量 registry
- 后端镜像会先本地构建，再推到这个 manager registry，避免以后 compute 节点加入后拉不到自定义镜像
- benchmark worker 镜像也会先本地构建，再推到这个 manager registry
- `deploy-portainer.sh` 也会先把 `portainer/agent` 和 `portainer-ce` 缓存进这个 manager registry，再进行部署
- `configure-registry-access.sh` 会修改宿主机 `/etc/docker/daemon.json`，加入 `insecure-registries` 并重启 Docker

推荐执行顺序：

```bash
cd /home/cw/ybj/Pivot_backend_build_team/Docker_swarm
./scripts/init-manager.sh <manager_lan_ip>
./scripts/configure-registry-access.sh 192.168.2.208:5000
./scripts/build-backend-image.sh
./scripts/deploy-app-stack.sh
./scripts/run-prestart.sh
./scripts/deploy-portainer.sh
./scripts/label-control-plane.sh self 192.168.2.208
./scripts/build-benchmark-image.sh
./scripts/create-local-seller-node.sh
./scripts/deploy-benchmark-stack.sh
./scripts/status.sh
```

访问入口：

- API: `http://<manager_ip>:8000`
- Portainer: `https://<manager_ip>:9443`
- Registry: `http://<manager_ip>:5000/v2/_catalog`

Marketplace 标签约定：

- 控制平面节点：`platform.role=control-plane`
- 可售卖算力节点：`platform.role=compute`
- seller 节点关键标签：`platform.compute_node_id`、`platform.seller_user_id`、`platform.accelerator`
- benchmark 验证服务关键约束：`platform.role=compute`、`platform.compute_enabled=true`

未来 seller 节点加入时：

```bash
cd /home/cw/ybj/Pivot_backend_build_team/Docker_swarm
./scripts/print-compute-node-onboarding.sh
```

为什么这里不用 Edge Agent：

- `Agent` 更适合同一个 Swarm / 局域网内的直接管理
- `Edge Agent` 更适合远端节点主动回连 Portainer 的场景
- 你的目标是“别人电脑加入这个 Swarm 变成算力节点”，所以先把普通 `Agent + manager registry + worker label` 调顺更重要

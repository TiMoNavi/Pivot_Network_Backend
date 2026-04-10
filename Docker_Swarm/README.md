# Docker Swarm

更新时间：`2026-04-10`

这里是当前项目唯一的 Docker Swarm 基础设施目录，也是 seller onboarding 和未来 runtime 执行面的基础设施根目录。

## 当前权威地址

- swarm manager 公网地址：`81.70.52.75`
- swarm manager WireGuard / control-plane 地址：`10.66.66.1`
- 当前权威 join target：`10.66.66.1:2377`

当前地址语义必须这样理解：

- `81.70.52.75`
  - SSH / 外网访问 / 公网入口
- `10.66.66.1`
  - seller swarm join 的 control-plane 目标
  - adapter `join-material.manager_addr`

## 目录约定

- `scripts/`
  - 当前唯一正式运维入口
- `env/`
  - 当前 Swarm / Portainer / registry 环境变量
- `stack/`
  - 权威 stack 文件
- `docs/`
  - 当前 Swarm/adapter 运维说明
- `upstream/`
  - 上游同步内容
- `Docker_Swarm_Adapter/`
  - 当前私有控制面 HTTP 服务

## 与项目其它模块的关系

当前正式链路固定为：

- `Seller_Client -> Plantform_Backend -> Docker_Swarm_Adapter -> Docker Swarm`

其中：

- `Seller_Client` 不直连 Swarm manager，也不直连 adapter
- `Plantform_Backend` 通过 adapter 获取 `join-material`、执行 inspect/claim/inspect
- `Docker_Swarm_Adapter` 使用本目录提供的环境与 Docker 命令完成基础设施动作

## 常用命令

```bash
cd /root/Pivot_network/Docker_Swarm
./scripts/archive-current-state.sh
./scripts/status.sh
./scripts/fetch-portainer-upstream.sh
./scripts/deploy-portainer.sh
./scripts/reset-swarm.sh
```

Adapter 开发或联调：

```bash
cd /root/Pivot_network/Docker_Swarm/Docker_Swarm_Adapter
./scripts/install-venv.sh
./scripts/check.sh
./scripts/run-dev.sh
```

## 当前环境文件语义

`env/swarm.env` 当前关键字段：

- `SWARM_MANAGER_ADDR=81.70.52.75`
- `SWARM_CONTROL_ADDR=10.66.66.1`
- `SWARM_DATA_PATH_ADDR=10.66.66.1`
- `SWARM_LISTEN_ADDR=10.66.66.1:2377`

这意味着 seller join 与 control-plane 文档都应该以 `SWARM_CONTROL_ADDR` 为准，而不是把公网 manager 地址重新写成 join target。

## 当前约束

- 当前为单 manager 基线
- Portainer 只是运维观察面，不是正式控制 API
- `wg0` 保持启用
- seller onboarding 的正式完成标准已经转成 manager-side task execution，不再是本地 `docker info` 自报

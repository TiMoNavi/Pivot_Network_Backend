# Docker Swarm 当前架构与配置说明

本文档描述当前项目这套 Docker Swarm 的完整情况，包括：

- 什么是 Docker Swarm
- 这套 Swarm 在你的项目里想解决什么问题
- 当前有哪些组件，它们分别做什么
- 这些组件的配置文件在哪、运行数据在哪
- Portainer、Registry、benchmark worker、`swarm_adapter` 之间是什么关系
- 当前已经实机验证到什么程度

更新时间：2026-03-23

## 1. 什么是 Docker Swarm

Docker Swarm 是 Docker 自带的集群编排能力。你可以把多台装了 Docker 的机器组织成一个集群，然后把服务交给 Swarm 去部署、调度、重启和管理。

在 Swarm 里最重要的几个概念是：

- `manager`：控制节点，负责保存集群状态和接收部署命令
- `worker`：执行节点，负责真正运行容器任务
- `service`：你希望持续存在的一类任务，比如 API、worker、benchmark 容器
- `stack`：一组服务的集合，通常由一个 Compose 文件描述
- `overlay network`：跨节点容器互通的网络
- `node label`：给节点打标签，用于表达节点角色和调度规则

对你的项目来说，Swarm 的意义不是“本机起几个容器”，而是为以后把别人的电脑接进平台、当成可调度的算力节点做准备。

## 2. 这套 Swarm 在你的项目里要做什么

你的目标不是普通 Web 部署，而是“算力交易平台”的基础设施雏形。

它现在分成三层：

### 第一层：控制平面先稳定

当前已经完成：

- 一个可用的 manager
- 一套基础业务服务：`backend`、`db`、`redis`、`worker`
- Portainer 控制台
- 一个本地 Registry，用来给未来新节点分发镜像

### 第二层：卖家电脑可以加入

这对应你的核心设想：“一个人把自己的电脑加进来，作为算力节点”。

当前已经能做到：

- 节点通过 `docker swarm join` 加入
- manager 端为节点打平台标签
- 集群能识别这是一个 compute 节点
- benchmark 容器可以按标签被调度过去

### 第三层：平台后端真正接管调度

这部分还没做完，是后续方向：

- 后端 API 真实读取 Swarm 节点和服务状态
- 后端 API 真实创建和删除 benchmark / runtime service
- 按 seller、节点标签、资源情况做平台级调度

## 3. 当前整体拓扑

当前真实拓扑如下：

```text
你的电脑（192.168.2.208）
├─ Docker Swarm manager
│  ├─ 业务 stack
│  │  ├─ backend
│  │  ├─ db
│  │  ├─ redis
│  │  └─ worker
│  ├─ Portainer stack
│  │  ├─ portainer
│  │  └─ agent
│  ├─ Benchmark stack
│  │  └─ benchmark_worker
│  └─ 本地 Registry 容器
│
└─ 本机模拟 seller 节点
   └─ seller-local-001
      ├─ 作为 Swarm worker 加入
      ├─ 自动运行 portainer agent
      └─ 承载 benchmark_worker
```

当前设计是：

- manager 负责控制平面
- 正式业务服务固定在 manager
- 本机额外模拟一个 seller worker，用于验证加入规则和 compute 调度
- benchmark 服务单独作为验证栈存在，不混入业务栈

这样做的好处是：

- 对现有业务影响小
- 验证链路清晰
- 资源占用可控
- 为未来真实 seller 节点接入留好结构

## 4. `Docker_swarm` 文件夹里现在有什么

`/home/cw/ybj/Pivot_backend_build_team/Docker_swarm` 目录放的是“Swarm 编排文件、镜像定义和脚本”，不是容器运行数据目录。

当前主要内容：

- [compose.swarm.yml](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/compose.swarm.yml)
  业务 stack 定义
- [compose.portainer.yml](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/compose.portainer.yml)
  Portainer stack 定义
- [compose.benchmark.yml](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/compose.benchmark.yml)
  benchmark 验证 stack 定义
- [benchmark_worker/](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/benchmark_worker)
  轻量 benchmark worker 镜像定义
- [scripts/](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/scripts)
  初始化、构建镜像、部署 stack、创建本地 seller 节点、打印 join 命令、打标签、查看状态等脚本

也就是说：

- `Docker_swarm` 目录里有“怎么部署”
- Portainer 数据、Registry 数据、Postgres 数据并不默认放在这里
- 它们目前都放在 Docker 自己管理的 volume 目录里

## 5. 当前有哪些核心组件

### 5.1 Swarm manager

当前 manager 地址：

- `192.168.2.208`

当前 manager 标签：

- `platform.managed=true`
- `platform.role=control-plane`
- `platform.control_plane=true`
- `platform.compute_enabled=false`
- `platform.manager_addr=192.168.2.208`

含义：

- 它是平台控制节点
- 它不是卖家算力节点
- 它负责部署、观察、统一管理整个集群

### 5.2 业务 stack

业务 stack 文件：

- [compose.swarm.yml](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/compose.swarm.yml)

当前服务：

- `backend`
- `db`
- `redis`
- `worker`

当前部署策略：

- 都是 `replicas: 1`
- 都固定在 manager：`node.role == manager`
- `backend` 使用 `--workers 1`
- `worker` 使用 `--pool=solo --concurrency=1`
- 对外开放 `8000`、`5432`、`6379`

这说明当前业务层的定位是：

- 先把平台控制面和业务 API 稳定跑起来
- 不让 seller 节点承载正式业务服务

### 5.3 Portainer

Portainer 是 Docker / Swarm 的网页控制台，不是你的业务后端。

它的作用：

- 看集群里有哪些节点
- 看 stack / service / task 状态
- 看日志
- 查看新节点是否加入成功
- 查看 benchmark 容器最终落到哪个节点

Portainer 配置文件：

- [compose.portainer.yml](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/compose.portainer.yml)

当前服务：

- `portainer`
- `agent`

当前部署策略：

- `portainer` 固定在 manager
- `agent` 使用 `global` 模式
- 所有 Linux 节点都会跑一个 agent
- 当前外部入口是 `https://192.168.2.208:9443`

当前实机状态：

- 由于 seller-local-001 已加入
- `portainer_agent` 当前是 `2/2`
- Portainer 已能看到 manager 和本机模拟 seller 节点

### 5.4 Registry

Registry 是镜像仓库，不是管理界面。

它的作用：

- 保存项目业务镜像
- 保存 benchmark worker 镜像
- 保存 Portainer 所需镜像缓存
- 让未来 compute 节点能从 manager 拉镜像

当前 Registry 由脚本自动拉起，不是 stack 服务。

当前地址：

- `192.168.2.208:5000`

当前至少缓存了这些仓库：

- `pivot-backend-build-team/backend`
- `pivot-backend-build-team/benchmark-worker`
- `portainer/agent`
- `portainer/portainer-ce`

### 5.5 Benchmark stack

benchmark stack 不是正式计费模块，而是当前用于验证“compute 节点加入后，AI benchmark 容器能不能被调度过去”的轻量验证栈。

相关文件：

- [compose.benchmark.yml](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/compose.benchmark.yml)
- [Dockerfile](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/benchmark_worker/Dockerfile)
- [benchmark_stub.py](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/benchmark_worker/benchmark_stub.py)

当前服务：

- `benchmark_worker`

当前部署策略：

- `replicas: 1`
- 只允许调度到 `platform.role=compute`
- 额外要求 `platform.compute_enabled=true`
- 当前默认要求 `platform.compute_node_id == compute-local-001`
- 内存上限 `128M`
- 默认输出一条结构化 benchmark JSON 后低占用保持存活

当前这层的意义：

- 验证 seller 节点标签是否影响调度
- 验证 compute 节点能否从本地 Registry 拉镜像
- 验证 Portainer 是否能看到 benchmark 服务落点

### 5.6 本机模拟 seller 节点

当前为了验证“卖家节点加入规则”，已经在本机额外创建了一个轻量 seller worker：

- 节点名：`seller-local-001`
- 实现方式：`docker:26.1-dind`
- 验证时资源限制：`1.0 CPU`、`768M memory`

当前标签：

- `platform.managed=true`
- `platform.role=compute`
- `platform.control_plane=false`
- `platform.compute_enabled=true`
- `platform.compute_node_id=compute-local-001`
- `platform.seller_user_id=seller-local-001`
- `platform.accelerator=cpu`

说明：

- 它是一个本机模拟 worker，不是正式卖家电脑
- 目的是用最低风险验证 seller 节点加入、标签和调度规则
- 如果以后不需要它，可以随时移除

### 5.7 Swarm Adapter

`swarm_adapter` 是你业务后端里“平台逻辑接 Docker Swarm”的那一层。

它不是 Portainer，也不是 Registry，而是平台后端代码里的模块。

当前相关代码：

- [service.py](/home/cw/ybj/Pivot_backend_build_team/backend/app/modules/swarm_adapter/service.py)
- [swarm_adapter.py](/home/cw/ybj/Pivot_backend_build_team/backend/app/api/routes/swarm_adapter.py)
- [swarm_adapter.py](/home/cw/ybj/Pivot_backend_build_team/backend/app/tasks/swarm_adapter.py)

它未来应负责：

- 生成 worker join 命令
- 查询节点状态
- 读取节点硬件摘要
- 认领 seller 节点
- 修改 availability
- 创建 / 删除 benchmark service
- 创建 / 删除 runtime service
- 查询 service 状态并做 reconcile

当前状态要特别说明：

- `swarm_adapter` 仍然是 `stub`
- 返回的是内存假数据
- 还没有真正读取当前这套真实 Swarm
- 健康检查也明确写着当前阶段是 `stage-1-swarm-adapter-stub`

结论是：

- Swarm 基础设施现在是真的
- Portainer 和 Registry 现在是真的
- benchmark stack 和 seller 节点验证也是真的
- 但 `swarm_adapter` 还没真正接到这些真实组件上

## 6. Portainer 和 Registry 现在到底放在哪里

这里必须分清“配置文件位置”和“运行时数据位置”。

### 6.1 Portainer 配置文件位置

Portainer 的部署文件在仓库里：

- [compose.portainer.yml](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/compose.portainer.yml)

### 6.2 Portainer 运行数据位置

Portainer 数据当前在 Docker volume 里，不在仓库目录里：

- volume 名称：`portainer_portainer_data`
- 挂载路径：`/var/lib/docker/volumes/portainer_portainer_data/_data`

### 6.3 Registry 配置位置

Registry 没有单独的 Compose 文件，而是由脚本在需要时自动启动。

关键脚本：

- [common.sh](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/scripts/common.sh)
- [build-backend-image.sh](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/scripts/build-backend-image.sh)
- [build-benchmark-image.sh](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/scripts/build-benchmark-image.sh)
- [deploy-portainer.sh](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/scripts/deploy-portainer.sh)

当前 Registry 容器名：

- `pivot-swarm-registry`

### 6.4 Registry 运行数据位置

Registry 数据当前也不在仓库目录里，而是在 Docker volume 里。

当前状态：

- 使用了匿名 volume
- 当前 volume 名称：`a3323121681c4736862e0738589d2bbec977c3063b7316a1de0508a6150c4e0e`
- 当前挂载路径：`/var/lib/docker/volumes/a3323121681c4736862e0738589d2bbec977c3063b7316a1de0508a6150c4e0e/_data`

所以结论是：

- Portainer 和 Registry 的编排脚本都在 `Docker_swarm` 目录里
- 但它们的实际运行数据都不在 `Docker_swarm` 目录里
- Portainer 用命名 volume
- Registry 目前用匿名 volume

## 7. 当前各组件之间是怎么连起来的

### 7.1 业务服务

- `backend` 连 `db`
- `backend` 连 `redis`
- `worker` 连 `redis`
- `backend` 和 `worker` 共用业务环境变量

### 7.2 Portainer

- `portainer` 通过 `agent` 管理当前 Swarm
- 新 Linux 节点加入后，`agent` 会自动部署到新节点
- 所以 Portainer 看到的是整个 Swarm，不只是 manager

### 7.3 Registry

- 业务镜像先在 manager 构建
- benchmark worker 镜像也先在 manager 构建
- 两者再推送到 `192.168.2.208:5000`
- compute 节点从这里拉取项目镜像

### 7.4 Benchmark stack

- benchmark worker 镜像来自 manager Registry
- benchmark service 只匹配 compute 节点标签
- 当前实际落点是 `seller-local-001`
- 输出结果通过 `docker service logs` 可见

### 7.5 平台后端与 Swarm

这一层目前还没真正打通：

- API 里已经有 `/swarm-adapter/...` 路由
- 但它们现在调用的是 `SwarmAdapterStubService`
- 还没有真实执行 `docker node ls`、`docker service create`、`docker stack deploy`

所以当前真实关系是：

- Portainer 管理真实 Swarm
- 脚本部署真实 Swarm
- benchmark stack 通过脚本真实运行
- 业务 API 里的 `swarm_adapter` 目前仍只是接口雏形

## 8. 当前 benchmark 验证结果

当前已经实际跑通一条低占用 benchmark 验证链路：

- Swarm 中新增了一个 compute 节点：`seller-local-001`
- Portainer `agent` 已从 `1/1` 变成 `2/2`
- benchmark stack 名称：`pivot-benchmark`
- benchmark service 名称：`pivot-benchmark_benchmark_worker`
- benchmark 任务实际落在：`seller-local-001`

当前 benchmark 日志已经能看到结构化输出，字段至少包含：

- `benchmark_job_id`
- `listing_id`
- `requested_profile`
- `cpu_cores_visible`
- `memory_limit_mb`
- `gpu_count`
- `runtime_source`

查看方式：

```bash
docker service logs --tail 20 pivot-benchmark_benchmark_worker
```

## 9. 当前对外入口

当前主要访问入口：

- API：`http://192.168.2.208:8000`
- 健康检查：`http://192.168.2.208:8000/api/v1/health`
- Portainer：`https://192.168.2.208:9443`
- Registry：`http://192.168.2.208:5000/v2/_catalog`
- Postgres：`192.168.2.208:5432`
- Redis：`192.168.2.208:6379`

## 10. 当前开放端口与网络要求

如果后续要让别人的电脑加入这套 Swarm，manager 需要放通：

- `2377/tcp`
- `7946/tcp`
- `7946/udp`
- `4789/udp`
- `9001/tcp`
- `5000/tcp`

含义：

- `2377`：Swarm join / manager 通信
- `7946`：节点发现
- `4789`：overlay 网络
- `9001`：Portainer agent
- `5000`：从 manager Registry 拉项目镜像

## 11. 当前 seller 节点怎么接入

未来真实 seller 电脑的标准接入流程仍然是：

1. 对方电脑安装 Docker，优先建议 Linux。
2. 对方电脑把 Docker 配成信任 `192.168.2.208:5000`。
3. 对方电脑执行 manager 打印出的 worker join 命令。
4. manager 上确认新节点进入集群。
5. manager 上给该节点打 compute 标签。

相关脚本：

- [print-worker-join.sh](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/scripts/print-worker-join.sh)
- [print-compute-node-onboarding.sh](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/scripts/print-compute-node-onboarding.sh)
- [label-compute-node.sh](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/scripts/label-compute-node.sh)

当前为了验证这套规则，还额外准备了本机模拟脚本：

- [create-local-seller-node.sh](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/scripts/create-local-seller-node.sh)
- [remove-local-seller-node.sh](/home/cw/ybj/Pivot_backend_build_team/Docker_swarm/scripts/remove-local-seller-node.sh)

如果后续想释放本机资源，可以执行：

```bash
cd /home/cw/ybj/Pivot_backend_build_team/Docker_swarm
./scripts/remove-local-seller-node.sh
```

## 12. 未来 `swarm_adapter` 应该怎么接

如果你的目标是做算力交易平台，那么 `swarm_adapter` 下一阶段应该从“stub”变成“真实适配层”。

建议定位：

- Portainer 继续做运维控制台
- `swarm_adapter` 做平台程序接口
- 二者不是替代关系

建议先接三件事：

1. 真实读取节点和标签
2. 真实创建 / 删除 benchmark service
3. 真实读取 service / task 状态

对于你当前这套单 manager 原型，最务实的方式是：

- 后端继续运行在 manager
- 后端通过本机 Docker CLI 或 Docker SDK 调用 Swarm
- Portainer 保持为观察和人工运维入口

## 13. 当前已经做到了什么，没做到什么

### 已做到

- 单机 manager Swarm 已稳定运行
- 业务 stack 已运行
- Portainer 控制台已运行
- manager 本地 Registry 已运行
- manager 已打控制平面标签
- seller 节点加入路径已准备并完成一次本机验证
- compute 节点标签约定已准备
- 轻量 benchmark worker 镜像已准备
- benchmark service 已能按 compute 标签落到 seller 节点
- Portainer 已能看到第二个节点与 benchmark service

### 还没做到

- `swarm_adapter` 真实接管 Swarm
- 平台通过 API 自动派发 benchmark / runtime 到 compute 节点
- GPU 实际探测和规格建模
- seller 节点计费、结算、仲裁
- 租用任务生命周期闭环

## 14. 当前最建议的下一步

如果继续按“算力交易平台”路线往前走，最值得做的是补上真正的“平台派单链路”：

1. 让 `swarm_adapter` 真实读取当前节点和标签
2. 让 `swarm_adapter` 真实创建和删除 benchmark service
3. 把现在脚本里的 benchmark 调度逻辑逐步收敛到后端接口里

这样你就会从“脚本已经能把 benchmark 派到 seller 节点”进入到“平台 API 已经能把 benchmark 派到 seller 节点”的下一阶段。

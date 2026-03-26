# Pivot Backend Build Team Project

> 2026-03-24 重建备份。
> 这份文件是按会话记录恢复的“较好的 8 步任务主线版 PROJECT”，作为后续重写蓝本保留。

## 当前唯一主线

这个目录只用于逐步落成后端工程。

当前只处理一条主线：`后端接 Docker Swarm`。

本轮唯一激活任务是 `Swarm Adapter`。`Pricing` 和 `AI Benchmark` 不再放在当前主文档里混做，已拆到单独保留文档：

- `future_task_packages/PRICING.md`
- `future_task_packages/AI_BENCHMARK.md`

要求很简单：

- 一次只做一个主线
- 不把后续模块顺手混进当前切片
- 先把“后端真实接上 Docker Swarm”做扎实，再继续往后走

## 本项目后端架构

本项目按以下后端架构落地：

- `Python`
- `FastAPI`
- `SQLAlchemy 2`
- `Alembic`
- `Celery`
- `Redis`
- `MySQL`

`Swarm Adapter` 是这套后端里的正式模块，不是独立脚本集合。

## 当前 Docker Swarm 现状

当前已经有可工作的 Swarm 环境，不是从零开始。

### 控制平面

- manager 地址：`192.168.2.208`
- 当前 manager 是平台控制平面，不是 seller 算力节点
- 当前 manager 标签：
  - `platform.managed=true`
  - `platform.role=control-plane`
  - `platform.control_plane=true`
  - `platform.compute_enabled=false`
  - `platform.manager_addr=192.168.2.208`

### 当前拓扑

- manager 上固定运行业务 stack：`backend`、`db`、`redis`、`worker`
- 本机已经有一个模拟 seller worker：`seller-local-001`
- benchmark 验证栈当前独立存在，不混入业务 stack
- 本机 seller worker 的创建和移除已有独立脚本
- Portainer 已可查看当前节点、业务服务和 benchmark 服务状态
- 本地 Registry 已可分发业务镜像和 benchmark worker 镜像

### 当前联调资源

- Registry：`192.168.2.208:5000`
- Swarm 当前已经可用于本机真实联调
- 当前阶段的真实联调目录是 `Docker_swarm/`
- benchmark 验证栈：`Docker_swarm/compose.benchmark.yml`
- benchmark worker 镜像定义：`Docker_swarm/benchmark_worker/Dockerfile`
- benchmark stub：`Docker_swarm/benchmark_worker/benchmark_stub.py`
- 本机 seller worker 脚本：
  - `Docker_swarm/scripts/create-local-seller-node.sh`
  - `Docker_swarm/scripts/remove-local-seller-node.sh`

## 当前任务包：Swarm Adapter

### 任务目标

`Swarm Adapter` 是所有 Docker Swarm 操作的唯一后端入口。

当前这轮的目标不是一次性把所有 runtime、benchmark、pricing 都做完，而是先把“后端真实接上当前 Docker Swarm”这条主线拆细、做实、做成可复现的后端能力。

## 分步执行顺序

### 任务 1：理解 Docker 与 Docker Swarm

- 搞清 Docker 与 Docker Swarm 的区别
- 搞清 `manager`、`worker`、`service`、`stack`、`overlay network`、`node label`
- 搞清当前 manager 与 `seller-local-001` 的职责边界
- 搞清哪些节点可以安全操作，哪些节点必须保护

### 任务 2：理解当前后端并补最小健康检查接口

- 理解当前 FastAPI route、config、tests 与 `swarm_adapter` stub 基线
- 保持并明确最小后端健康检查接口：`GET /api/v1/health`
- 新增或明确最小 Swarm 连通性检查接口：`GET /api/v1/swarm/health`

### 任务 3：先通过命令行完成最小真实 Swarm 操作

- 读取 worker join token
- 生成或确认 worker join command
- 列出当前 Swarm 节点
- inspect 当前 manager 和当前 seller worker
- 读取节点 `availability`、`ready/down`、控制面标签

### 任务 4：让后端真实调用 Docker Swarm 命令

- `backend` 容器具备 `docker` CLI
- `backend` 容器可访问 manager 上的 Docker socket
- 后端能真实执行最小只读命令
- 写操作必须带安全前置检查
- 现有 stub 测试路径不能被打碎

### 任务 5：封装标准的后端原语

当前这轮只封装节点控制面最小原语：

- `get_join_token()`
- `build_worker_join_command()`
- `list_swarm_nodes()`
- `inspect_swarm_node()`
- `inspect_swarm_node_by_id()`
- `get_node_hardware_info()`
- `claim_swarm_node_labels()`
- `set_node_availability()`

### 任务 6：通过简单原语排列组合完成复杂操作

- 节点接入链路：
  `get_join_token + build_worker_join_command + inspect_swarm_node + claim_swarm_node_labels`
- 节点维护链路：
  `inspect_swarm_node + set_node_availability`

### 任务 7：扩到完整节点生命周期操作

- 把 `remove_swarm_node()` 纳回正式范围
- 明确“接入节点、查看节点状态、维护节点、删除节点”的完整后端责任边界
- 删除动作必须先检查节点状态、availability、是否仍承载平台 workload，以及是否满足安全移除前提

### 任务 8：完成主文档要求的真实操作与验收

- 读取当前 manager 的 worker join token
- 生成真实 worker join command
- 查看当前 Swarm 节点列表
- inspect 当前 manager 和当前 seller worker
- 查看节点 `availability`、`ready/down`、标签、硬件观测值
- 接入一个新节点，或完整复演一次新节点接入链路
- 对新接入节点完成认领与状态检查
- 在满足安全条件时完成节点删除链路，或完整跑通删除前的所有后端调用与验证

## 当前明确不做

- `Pricing` 的任何实现工作
- `AI Benchmark` 的任何实现工作
- runtime service 原语真实现
- benchmark service 原语真实现
- 完整 seller onboarding 业务
- 完整订单业务
- 完整 reconcile 闭环

## 当前总完成标准

当前这轮只以“后端真实接上 Docker Swarm”作为完成标准。

至少要满足：

- 当前任务已经被拆成可逐步执行的小任务
- 最小后端健康检查接口清楚
- 最小 CLI 真实链路清楚
- backend 具备执行 Docker Swarm 命令的前提
- 节点控制面最小原语已经收口成正式后端接口
- 简单原语可以组合成节点接入与节点维护链路
- 节点生命周期操作已经扩到接入、查看、维护、删除
- 文档里要求的关键节点操作已经完成真实验收或达到诚实可验证停点

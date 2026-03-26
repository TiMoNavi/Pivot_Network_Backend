# Swarm Adapter 进度

## 当前阶段

截至 `2026-03-24`，Phase 1 已经从“协作与规划已建立，但真实 Swarm 接入尚未开始”推进到“第一个只读 Swarm adapter 切片已落地并完成验收基线”。

## 当前已完成

- 保留原有 `GET /api/v1/health`，没有改坏基础健康检查。
- 新增真实 `GET /api/v1/swarm/health`。
- adapter 通过 Docker CLI 执行 `docker info --format '{{json .Swarm}}'`，不是伪造响应。
- adapter 不可用时，接口按约定返回 `503` 与错误详情。
- `backend/tests` 已经是 `9/9` 绿色；其中 `backend/tests/core/test_config.py` 已修成 hermetic。
- compose/runtime 验证包含：
  - backend 镜像在 Dockerfile 变更后先重建；
  - 对运行中的 backend 容器做 live HTTP `GET /api/v1/health`；
  - 对运行中的 backend 容器做 live HTTP `GET /api/v1/swarm/health`；
  - 运行时检查清理后，`docker compose ps backend` 为空。

## 8 步主线状态

- 任务 1：已验证验收基线中的 Docker Desktop / WSL2 与 Swarm 拓扑记录。
- 任务 2：已完成，最小后端骨架与 `GET /api/v1/health` 保持可用。
- 任务 3：已完成最小只读 CLI 链路验证。
- 任务 4：已完成首个 backend 兼容口：`GET /api/v1/swarm/health`。
- 任务 5：未开始。节点控制原语还没有进入实现。
- 任务 6：未开始。节点接入与维护链路还没有开始。
- 任务 7：未开始。完整节点生命周期与安全移除前检查还没有开始。
- 任务 8：部分完成。已完成首个只读验收切片，但还没有进入真实写操作验收。

## 当前诚实停点

- 当前只打通了一个读路径，用于确认 backend 可以真实碰到 Docker Swarm。
- 还没有服务部署、节点变更、节点标签管理、节点上下线等控制面原语。
- 根目录 `tests/` 在当前 Windows runtime 下仍因 Linux 路径与 shell 假设失败；这属于仓库级历史兼容问题，不是当前 Swarm adapter 切片的完成标准。

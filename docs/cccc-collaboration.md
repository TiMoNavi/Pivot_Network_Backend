# CCCC 协作配置

## 当前主线

这个仓库当前只激活一条主线：`后端真实接上 Docker Swarm`。

这套协作配置按官方 `0.4.7` 的 working group 思路建立，不再回退到旧的 `POR / SUBPOR / FOREMAN_TASK` 文档树。

项目级协作模板放在 `CCCC/templates/pivot-backend-build-team.group-template.yaml`，启动入口仍然是：

- `CCCC/cccc-start.sh`
- `CCCC/cccc-status.sh`
- `CCCC/cccc-stop.sh`

## 任务规划

当前任务拆分直接沿用备份蓝图里的 8 步主线：

1. 理解 Docker 与 Docker Swarm、manager/worker、label 与当前拓扑。
2. 理解当前后端骨架，保住最小健康检查接口。
3. 先通过 CLI 跑通最小真实 Swarm 只读链路。
4. 让 backend 具备真实调用 Docker Swarm 命令的前提。
5. 封装节点控制面的最小后端原语。
6. 用简单原语组合出节点接入与维护链路。
7. 扩到完整节点生命周期，包括安全删除链路。
8. 做真实操作验收，或停在诚实可验证的停点。

## Agent 划分

- `lead`
  作为第一个 actor 自动承担 `foreman` 角色，负责控范围、拆任务、看集成质量和最终验收。
- `swarm_cli`
  负责 Docker Swarm 拓扑理解、CLI 证据、安全前置检查和节点状态核查。
- `backend_adapter`
  负责 FastAPI、Swarm Adapter、接口与原语实现。
- `verification`
  负责回归测试、命令验证、真实停点与风险说明。
- `docs_summary`
  负责更新 `docs/current-status.md` 和 `docs/swarm-adapter-progress.md`，同步当前阶段、关键验证结果与真实进展。

## 当前约束

- 不混入 `Pricing` 和 `AI Benchmark` 的实现工作。
- 不动 `future_task_packages/`。
- 不动 `Docker_swarm/` 里的现有联调资产。
- 不动 `docs/project_backups/2026-03-24-project-8step-blueprint.md`。

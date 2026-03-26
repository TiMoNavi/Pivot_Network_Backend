# 当前项目情况

## 当前结论

当前仓库已经不再是“只有空骨架、还没有任何真实 Swarm 后端原语”的状态。

截至 `2026-03-24` 的 Phase 1 验收基线，仓库已经落下第一个真实、可验证的 backend adapter 切片：

- `GET /api/v1/health` 保持不变，仍然是基础服务健康检查。
- backend 新增 `GET /api/v1/swarm/health`，由 backend 内部通过 Docker CLI 真实执行 `docker info --format '{{json .Swarm}}'`。
- `backend/tests` 现为 `9/9` 通过；`backend/tests/core/test_config.py` 已通过 `monkeypatch.delenv` 做成对宿主环境变量不敏感的 hermetic 测试。
- compose/runtime 验证在 backend 镜像完成 Dockerfile 相关变更后做了重建，并对运行中的 backend 容器完成了 live HTTP `GET /api/v1/health` 与 `GET /api/v1/swarm/health`。
- runtime 检查清理后，`docker compose ps backend` 为空。

## 已验证的 Phase 1 范围

- 当前唯一主线仍然是“让 AI 真实操作 Docker Swarm，并在 backend 里做兼容口 / adapter”。
- 本轮已经验证的最小兼容口是只读 Swarm 健康接口，不涉及节点写操作、服务编排写操作或业务流程。
- 验收基线记录的 Docker 环境是 Docker Desktop / WSL2；在该次验收检查里，Swarm 状态记录为单节点 active manager，且没有已部署 services / stacks。

## 当前还没有做的内容

- 没有进入 Pricing、AI Benchmark、订单、支付、完整 seller onboarding 等 Phase 2 范围。
- 没有开始节点生命周期写操作、服务部署编排、节点安全移除前检查等后续步骤。
- 没有把 backend 扩展成完整业务后端；当前只是先建立一个真实可调用的 Swarm adapter 起点。

## 诚实停点

- Phase 1 目前只完成了第一个只读 Swarm 健康接口切片。
- 根目录测试仍不是绿色：在当前 Windows runtime 下，`pytest tests -q` 仍会因 `tests/test_cccc_layout.py` 中硬编码的 Linux 路径与 shell 假设失败。
- 上述根目录失败不属于这次 Swarm adapter 切片的修复范围，也不影响 `backend/tests` 的 `9/9` 通过结论。

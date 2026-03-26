# Backend Skeleton

这是一个最小后端骨架，保留：

- `FastAPI`
- `SQLAlchemy 2`
- `Alembic`
- `Celery`

当前只保留框架，不保留历史业务模块。

## Quick Start

```bash
cd /home/cw/ybj/Pivot_backend_build_team/backend
uv sync
uv run uvicorn app.main:app --reload
```

健康检查：

- `GET /api/v1/health`

当前额外提供的平台 bootstrap 接口：

- `GET /api/v1/platform/runtime/codex`
- `POST /api/v1/platform/nodes/wireguard/bootstrap`
- `GET /api/v1/platform/swarm/worker-join-token`
- `GET /api/v1/platform/swarm/overview`

如果后端配置了：

- `WIREGUARD_SERVER_SSH_ENABLED=true`
- `WIREGUARD_SERVER_SSH_HOST`
- `WIREGUARD_SERVER_SSH_USER`
- `WIREGUARD_SERVER_SSH_PASSWORD` 或 `WIREGUARD_SERVER_SSH_KEY_PATH`

那么 `POST /api/v1/platform/nodes/wireguard/bootstrap` 不只会返回 profile，还会通过 SSH 自动把 peer 写入服务器侧 `wg0`。

## Backend-only CodeX Auth

如果要让平台后端向 seller-Agent 下发 CodeX/OpenAI runtime 配置，推荐只在后端保存认证材料。

支持两种来源：

1. 环境变量 `OPENAI_API_KEY`
2. `backend/.codex/auth.json`

`backend/.codex/auth.json` 格式：

```json
{
  "OPENAI_API_KEY": "replace-with-backend-only-key"
}
```

该目录已经在仓库 `.gitignore` 中忽略，不应提交到仓库。

## Tests

```bash
cd /home/cw/ybj/Pivot_backend_build_team/backend
uv run pytest
```

## Migrations

```bash
cd /home/cw/ybj/Pivot_backend_build_team/backend
uv run alembic upgrade head
```

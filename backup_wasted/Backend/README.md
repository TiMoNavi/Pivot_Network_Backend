# Pivot Platform Backend

`Backend/` 是 Pivot Network 当前的平台后端实现目录。它已经不是通用 scaffold，而是一个真实接入 `PostgreSQL` 和 `Docker Swarm Adapter` 的 `FastAPI` 服务。

当前系统主链路是：

```text
seller-client / buyer-client / platform UI
                |
                v
        Pivot Platform Backend
                |
                v
      Docker Swarm Adapter
                |
                v
      Docker Swarm / WireGuard
```

默认原则：

- 客户端只连 `Backend`
- `Backend` 只通过 HTTP 调 `Adapter`
- 真正操作 `Docker Swarm` / `WireGuard` 的是 `Adapter`

## 当前职责

- 统一的云端入口：为 `seller-client`、`buyer-client`、平台管理端提供 API
- 认证与角色：注册、登录、登出、`buyer / seller / platform_admin` 角色鉴权
- seller 工作流：运行时基础镜像/契约、onboarding session、Windows/Ubuntu 双环境上报、节点接入与 claim、镜像上报
- buyer 工作流：catalog、订单、access code、runtime session、buyer runtime client bootstrap
- 平台运维：overview、Swarm 同步、节点/订单/session 视图、审计与 operation log、maintenance worker
- Adapter 代理：通过 `/api/v1/adapter-proxy/*` 暴露对 Adapter 的受控代理接口

## 当前已实现能力

### `auth`

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`

### `seller`

- `GET /api/v1/seller/runtime-base-images`
- `GET /api/v1/seller/runtime-contract`
- `POST /api/v1/seller/onboarding/sessions`
- `GET /api/v1/seller/onboarding/sessions/{session_id}`
- `GET /api/v1/seller/onboarding/sessions/{session_id}/bootstrap-config`
- `GET /api/v1/seller/onboarding/sessions/{session_id}/ubuntu-bootstrap`
- `POST /api/v1/seller/onboarding/sessions/{session_id}/env-report`
- `POST /api/v1/seller/onboarding/sessions/{session_id}/host-env-report`
- `POST /api/v1/seller/onboarding/sessions/{session_id}/ubuntu-env-report`
- `POST /api/v1/seller/onboarding/sessions/{session_id}/compute-ready`
- `POST /api/v1/seller/onboarding/sessions/{session_id}/heartbeat`
- `POST /api/v1/seller/onboarding/sessions/{session_id}/close`
- `POST /api/v1/seller/nodes/register`
- `GET /api/v1/seller/nodes`
- `GET /api/v1/seller/nodes/{node_id}`
- `GET /api/v1/seller/nodes/{node_id}/claim-status`
- `POST /api/v1/seller/nodes/{node_id}/claim`
- `POST /api/v1/seller/images/report`
- `GET /api/v1/seller/images`
- `GET /api/v1/seller/offers`

### `buyer`

- `GET /api/v1/buyer/catalog/offers`
- `POST /api/v1/buyer/orders`
- `GET /api/v1/buyer/orders/{order_id}`
- `POST /api/v1/buyer/access-codes/redeem`
- `POST /api/v1/buyer/runtime-sessions`
- `GET /api/v1/buyer/runtime-sessions/{session_id}`
- `POST /api/v1/buyer/runtime-sessions/{session_id}/connect-material`
- `POST /api/v1/buyer/runtime-sessions/{session_id}/stop`
- `GET /api/v1/buyer/runtime-sessions/{session_id}/bootstrap-config`
- `GET /api/v1/buyer/runtime-sessions/{session_id}/client-session`
- `POST /api/v1/buyer/runtime-sessions/{session_id}/env-report`
- `POST /api/v1/buyer/runtime-sessions/{session_id}/heartbeat`
- `POST /api/v1/buyer/runtime-sessions/{session_id}/close`

### `platform`

- `GET /api/v1/platform/overview`
- `GET /api/v1/platform/swarm/overview`
- `POST /api/v1/platform/swarm/sync`
- `GET /api/v1/platform/nodes`
- `GET /api/v1/platform/nodes/{node_id}`
- `GET /api/v1/platform/activity`
- `GET /api/v1/platform/orders`
- `GET /api/v1/platform/runtime-sessions`
- `GET /api/v1/platform/runtime-sessions/{session_id}`
- `POST /api/v1/platform/runtime-sessions/{session_id}/refresh`
- `GET /api/v1/platform/operation-logs`
- `POST /api/v1/platform/maintenance/runtime-refresh`
- `POST /api/v1/platform/maintenance/runtime-reaper`
- `POST /api/v1/platform/maintenance/access-code-reaper`

### `adapter-proxy`

当前已代理的能力包括：

- `swarm overview / nodes / inspect / join-material / claim / availability / remove`
- `runtime image validate`
- `node probe`
- `service inspect`
- `runtime-session-bundle create / inspect / remove`
- `wireguard peer apply / remove`

## 目录结构

```text
Backend/
├── alembic/
├── backend_app/
│   ├── api/
│   ├── clients/
│   ├── core/
│   ├── db/
│   ├── repositories/
│   ├── schemas/
│   ├── services/
│   ├── workers/
│   └── main.py
├── compose.yml
├── docs/
├── pyproject.toml
└── tests/
```

## 本机启动

推荐先准备 `.env`：

```bash
cd /root/Pivot_network/Backend
cp .env.example .env
```

然后本机启动：

```bash
cd /root/Pivot_network/Backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
docker compose up -d postgres
alembic upgrade head
python -m uvicorn backend_app.main:app --host 0.0.0.0 --port 8000
```

启动后：

- 根路径：`http://localhost:8000/`
- Swagger：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/api/v1/health`
- 就绪检查：`http://localhost:8000/api/v1/ready`

## Docker Compose 启动

如果要连同 PostgreSQL 一起起服务：

```bash
cd /root/Pivot_network/Backend
cp .env.example .env
docker compose up --build
```

`compose.yml` 会自动执行：

- `alembic upgrade head`
- `uvicorn backend_app.main:app --host 0.0.0.0 --port 8000 --reload`

注意：

- `Backend` 本身仍依赖可达的 `Docker Swarm Adapter`
- `BACKEND_ADAPTER_BASE_URL` 和 `BACKEND_ADAPTER_TOKEN` 必须正确

## 数据库迁移

当前 Alembic 迁移已经到：

- `0007_buyer_client`

常用命令：

```bash
alembic current
alembic upgrade head
```

## 关键环境变量

完整列表见 [`.env.example`](.env.example)。

最常用的几组配置是：

### 基础服务

- `BACKEND_POSTGRES_*`
- `BACKEND_ADAPTER_BASE_URL`
- `BACKEND_ADAPTER_TOKEN`
- `BACKEND_SESSION_TOKEN_TTL_HOURS`

### seller onboarding / Codex

- `BACKEND_SELLER_CODEX_OPENAI_API_KEY`
- `BACKEND_SELLER_CODEX_MODEL`
- `BACKEND_SELLER_CODEX_REVIEW_MODEL`
- `BACKEND_SELLER_CODEX_BASE_URL`
- `BACKEND_SELLER_CODEX_MCP_SERVER_NAME`

如果这个 API key 没配好，`GET /api/v1/seller/onboarding/sessions/{id}/bootstrap-config` 会返回配置缺失错误。

### seller Ubuntu compute policy

- `BACKEND_SELLER_COMPUTE_SUBSTRATE`
- `BACKEND_SELLER_COMPUTE_HOST_TYPE`
- `BACKEND_SELLER_COMPUTE_NETWORK_MODE`
- `BACKEND_SELLER_COMPUTE_RUNTIME`
- `BACKEND_SELLER_COMPUTE_UBUNTU_*`
- `BACKEND_SELLER_COMPUTE_WIREGUARD_*`
- `BACKEND_SELLER_COMPUTE_SWARM_*`

这组配置决定后端下发给 `seller-client` 的 Ubuntu bootstrap 策略。

### buyer runtime client

- `BACKEND_BUYER_RUNTIME_CLIENT_SESSION_TTL_MINUTES`
- `BACKEND_BUYER_WORKSPACE_SYNC_MAX_MB`
- `BACKEND_BUYER_RUNTIME_WORKSPACE_ROOT`
- `BACKEND_BUYER_SHELL_EMBED_PATH`
- `BACKEND_BUYER_WORKSPACE_UPLOAD_PATH`
- `BACKEND_BUYER_WORKSPACE_EXTRACT_PATH`
- `BACKEND_BUYER_WORKSPACE_STATUS_PATH`
- `BACKEND_BUYER_CODEX_*`

### worker / maintenance

- `BACKEND_ENABLE_BUILTIN_WORKERS`
- `BACKEND_RUNTIME_REFRESH_STALE_AFTER_MINUTES`
- `BACKEND_RUNTIME_REFRESH_INTERVAL_SECONDS`
- `BACKEND_RUNTIME_REAPER_INTERVAL_SECONDS`
- `BACKEND_ACCESS_CODE_REAPER_INTERVAL_SECONDS`
- `BACKEND_MAINTENANCE_BATCH_LIMIT`

默认情况下内建 worker 不会自动启动；可以通过 platform maintenance API 手动触发，或者显式开启内建 worker。

## 测试

仓库内目前已有的后端测试覆盖了：

- 健康检查
- seller onboarding 主流程
- buyer runtime client 路由覆盖

可直接运行：

```bash
cd /root/Pivot_network/Backend
pytest tests/test_health.py tests/test_seller_onboarding.py tests/test_buyer_runtime_client.py
```

## 当前状态与注意事项

- seller onboarding 的正式目标架构已经切到 `Windows 控制台 + WSL Ubuntu compute`
- buyer runtime client bootstrap 已经落地到后端 API 与数据库迁移
- 内建 worker 已实现，但默认关闭
- 写操作会通过 Adapter 影响真实 `Swarm / WireGuard`，联调前请确认目标环境
- 当前更适合“可运行原型 / 内部联调环境”，生产发布前仍需要补齐 secret、权限、异常恢复和安全加固

## 相关文档

- [docs/backend-adapter-client-interface-map.md](docs/backend-adapter-client-interface-map.md)
- [docs/backend-assessment-2026-04-05.md](docs/backend-assessment-2026-04-05.md)
- [docs/windows-console-wsl-ubuntu-compute-migration.md](docs/windows-console-wsl-ubuntu-compute-migration.md)
- [docs/windows-wsl-ubuntu-compute-implementation.md](docs/windows-wsl-ubuntu-compute-implementation.md)

# 启动手册

## 怎么选路径

- 如果你要验证当前这套 `Docker_swarm/` 资产、单机 manager、或者后续多节点接入，请看 `01_Docker Swarm 如何启动`。
- 这条路线默认面向 Linux 或 WSL 里的 `bash` 环境，不是原生 PowerShell 等价路径。
- 如果你要在 Windows 上把当前后端和依赖一起跑起来，做本地开发、接口联调或健康检查，请看 `02_后端如何启动`。
- Windows 日常开发默认走 `docker compose`，本地启动集现在包含 `db`、`redis`、`backend`、`worker`、`registry`、`portainer`。
- 这两条路径不是同一件事。`Swarm` 是现有联调资产，`后端启动` 是当前仓库默认本地开发路径。

## 01_Docker Swarm 如何启动

### 适用场景

- 适合 Linux 主机，或者已经装好 Docker CLI 的 WSL `bash` 环境。
- 适合验证当前仓库保留的 `Docker_swarm/` 资产。
- 不适合直接在原生 PowerShell 里照抄执行，因为现有脚本依赖 `bash`、`/etc/docker/daemon.json`、`systemctl`、`nsenter`、`/:/host` 这类 Linux 语义。

### 前置条件

- Docker daemon 已启动，并且 `docker info` 能正常返回。
- 仓库根目录已经有 `.env` 文件；当前脚本默认读取仓库根目录 `.env`。
- 你知道当前 manager 机器可被其他节点访问的 LAN IP。
- 如果你在 WSL 里执行，请确认 WSL 里的 Docker CLI 已经能连接到 Docker Desktop 或 Linux Docker daemon。

### 启动顺序

在 Linux 或 WSL 的 `bash` 里执行：

```bash
cd Docker_swarm
./scripts/init-manager.sh <manager_lan_ip>
./scripts/configure-registry-access.sh <registry_host>
./scripts/build-backend-image.sh
./scripts/deploy-app-stack.sh
./scripts/run-prestart.sh
```

命令说明：

- `./scripts/init-manager.sh <manager_lan_ip>`
  初始化单机 Swarm manager；如果当前机器已经是 active manager，会直接返回当前 manager 地址。
- `./scripts/configure-registry-access.sh <registry_host>`
  把 Docker daemon 配成信任 manager 本地 registry。
- `./scripts/build-backend-image.sh`
  构建后端镜像并推送到本地 registry。
- `./scripts/deploy-app-stack.sh`
  用 [`Docker_swarm/compose.swarm.yml`](../Docker_swarm/compose.swarm.yml) 部署 `backend`、`db`、`redis`、`worker`。
- `./scripts/run-prestart.sh`
  尝试在 stack 网络里执行 prestart / migration / initial data 流程。

### 可选步骤

只有在你需要这些能力时再执行：

```bash
./scripts/deploy-portainer.sh
./scripts/label-control-plane.sh self <manager_lan_ip>
./scripts/build-benchmark-image.sh
./scripts/create-local-seller-node.sh
./scripts/deploy-benchmark-stack.sh
```

### 验证命令

```bash
cd Docker_swarm
./scripts/status.sh
docker node ls
docker stack services pivot-backend-build-team
curl http://<manager_lan_ip>:8000/api/v1/health
```

如果你启用了可选 stack，还可以继续看：

```bash
docker stack services portainer
docker stack services pivot-benchmark
```

### 停止与清理

按需清理，不必一次性全部删掉：

```bash
docker stack rm pivot-benchmark
docker stack rm portainer
docker stack rm pivot-backend-build-team
./scripts/remove-local-seller-node.sh
```

补充说明：

- `registry` 不是 stack 服务，而是脚本按需拉起的独立容器；如果你后面还要继续联调，可以先保留。
- `Portainer` 也是按需组件；只做最小后端联调时可以不启动。
- seller 验证节点只在你需要验证 worker join、label、benchmark 调度时再保留。

### 低内存建议

- 默认只启动业务 stack，也就是 `backend`、`db`、`redis`、`worker`。
- `Portainer`、`benchmark`、本地 seller worker 都按需启动，不要默认常驻。
- 当前编排已经做了最基本的低占用约束：
  `backend` 使用 `--workers 1`
  `worker` 使用 `--pool=solo --concurrency=1`
- 如果你只是想把 API 跑起来，不建议先走整套 Swarm。

### 诚实限制

- 当前仓库的 Swarm 资产是“原始联调路径”，不是已经在 Windows 上整理过的默认开发路径。
- [`Docker_swarm/scripts/run-prestart.sh`](../Docker_swarm/scripts/run-prestart.sh) 当前会尝试执行 `app.backend_pre_start` 和 `app.initial_data`，但仓库里目前没有找到这两个 Python 入口。
- 这意味着前面的 `init-manager`、`build-backend-image`、`deploy-app-stack` 仍然有参考价值，但 `run-prestart.sh` 在当前空壳仓库里可能成为诚实停点。
- 如果你的目标只是“先跑后端”，请直接跳到 `02_后端如何启动`。

### 常见问题

- `docker info` 报错或连不上 daemon：
  先确认 Docker Desktop 或 Docker Engine 已启动。
- Swarm 不是 `active`：
  先执行 `./scripts/init-manager.sh <manager_lan_ip>`。
- registry 不可信，镜像拉取失败：
  先执行 `./scripts/configure-registry-access.sh <registry_host>`，再重新部署。
- Windows 直接执行 `./scripts/*.sh` 失败：
  这是因为这些脚本按 Linux / WSL `bash` 写的，不是 PowerShell 原生脚本。

## 02_后端如何启动

### A. 本地 Python 启动

适用场景：

- 你想最快把当前后端代码跑起来。
- 你在做本地开发、接口调试、最小健康检查。
- 你不依赖容器内的 `Postgres`、`Redis`、`Portainer`、`registry`。

启动命令：

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

健康检查：

- 打开 `http://localhost:8000/api/v1/health`

测试验证：

在仓库根目录另开一个终端执行：

```bash
python -m pytest backend/tests -q
```

停止方式：

- 当前终端按 `Ctrl+C`

说明：

- 配置现在会稳定读取仓库根目录 `.env`。
- 如果根目录 `.env` 提供了 `POSTGRES_*`，应用会优先推导出 `postgresql+psycopg://...` 的 `DATABASE_URL`。
- 只做纯本地 Python 调试时，如果你不想依赖容器内 `Postgres`，可以显式覆盖：

```bash
DATABASE_URL=sqlite:///./pivot_backend.db uv run uvicorn app.main:app --reload
```

- 当前仓库的最小健康检查接口是 `GET /api/v1/health`。

### B. Docker Compose 启动

适用场景：

- 你在 Windows 上已经有 Docker Desktop。
- 你希望用容器跑 `db`、`redis`、`backend`、`worker`，并把 `registry` 和 `portainer` 一起带起来。
- 你不需要同时把整套 Swarm 常驻起来。

前置条件：

- 仓库根目录 `.env` 已存在。
- Docker daemon 已启动。
- 建议先配置 `C:\Users\Administrator\.wslconfig`：

```ini
[wsl2]
memory=4GB
swap=1GB
```

- 修改后执行一次 `wsl --shutdown`，再重启 Docker Desktop。

启动命令：

在仓库根目录执行：

```bash
docker compose up --build
```

验证命令：

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f worker
docker compose exec db pg_isready -U postgres -d pivot_backend
```

健康检查：

- 打开 `http://localhost:8000/api/v1/health`
- 打开 `https://localhost:9443`
- 打开 `http://localhost:5000/v2/_catalog`

停止方式：

```bash
docker compose down -v
```

诚实说明：

- 当前 [`compose.yml`](../compose.yml) 会默认启动 `db`、`redis`、`backend`、`worker`、`registry`、`portainer`。
- 配置层会优先读取显式 `DATABASE_URL`、`CELERY_BROKER_URL`、`CELERY_RESULT_BACKEND`，未提供时再从 `POSTGRES_*` 和 `REDIS_URL` 推导。
- 本地 `Portainer` 入口默认是 `https://localhost:9443`。
- 本地 `registry` 入口默认是 `http://localhost:5000/v2/_catalog`。

## 当前推荐

- Windows 日常开发优先使用 `B. Docker Compose 启动`；只有在你明确不需要容器依赖时，再使用 `A. 本地 Python 启动`。
- `Docker Swarm` 保留给 Linux / WSL 下的联调、单机 manager 验证和后续多节点验证。
- 如果只是要验证当前仓库最小可运行状态，先看 `http://localhost:8000/api/v1/health` 是否返回 `200`。

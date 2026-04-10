# Managed Runtime Test Image

这个测试镜像用于本地验证：

- `runtime-images/validate`
- `runtime-session-bundles/create`
- `runtime-session-bundles/inspect`
- `runtime-session-bundles/remove`

它满足当前 MVP 的最小契约：

- 带 `io.pivot.runtime.base_image`
- 带 `io.pivot.runtime.contract_version=v1`
- 带 `io.pivot.runtime.buyer_agent=v1`
- 提供 `/usr/local/bin/pivot-shell-agent`
- 在 `7681` 暴露一个最小 HTTP 服务

当前测试 shell-agent 额外提供：

- `GET /health`
- `GET /shell/`
- `POST /api/exec`
- `POST /api/workspace/upload`
- `POST /api/workspace/extract`
- `GET /api/workspace/status`

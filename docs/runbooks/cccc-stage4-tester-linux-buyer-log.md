# CCCC Stage4 Tester Linux Buyer Log

更新时间：`2026-04-11 08:35:06 CST` (`2026-04-11 00:35:06 UTC`)

## Scope

- 只服务于 `Stage4`
- 只验证 Linux `Buyer_Client` + MCP 路径
- 当前目标链固定为：
  - `offer_76fff26fa2692634`
  - `order_5d1236d1338ac6ab`
  - `grant_a84b49a685609153`
  - `runtime_session_bd6eab1e6279291f`
- 不进入 `Stage5` 自然语言流
- 不进入 Windows buyer scope

## Current Status

- Stage4 Linux `Buyer_Client` + MCP 真链路已跑到：
  - grant import/pull
  - session create/refresh
  - WireGuard up
  - shell reachability
  - workspace sync
  - minimal task
- 当前唯一剩余异常不在主链路成功本身，而在本地清理回滚返回：
  - `wireguard_down` 报错
  - 但 confirm-only 检查显示：
    - 接口 `pivot-2426388f` 已不存在
    - `10.66.66.1/32` 路由已不存在
  - 所以临时 Linux buyer tunnel 实际上已经清掉

## Verification Ledger

### Action 1: inspect Buyer_Client implementation surface

- Before state:
  - Stage4 backend/support gap 已由 `platform` 关闭
  - 需要先确认 Linux `Buyer_Client` 本地入口是否能启动
- Commands:

```bash
ls -l Buyer_Client/buyer_client_app
find Buyer_Client/buyer_client_app -maxdepth 1 -type f -printf '%f\n' | sort
rg -n "class BuyerClientState|def build_runtime_access_plan|BuyerClientState\(|build_runtime_access_plan\(" Buyer_Client -g '*.py'
```

- After state:
  - `Buyer_Client/buyer_client_app/` 当前存在：
    - `backend.py`
    - `config.py`
    - `errors.py`
    - `flow.py`
    - `main.py`
    - `mcp_fastmcp.py`
    - `mcp_server.py`
    - `session_ops.py`
    - `state.py`
    - `wireguard.py`
    - `workspace.py`
- Rollback:
  - none; read-only inspection
- What this verified:
  - 当前 Linux `Buyer_Client` 源码树已具备 Stage4 所需的主要模块

### Action 2: direct Buyer_Client import/startup check

- Before state:
  - 需要确认本地 Linux `Buyer_Client` 入口和 in-repo MCP server 现在能否真正启动
- Commands:

```bash
cd Buyer_Client && python - <<'PY'
import traceback
try:
    import buyer_client_app.main
    import buyer_client_app.mcp_server
    print('buyer-import-ok')
except Exception:
    traceback.print_exc()
    raise
PY

cd Buyer_Client && timeout 4s python -m uvicorn buyer_client_app.main:app --host 127.0.0.1 --port 8912
```

- After state:
  - direct import now passes:
    - `buyer-import-ok`
  - timed `uvicorn` run reaches:
    - application startup complete
    - clean shutdown after timeout
- Rollback:
  - none; read-only startup check
- What this verified:
  - 当前 Linux `Buyer_Client` 本地入口与 in-repo MCP server 已可导入
  - Stage4 可以进入真实运行态验证

### Action 3: local Buyer_Client auth + grant pull + attach on the real chain

- Before state:
  - 本地 Linux `Buyer_Client` app 已在 `127.0.0.1:8912` 可启动
  - 真实目标链固定为：
    - `order_5d1236d1338ac6ab`
    - `grant_a84b49a685609153`
    - `runtime_session_bd6eab1e6279291f`
- Commands:

```http
POST http://127.0.0.1:8912/local-api/window-session/open
POST http://127.0.0.1:8912/local-api/auth/login
GET  http://127.0.0.1:8912/local-api/auth/me
GET  http://127.0.0.1:8912/local-api/access-grants/active
POST http://127.0.0.1:8912/local-api/runtime/attach-active-grant
GET  http://127.0.0.1:8912/local-api/runtime/current
```

  - login buyer:
    - `stage2-buyer-a341c1804963@example.com`
  - attach exact grant:
    - `grant_a84b49a685609153`
- After state:
  - local window session opened:
    - `session_id = 88c37e65-dd11-4827-bf0e-ab1d66d09d34`
  - login succeeded for buyer:
    - `user_13e35642ec9f9f57`
  - active grants pull returned the real redeemed grant:
    - `grant_id = grant_a84b49a685609153`
    - `grant_code = CDzofnFz7eoFkI6beKoQeTD_JPkNpWf-NqvinDSTBt0`
    - `runtime_session_id = runtime_session_bd6eab1e6279291f`
    - `status = redeemed`
  - attach-active-grant bound local state to:
    - `order_5d1236d1338ac6ab`
    - `grant_a84b49a685609153`
    - `runtime_session_bd6eab1e6279291f`
  - runtime access plan already contains:
    - `status = ready`
    - `network_entry.shell_embed_url = http://10.66.66.1:32080/shell/`
    - `network_entry.workspace_sync_url = http://10.66.66.1:32080/api/workspace/upload`
    - `network_entry.task_exec_url = http://10.66.66.1:32080/api/exec`
    - `wireguard_profile.client_address = 10.66.66.201/32`
- Rollback:
  - local window session can be closed via:

```http
POST http://127.0.0.1:8912/local-api/window-session/close
```

- What this verified:
  - Linux `Buyer_Client` 本地 API 可以登录 buyer、拉取真实 grant，并把本地状态绑定到真实 runtime session 链

### Action 4: Buyer MCP import/pull + session create/refresh on the real chain

- Before state:
  - 本地 API 已经把当前 buyer/grant/order 链绑定到真实会话
- Commands:

```python
from buyer_client_app.mcp_server import _invoke_tool

_invoke_tool("import_grant_code", {"grant_code": "CDzofnFz7eoFkI6beKoQeTD_JPkNpWf-NqvinDSTBt0"})
_invoke_tool("list_active_grants", {})
_invoke_tool("create_runtime_session", {"grant_id": "grant_a84b49a685609153"})
_invoke_tool("refresh_runtime_session", {"runtime_session_id": "runtime_session_bd6eab1e6279291f"})
_invoke_tool("read_runtime_state", {})
```

- After state:
  - MCP `import_grant_code` succeeded
  - MCP `list_active_grants` returned the same real redeemed grant
  - MCP `create_runtime_session` redeemed into:
    - same runtime session id `runtime_session_bd6eab1e6279291f`
    - `status = ready`
    - `runtime_bundle_status = running`
  - MCP `refresh_runtime_session` succeeded on the same session
  - persisted buyer runtime state now includes:
    - runtime session file path
    - generated local WireGuard keypair
    - shell/workspace/task URLs
- Rollback:
  - none yet; local WireGuard tunnel had not been started at this point
- What this verified:
  - in-repo Buyer MCP can import the real grant code, read active grants, and create/refresh the real runtime session on the unchanged Stage3 chain

### Action 5: Linux Buyer_Client wireguard_up on the real chain

- Before state:
  - local runtime state is initialized on:
    - `grant_a84b49a685609153`
    - `runtime_session_bd6eab1e6279291f`
  - generated WireGuard config target path is under:
    - `/tmp/pivot_buyer_client/sessions/runtime_session_bd6eab1e6279291f/wireguard/`
- Command:

```python
from buyer_client_app.mcp_server import _invoke_tool
_invoke_tool("wireguard_up", {})
```

- After state:
  - `wireguard_up` now succeeds on the real chain
  - generated config path:
    - `/tmp/pivot_buyer_client/sessions/runtime_session_bd6eab1e6279291f/wireguard/pivot-2426388f.conf`
  - interface name:
    - `pivot-2426388f`
  - runtime session attached to the tunnel:
    - `runtime_session_bd6eab1e6279291f`
  - command output confirms tunnel setup:
    - `ip link add pivot-2426388f type wireguard`
    - userspace fallback path engaged
    - `ip -4 address add 10.66.66.201/32 dev pivot-2426388f`
    - `ip -4 route add 10.66.66.1/32 dev pivot-2426388f`
- Rollback:
  - planned local rollback was:

```python
from buyer_client_app.mcp_server import _invoke_tool
_invoke_tool("wireguard_down", {})
```
- What this verified:
  - Linux Buyer_Client local WireGuard path now works on the real chain

### Action 6: shell reachability over the Linux Buyer_Client path

- Before state:
  - local WireGuard tunnel is up on:
    - `pivot-2426388f`
  - current runtime session chain remains:
    - `grant_a84b49a685609153`
    - `runtime_session_bd6eab1e6279291f`
- Command:

```python
from buyer_client_app.mcp_server import _invoke_tool
_invoke_tool("open_shell", {})
```

- After state:
  - shell open returned:
    - `runtime_session_id = runtime_session_bd6eab1e6279291f`
    - `shell_embed_url = http://10.66.66.1:32080/shell/`
  - returned `wireguard_state.status = up`
  - returned `wireguard_state.interface_name = pivot-2426388f`
- Rollback:
  - same local tunnel teardown path as Action 5
- What this verified:
  - Linux Buyer_Client can resolve the real shell entrypoint through the live WireGuard-backed runtime plan

### Action 7: workspace sync on the Linux Buyer_Client path

- Before state:
  - local test workspace prepared at:
    - `/tmp/pivot_stage4_workspace`
  - files:
    - `README.txt`
    - `demo.py`
- Command:

```python
from buyer_client_app.mcp_server import _invoke_tool
_invoke_tool("sync_workspace", {"path": "/tmp/pivot_stage4_workspace"})
_invoke_tool("read_workspace_status", {})
```

- After state:
  - local packaged archive:
    - `/tmp/pivot-buyer-workspace-urryswlc/workspace.zip`
  - upload succeeded:
    - `archive_path = /tmp/pivot-workspace-spf7jv5x/workspace.zip`
  - extract succeeded:
    - `workspace_root = /workspace`
  - workspace status returned the synced files:
    - `demo.py`
    - `README.txt`
- Rollback:
  - no destructive runtime cleanup was exposed through current local API
  - workspace evidence remains confined to the real runtime session chain
- What this verified:
  - Linux Buyer_Client + MCP can package and sync a local workspace into the real runtime session

### Action 8: minimal task flow on the Linux Buyer_Client path

- Before state:
  - runtime session remains:
    - `runtime_session_bd6eab1e6279291f`
  - workspace has already been synced to `/workspace`
- Command:

```python
from buyer_client_app.mcp_server import _invoke_tool
task = _invoke_tool("submit_task_execution", {"command": "echo stage4-ok && pwd && ls -1"})
_invoke_tool("tail_task_logs", {"task_id": task["id"]})
```

- After state:
  - task record id:
    - `d4121dce-fd1c-4db5-befb-f4e4b76725e2`
  - task status:
    - `succeeded`
  - `exit_code = 0`
  - remote stdout:
    - `stage4-ok`
    - `/workspace`
    - `README.txt`
    - `demo.py`
  - remote stderr:
    - empty
  - local logs written:
    - `/tmp/pivot_buyer_client/sessions/runtime_session_bd6eab1e6279291f/logs/d4121dce-fd1c-4db5-befb-f4e4b76725e2.stdout.log`
    - `/tmp/pivot_buyer_client/sessions/runtime_session_bd6eab1e6279291f/logs/d4121dce-fd1c-4db5-befb-f4e4b76725e2.stderr.log`
- Rollback:
  - no runtime stop/close was used
  - task evidence remains on the same runtime session chain
- What this verified:
  - Linux Buyer_Client + MCP can submit and observe one minimal task on the real runtime session

### Action 9: local tunnel teardown / rollback check

- Before state:
  - local WireGuard interface:
    - `pivot-2426388f`
  - route was installed for:
    - `10.66.66.1/32`
- Command:

```python
from buyer_client_app.mcp_server import _invoke_tool
_invoke_tool("wireguard_down", {})
```

  - confirm-only checks after the error:

```bash
ip link show pivot-2426388f
ip route show | rg '10\.66\.66\.1/32|pivot-2426388f'
```

- After state:
  - `wireguard_down` returned a local error:
    - `wg-quick down` failed
    - stderr:
      - `wg-quick: 'pivot-2426388f' is not a WireGuard interface`
  - but confirm-only checks show cleanup effectively completed:
    - `ip link show pivot-2426388f` -> device does not exist
    - route check shows no remaining `10.66.66.1/32` route via that interface
- Rollback:
  - local temporary buyer tunnel state is effectively absent after the failed-return path
  - grant/runtime session chain unchanged
- What this verified:
  - Stage4 forward path evidence is intact
  - only residual issue is a local teardown false-negative, not a failure of the real Linux Buyer_Client forward path

## Result

- Verified on the real Stage4 chain:
  - Linux `Buyer_Client` imports and starts
  - local auth/login works
  - real grant pull works
  - real grant import works
  - real runtime session create/refresh works
  - shell reachability works through the Linux Buyer_Client path
  - workspace sync works through the Linux Buyer_Client path
  - one minimal task works through the Linux Buyer_Client path
- Exact real chain used throughout:
  - `grant_a84b49a685609153`
  - `runtime_session_bd6eab1e6279291f`
- Residual issue:
  - local `wireguard_down` teardown returns a false-negative even though the interface and route are actually gone

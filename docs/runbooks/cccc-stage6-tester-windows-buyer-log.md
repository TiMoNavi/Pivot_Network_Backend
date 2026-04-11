# CCCC Stage6 Tester Windows Buyer Log

更新时间：`2026-04-11 09:20:30 CST` (`2026-04-11 01:20:30 UTC`)

## Scope

- 只服务于 `Stage6`
- 只验证 Windows-local `Buyer_Client` 路径
- 当前目标链固定为：
  - `order_5d1236d1338ac6ab`
  - `grant_a84b49a685609153`
  - `runtime_session_bd6eab1e6279291f`
- `reverse SSH / WG` 只作为 operator access，用于 deployment / diagnostics / verification
- 不把 operator reachability 写成产品成功

## Verification Ledger

### Action 1: Windows-local Buyer_Client staging and startup surface

- Before state:
  - 需要确认 Windows 本地 buyer app 是否真的 staged 并启动，而不是只停留在 repo 对齐
- Commands:

```bash
ssh win-local-via-reverse-ssh "powershell -NoProfile -Command \"Test-Path 'D:\AI\Pivot_Client\buyer_client'; Test-Path 'D:\AI\Pivot_Client\buyer_client\bootstrap\windows\start_buyer_client.ps1'; Get-Command wireguard.exe -ErrorAction SilentlyContinue | Select-Object Source; Get-Command wg.exe -ErrorAction SilentlyContinue | Select-Object Source\""
ssh win-local-via-reverse-ssh "powershell -NoProfile -ExecutionPolicy Bypass -Command \"& 'D:\AI\Pivot_Client\buyer_client\bootstrap\windows\start_buyer_client.ps1'\""
ssh win-local-via-reverse-ssh "powershell -NoProfile -Command \"Get-NetTCPConnection -LocalPort 8902 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess; (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8902/ -TimeoutSec 5).StatusCode\""
```

- After state:
  - `D:\AI\Pivot_Client\buyer_client` exists
  - `D:\AI\Pivot_Client\buyer_client\bootstrap\windows\start_buyer_client.ps1` exists
  - `wireguard.exe` and `wg.exe` exist on Windows
  - startup script completed
  - local app listener is up on:
    - `127.0.0.1:8902`
  - local app root returns:
    - `200`
- Rollback:
  - stop local app process on `8902` if the staged deployment must be invalidated
- What this verified:
  - Windows-local Buyer_Client surface really exists and is running locally on Windows

### Action 2: Windows-local bind to the real buyer/runtime chain

- Before state:
  - local app is listening on `127.0.0.1:8902`
  - target real chain is:
    - `order_5d1236d1338ac6ab`
    - `grant_a84b49a685609153`
    - `runtime_session_bd6eab1e6279291f`
- Command family:
  - executed on Windows locally via PowerShell and local HTTP calls to `127.0.0.1:8902`
  1. open local window session
  2. login buyer `stage2-buyer-a341c1804963@example.com`
  3. pull active grants
  4. attach exact grant `grant_a84b49a685609153`
  5. create / refresh the real runtime session through local API surfaces
- After state:
  - local app window session opened:
    - `ad94bbdc-24e0-4e82-8f0b-d0452b8108bf`
  - buyer login succeeded:
    - `user_13e35642ec9f9f57`
  - active grants returned the real grant:
    - `grant_id = grant_a84b49a685609153`
    - `grant_code = CDzofnFz7eoFkI6beKoQeTD_JPkNpWf-NqvinDSTBt0`
    - `runtime_session_id = runtime_session_bd6eab1e6279291f`
  - local attach succeeded on the same grant
  - local create / refresh kept the same runtime session:
    - `runtime_session_bd6eab1e6279291f`
    - `status = ready`
    - `runtime_bundle_status = running`
- Rollback:
  - stop the local app process if the Windows-local deployment must be invalidated
  - no grant/session mutation beyond same-chain reads/refreshes
- What this verified:
  - Windows-local Buyer_Client can bind itself to the same real buyer/runtime chain before runtime-path verification

### Action 3: first Windows-local runtime-path step on the real chain

- Before state:
  - Windows-local Buyer_Client is already bound to:
    - `grant_a84b49a685609153`
    - `runtime_session_bd6eab1e6279291f`
  - local runtime access plan is ready for:
    - WireGuard
    - shell
    - workspace
    - task
- Command:
  - executed on Windows locally via local API:

```http
POST http://127.0.0.1:8902/local-api/wireguard/up
```

- After state:
  - first Windows-local rerun surfaced a real blocker:
    - `step = wireguard.up`
    - `code = wireguard_install_failed`
    - message = `Failed to install or start the buyer WireGuard tunnel service.`
  - exact stderr detail:
    - `Error: Tunnel already installed and running`
  - runtime later narrowed the blocker basis:
    - current runtime surfaces themselves are live
    - issue is likely remote step sequencing across the short browser window-session TTL
    - runtime is rerunning the same Windows-local wireguard/shell/workspace/task path inside one single local PowerShell session so the same window session stays valid across all calls
- Rollback:
  - local rollback was executed:
    - `POST /local-api/wireguard/down`
  - rollback returned:
    - `status = down`
    - `interface_name = pivot-2426388f`
  - temporary local test workspace under:
    - `D:\AI\Pivot_Client\buyer_client\stage6_workspace`
    was removed
- What this verified:
  - Windows-local path progressed past app staging and real-chain binding
  - first failing rerun stopped at the first Windows-local WireGuard step
  - current active rerun basis is narrower: keep the same real chain and rerun inside one local PowerShell session before treating the tunnel error as the final product-path blocker

## Current Exact Blocker

### Action 4: rerun against the updated Windows-local tree

- Before state:
  - current repo tree was redeployed to:
    - `D:\AI\Pivot_Client\buyer_client`
  - staged Windows file hashes now match current repo, including:
    - `buyer_client_app\wireguard.py`
  - staged buyer app was then restarted from:
    - `D:\AI\Pivot_Client\buyer_client\bootstrap\windows\start_buyer_client.ps1`
- Commands:

```bash
Buyer_Client/scripts/deploy-to-windows.sh
ssh win-local-via-reverse-ssh "powershell -NoProfile -ExecutionPolicy Bypass -Command \"& 'D:\AI\Pivot_Client\buyer_client\bootstrap\windows\start_buyer_client.ps1'\""
ssh win-local-via-reverse-ssh "powershell -NoProfile -Command \"Get-NetTCPConnection -LocalPort 8902 -State Listen -ErrorAction SilentlyContinue; (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8902/ -TimeoutSec 5).StatusCode\""
ssh win-local-via-reverse-ssh "powershell -NoProfile -ExecutionPolicy Bypass -Command \"& 'D:\AI\Pivot_Client\stage6_windows_verify.ps1'\""
```

- After state:
  - repo deployment completed
  - staged `wireguard.py` hash now matches local repo
  - startup script completed without crashing
  - but the Windows-local app is no longer listening on `127.0.0.1:8902`:
    - `Get-NetTCPConnection -LocalPort 8902 -State Listen` returned nothing
    - local HTTP probe to `http://127.0.0.1:8902/` failed with:
      - `无法连接到远程服务器`
  - full Windows-local verifier script then failed immediately on the same basis:
    - could not connect to local Buyer_Client at `127.0.0.1:8902`
- Rollback:
  - no additional product-path mutation occurred
  - temporary local test workspace was removed by the verifier cleanup path
- What this verified:
  - the current exact blocker has shifted earlier than `wireguard_up`
  - the updated Windows-local Buyer_Client app is not staying up on `127.0.0.1:8902`, so there is no live local API surface to drive on the real chain

### Action 5: minimal seller-tunnel stop to separate same-host routes

- Before state:
  - buyer tunnel `pivot-2426388f` exists on Windows and shows:
    - `0 B received`
    - `16.62 KiB sent`
  - seller tunnel `wg-seller` also exists on the same host and shows:
    - active handshakes
    - `2.60 MiB received`
    - `1.39 MiB sent`
  - `route print 10.66.66.1` shows duplicate host routes via:
    - `10.66.66.10`
    - `10.66.66.201`
- Command:

```bash
ssh win-local-via-reverse-ssh "powershell -NoProfile -ExecutionPolicy Bypass -Command \"& 'D:\AI\Pivot_Client\seller_client\bootstrap\windows\stop_windows_wg_tunnel.ps1' -HostTunnelName wg-seller\""
```

- After state:
  - `WireGuard Tunnel: wg-seller` returned:
    - `status = Stopped`
  - `wg.exe show` no longer lists `wg-seller`
  - `route print 10.66.66.1` now shows only one host route:
    - via `10.66.66.201`
- Rollback:
  - reinstall / restart the seller tunnel from its existing config after the Windows-local buyer verification block
- What this verified:
  - the same-host seller/buyer WireGuard lane collision was removed with the minimal Windows-local mutation requested by `runtime`

### Action 6: Stage6 rerun after seller-tunnel stop

- Before state:
  - seller tunnel `wg-seller` is stopped
  - duplicate route to `10.66.66.1/32` is removed
  - real chain remains unchanged:
    - `order_5d1236d1338ac6ab`
    - `grant_a84b49a685609153`
    - `runtime_session_bd6eab1e6279291f`
- Command:

```bash
ssh win-local-via-reverse-ssh "powershell -NoProfile -ExecutionPolicy Bypass -Command \"& 'D:\AI\Pivot_Client\stage6_windows_verify.ps1'\""
```

- After state:
  - rerun still fails immediately before entering the local product path
  - exact preflight result:
    - `listener = {}`
    - `home_status = null`
  - exact failure:
    - local HTTP calls to `http://127.0.0.1:8902/` fail with:
      - `无法连接到远程服务器`
- Rollback:
  - no additional product-path mutation occurred
  - temporary local test workspace was removed by the verifier cleanup path
- What this verified:
  - even after seller-tunnel separation, the current exact blocker remains the missing Windows-local app listener on `127.0.0.1:8902`
  - proof generation still stops before login/grant/session/WireGuard on the local product surface

### Action 7: direct rerun against the unchanged real chain after lead-side recheck

- Before state:
  - lead had already rechecked locally on Windows and reported a live listener on `127.0.0.1:8902`
  - tester therefore reran the same exact preflight and full verifier on the unchanged real chain:
    - `order_5d1236d1338ac6ab`
    - `grant_a84b49a685609153`
    - `runtime_session_bd6eab1e6279291f`
- Commands:

```bash
ssh win-local-via-reverse-ssh "powershell -NoProfile -EncodedCommand <listener_and_http_probe_script>"
ssh win-local-via-reverse-ssh "powershell -NoProfile -ExecutionPolicy Bypass -Command \"& 'D:\AI\Pivot_Client\stage6_windows_verify.ps1'\""
```

- After state:
  - direct preflight rerun still reports:
    - `listener = {}`
    - `home_status = null`
  - local HTTP probe to `http://127.0.0.1:8902/` still fails with:
    - `无法连接到远程服务器`
  - full verifier script fails immediately on the same basis
- Rollback:
  - no additional product-path mutation occurred
  - temporary local test workspace was removed by verifier cleanup
- What this verified:
  - the exact current blocker is reproducible on demand from tester side
  - at the time of actual proof rerun, there is still no live Windows-local Buyer_Client API surface to drive

### Action 8: same-chain rerun after listener recovery and same-session key-refresh fix

- Before state:
  - real chain remains unchanged:
    - `order_5d1236d1338ac6ab`
    - `grant_a84b49a685609153`
    - `runtime_session_bd6eab1e6279291f`
  - local app listener is back on:
    - `127.0.0.1:8902`
    - `home_status = 200`
- Command:

```bash
ssh win-local-via-reverse-ssh "powershell -NoProfile -ExecutionPolicy Bypass -Command \"& 'D:\AI\Pivot_Client\stage6_windows_verify.ps1'\""
```

- After state:
  - rerun advanced into the real Windows-local product path:
    - login succeeded
    - active grant pull succeeded
    - attach succeeded
    - create / refresh stayed on `runtime_session_bd6eab1e6279291f`
    - `wireguard_up` succeeded with:
      - `status = up`
      - `interface_name = pivot-2426388f`
      - `converged = true`
    - `open_shell` succeeded with:
      - `shell_embed_url = http://10.66.66.1:32080/shell/`
  - current exact failure is now at Windows-local workspace sync:
    - `step = workspace.sync`
    - `code = workspace_sync_failed`
    - `message = Failed to upload or extract the local workspace into the buyer runtime.`
    - detail exception:
      - `Server disconnected without sending a response.`
  - failing URLs on the same chain were:
    - `http://10.66.66.1:32080/api/workspace/upload`
    - `http://10.66.66.1:32080/api/workspace/extract`
    - `http://10.66.66.1:32080/api/workspace/status`
- Rollback:
  - `wireguard_down` succeeded:
    - `status = down`
    - `interface_name = pivot-2426388f`
  - temporary local test workspace was removed
- What this verified:
  - the old listener blocker is stale
  - current exact Stage6 blocker moved forward to the Windows-local workspace boundary on the same real chain

## Current Exact Blocker

### Control-Plane Update: earlier tunnel-convergence blocker is now stale

- buyer delivered a current-tree `wireguard_up` convergence fix
- latest rerun on the unchanged real chain showed:
  - Windows-local path reaches:
    - login
    - grant pull / attach
    - same-session create / refresh
    - `wireguard_up`
  - current exact blocker is now the data-plane readability probe inside `wireguard_up`, not service-install convergence

### Action 9: same-chain rerun after Windows tunnel-convergence fix

- Before state:
  - unchanged real chain remains:
    - `order_5d1236d1338ac6ab`
    - `grant_a84b49a685609153`
    - `runtime_session_bd6eab1e6279291f`
  - staged Windows `buyer_client_app\wireguard.py` matches current repo with the new convergence fix
- Command:

```bash
ssh win-local-via-reverse-ssh "powershell -NoProfile -ExecutionPolicy Bypass -Command \"& 'D:\AI\Pivot_Client\stage6_windows_verify.ps1'\""
```

- After state:
  - rerun advanced through:
    - login
    - grant pull / attach
    - same-session create / refresh
  - current exact failure happens inside Windows-local `wireguard_up`
  - local API returns:
    - `step = wireguard.up`
    - `code = wireguard_gateway_unreachable`
    - `message = Buyer WireGuard tunnel came up, but the runtime gateway is not readable through it.`
  - exact probe details:
    - `config_path = D:\AI\Pivot_Client\buyer_client\sessions\runtime_session_bd6eab1e6279291f\wireguard\pivot-2426388f.conf`
    - `interface_name = pivot-2426388f`
    - `health_url = http://10.66.66.1:32080/health`
    - exception = `Server error '502 Bad Gateway' for url 'http://10.66.66.1:32080/health'`
- Rollback:
  - `wireguard_down` succeeds:
    - `status = down`
    - `interface_name = pivot-2426388f`
  - temporary local test workspace was removed
- What this verified:
  - the old `Tunnel already installed and running` blocker is stale
  - current exact Stage6 blocker is now the Windows-local data-plane/readability boundary inside `wireguard_up` on the same real chain

## Current Exact Blocker

- blocked step:
  - Windows-local `wireguard_up` data-plane/readability probe on the unchanged real chain
- exact error:
  - `step = wireguard.up`
  - `code = wireguard_gateway_unreachable`
  - `message = Buyer WireGuard tunnel came up, but the runtime gateway is not readable through it.`
  - probe details:
    - `health_url = http://10.66.66.1:32080/health`
    - exception = `Server error '502 Bad Gateway'`
- why this stops proof generation:
  - until the Windows-local buyer tunnel can actually read the runtime gateway over the same real session, tester cannot credibly proceed to Windows-local shell / workspace / natural-language task proof

### Action 9: same-chain rerun after real Windows wireguard convergence fix

- Before state:
  - unchanged real chain remains:
    - `order_5d1236d1338ac6ab`
    - `grant_a84b49a685609153`
    - `runtime_session_bd6eab1e6279291f`
  - current repo tree with the Windows tunnel-service convergence probe fix was redeployed to:
    - `D:\AI\Pivot_Client\buyer_client`
  - exact staged `buyer_client_app\wireguard.py` hash matches repo:
    - `4CA95BB37417B8272B4590E3D1AD8486E5EA9994246B432DABD40C518061CB24`
- Command:

```bash
ssh win-local-via-reverse-ssh "powershell -NoProfile -ExecutionPolicy Bypass -Command \"& 'D:\AI\Pivot_Client\stage6_windows_verify.ps1'\""
```

- After state:
  - rerun advances further on the real Windows-local chain:
    - login succeeds
    - grant pull / attach succeeds
    - same-session create / refresh stays on `runtime_session_bd6eab1e6279291f`
    - `wireguard_up` now converges successfully:
      - `status = up`
      - `interface_name = pivot-2426388f`
      - `converged = true`
      - probe confirms:
        - `WireGuardTunnel$pivot-2426388f` service status = `Running`
        - `wg show pivot-2426388f` succeeds
        - latest handshake `2 seconds ago`
        - transfer `124 B received, 180 B sent`
    - `open_shell` succeeds:
      - `shell_embed_url = http://10.66.66.1:32080/shell/`
  - tester rerun observed the next failing step at Windows-local workspace sync:
    - `step = workspace.sync`
    - `code = workspace_sync_failed`
    - `message = Failed to upload or extract the local workspace into the buyer runtime.`
    - detail exception:
      - `Server error '502 Bad Gateway' for url 'http://10.66.66.1:32080/api/workspace/upload'`
  - later lead-side reprobe narrowed the blocker basis one level deeper on the same unchanged chain:
    - `wireguard_up` returns success
    - `wg show` still reports `0 B received`
    - direct Windows-local `GET http://10.66.66.1:32080/health` times out
    - `/local-api/workspace/status` returns `502`
    - gateway Caddy on the same session is timing out to runtime upstream:
      - `10.0.20.2:7681`
    - runtime logs are unavailable because node:
      - `ukdcii54j1xasu7okv7zgm8s0`
      is not available
  - so the current blocker is no longer treated as upload-only or merely buyer-side tunnel readability
- Rollback:
  - `wireguard_down` succeeds:
    - `status = down`
    - `interface_name = pivot-2426388f`
  - temporary local test workspace was removed
- What this verified:
  - the earlier Windows `wireguard_up` convergence blocker is stale
  - current exact Stage6 blocker is now the deeper same-session upstream reachability boundary on the same real chain

## Current Exact Blocker

- blocked step:
  - same-session upstream reachability from gateway to runtime after Windows-local `wireguard_up` success on the unchanged real chain
- exact error:
  - `wireguard_up` returns success with service `Running` and `wg show` OK
  - but `wg show` still shows `0 B received`
  - direct Windows-local `GET http://10.66.66.1:32080/health` times out
  - `/local-api/workspace/status` returns `502`
  - deeper runtime-side boundary:
    - gateway Caddy times out to runtime upstream `10.0.20.2:7681`
    - runtime logs unavailable because node `ukdcii54j1xasu7okv7zgm8s0` is not available
- why this stops proof generation:
  - the Windows-local path now reaches login / grant / session / WireGuard / shell on the real chain, but the same session still cannot complete end-to-end runtime readability because the gateway cannot reach the runtime upstream on `10.0.20.2:7681`; until that same-chain upstream boundary is resolved, tester cannot credibly complete Windows-local workspace or natural-language task proof

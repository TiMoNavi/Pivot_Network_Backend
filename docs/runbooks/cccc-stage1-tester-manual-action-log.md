# CCCC Stage1 Tester Manual-Action Log

更新时间：`2026-04-11 04:26:31 CST` (`2026-04-10 20:26:31 UTC`)

## Scope

- 只服务于 `Stage1`
- 只记录 `tester` 的 Windows/operator/manual-action 证据
- 这不是 Stage1 成功证明
- `operator access` / `SSH` / `reverse SSH` / `WireGuard reachability` 不能单独当作 Stage1 proof
- 本日志只能附着到 `runtime` 的同一条 seller-path rerun evidence chain

## 当前结论边界

- 截至本次记录，`tester` 还没有执行任何 stateful step
- 当前只完成了 read-only baseline
- 当前已确认 blocker 是：最新 seller session 对 backend 的直接读面探测返回 `401 unauthorized`
- 这个 blocker 只能写成 `auth/session blocker`
- 不能把它写成 `join failed`
- 当前没有 canonical rerun `session_id`
- `join_session_7aafaead0385c9c6` 已被完全剥离出 Stage1 proof：
  - 它只是一份 drifted local artifact / parked candidate
  - backend `GET /seller/onboarding/sessions/join_session_7aafaead0385c9c6` 返回 `404 Onboarding session not found`
  - 它不能再作为 Stage1 active anchor
- 当前 canonical rerun anchor 已经切换到 replacement chain：
  - `session_id = join_session_733b69e1bf293c7a`
  - `compute_node_id = compute-user-8b7c0b9dd725cbc3`
  - `session_file = D:\AI\Pivot_Client\seller_client\sessions\join_session_733b69e1bf293c7a\session.json`
  - 这是当前唯一允许挂接 Block 2 及后续 proof step 的链路

## Read-Only Baseline

- Windows operator 入口当前可用：`550W` / `550w\\550w`
- Windows 工作区存在：`D:\AI\Pivot_Client`、`D:\AI\Pivot_Client\seller_client`
- `sshd` 当前状态：`Running`
- seller client 本地服务：`http://127.0.0.1:8901/ -> 200`
- Windows 本地 Docker Swarm：
  - `NodeID = ukdcii54j1xasu7okv7zgm8s0`
  - `NodeAddr = 10.66.66.10`
  - `LocalNodeState = active`
  - `RemoteManagers = 10.66.66.1:2377`
- manager 侧当前看到：
  - `docker-desktop -> Ready / Active`
  - `Addr = 10.66.66.10`
  - 当前至少有一个运行中的 task：`portainer_agent.ukdcii54j1xasu7okv7zgm8s0`
- Windows bootstrap 脚本与本地 repo 当前 hash 完全一致：
  - `start_seller_client.ps1 -> 1998bded9e2cf23eda9aeee47b911e0058cb0f584635fdb575152c34f03fc656`
  - `attempt_manager_addr_correction_cycle.ps1 -> 2b3cf70d08f92d398b0a5164b8b8f70a674fbb95a056b08ba5e9e30a64cc1b70`
  - `rejoin_windows_swarm_worker.ps1 -> 4dc3c5cf385aacbc43fed7e9d73508c27e1ff3fd5a904cfa98b8294407783421`
- 目前没有证据表明需要先做 `deploy-to-windows`
- 最新 session baseline：
  - `session_file = D:\AI\Pivot_Client\seller_client\sessions\join-session-0001\session.json`
  - `session_last_write_time = 2026-04-10 19:35:31 CST`
  - `session_id = join-session-0001`
  - `onboarding_status = issued`
  - `requested_compute_node_id = compute-seller-1`
  - `backend_base_url = https://pivotcompute.store`
  - `backend_api_prefix = /api/v1`
  - `auth_token_present = true`
  - backend direct read probe result = `401 unauthorized`

## Manual-Action Ledger

### Action 1: Windows operator baseline

- Before state:
  - Windows operator/session baseline 未核实
- Command:

```bash
ssh win-local-via-reverse-ssh "hostname && whoami && cd && powershell -NoProfile -Command \"Test-Path 'D:\AI\Pivot_Client'; Test-Path 'D:\AI\Pivot_Client\seller_client'; (Get-Service sshd).Status\""
```

- After state:
  - `hostname -> 550W`
  - `whoami -> 550w\550w`
  - default directory -> `C:\Users\Administrator`
  - `Test-Path 'D:\AI\Pivot_Client' -> True`
  - `Test-Path 'D:\AI\Pivot_Client\seller_client' -> True`
  - `sshd -> Running`
- Rollback:
  - none; read-only inspection
- What this verified:
  - 只验证 Windows operator entry 与工作区存在
  - 不构成 Stage1 success

### Action 2: seller client local HTTP and script timestamp baseline

- Before state:
  - seller client 本地服务与 Windows bootstrap script 状态未核实
- Command:

```bash
ssh win-local-via-reverse-ssh "powershell -NoProfile -Command \"try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8901/ -TimeoutSec 10).StatusCode } catch { $_.Exception.Message }; Get-Item 'D:\AI\Pivot_Client\seller_client\bootstrap\windows\start_seller_client.ps1','D:\AI\Pivot_Client\seller_client\bootstrap\windows\attempt_manager_addr_correction_cycle.ps1','D:\AI\Pivot_Client\seller_client\bootstrap\windows\rejoin_windows_swarm_worker.ps1' | Select-Object FullName,Length,LastWriteTime | Format-Table -AutoSize\""
```

- After state:
  - `http://127.0.0.1:8901/ -> 200`
  - `start_seller_client.ps1 -> Length 2376 / LastWriteTime 2026/4/9 6:53:26`
  - `attempt_manager_addr_correction_cycle.ps1 -> Length 20162 / LastWriteTime 2026/4/10 2:55:05`
  - `rejoin_windows_swarm_worker.ps1 -> Length 20776 / LastWriteTime 2026/4/10 3:59:16`
- Rollback:
  - none; read-only inspection
- What this verified:
  - seller client 本地 HTTP 面当前可响应
  - 当前 Windows 侧 seller bootstrap script 存在，可进一步比对 drift
  - 不构成 Stage1 success

### Action 3: latest session baseline and backend direct-read probe

- Before state:
  - 当前 seller session 是否还能写 backend 未核实
- Command:
  - executed via `ssh win-local-via-reverse-ssh "powershell -NoProfile -EncodedCommand <generated-from-inline-script>"`
  - inline PowerShell payload:

```powershell
$file = Get-ChildItem 'D:\AI\Pivot_Client\seller_client\sessions' -Recurse -Filter session.json -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1
if (-not $file) {
  [pscustomobject]@{ session_found = $false } | ConvertTo-Json -Depth 4 -Compress
  exit 0
}
$session = Get-Content -Raw -Encoding UTF8 $file.FullName | ConvertFrom-Json
$headers = @{ Authorization = "Bearer $($session.auth_token)" }
$url = "$($session.backend_base_url)$($session.backend_api_prefix)/seller/onboarding/sessions/$($session.onboarding_session.session_id)"
try {
  $resp = Invoke-RestMethod -Headers $headers -Uri $url -Method GET -TimeoutSec 15
  [pscustomobject]@{
    session_found = $true
    session_file = $file.FullName
    session_last_write_time = $file.LastWriteTime
    session_id = $session.onboarding_session.session_id
    onboarding_status = $session.onboarding_session.status
    requested_compute_node_id = $session.onboarding_session.requested_compute_node_id
    backend_base_url = $session.backend_base_url
    backend_api_prefix = $session.backend_api_prefix
    auth_token_present = [bool]$session.auth_token
    probe_ok = $true
    backend_status = $resp.status
    manager_acceptance_status = $resp.manager_acceptance.status
    compute_node_id = $resp.compute_node_id
  } | ConvertTo-Json -Depth 5 -Compress
} catch {
  [pscustomobject]@{
    session_found = $true
    session_file = $file.FullName
    session_last_write_time = $file.LastWriteTime
    session_id = $session.onboarding_session.session_id
    onboarding_status = $session.onboarding_session.status
    requested_compute_node_id = $session.onboarding_session.requested_compute_node_id
    backend_base_url = $session.backend_base_url
    backend_api_prefix = $session.backend_api_prefix
    auth_token_present = [bool]$session.auth_token
    probe_ok = $false
    probe_error = $_.Exception.Message
  } | ConvertTo-Json -Depth 5 -Compress
}
```

- After state:
  - latest session file found: `D:\AI\Pivot_Client\seller_client\sessions\join-session-0001\session.json`
  - `session_last_write_time -> 2026-04-10 19:35:31 CST`
  - `session_id -> join-session-0001`
  - `onboarding_status -> issued`
  - `requested_compute_node_id -> compute-seller-1`
  - `backend_base_url -> https://pivotcompute.store`
  - `backend_api_prefix -> /api/v1`
  - `auth_token_present -> true`
  - backend direct read probe -> `401 unauthorized`
- Rollback:
  - none; read-only inspection
- What this verified:
  - 当前旧 session 不能直接作为 seller-path same-chain rerun 证据起点
  - 当前 blocker 是 `auth/session blocker`
  - 这不是 join failure 结论

### Action 4: Windows local swarm baseline

- Before state:
  - Windows 本地 swarm 状态未核实
- Command:

```bash
ssh win-local-via-reverse-ssh "powershell -NoProfile -Command \"docker info --format '{{json .Swarm}}'\""
```

- After state:
  - `NodeID -> ukdcii54j1xasu7okv7zgm8s0`
  - `NodeAddr -> 10.66.66.10`
  - `LocalNodeState -> active`
  - `ControlAvailable -> false`
  - `RemoteManagers -> 10.66.66.1:2377`
- Rollback:
  - none; read-only inspection
- What this verified:
  - Windows 本地 seller host 当前仍处于 swarm active 状态
  - 这是 same-chain rerun 前的 before-state，不是最终成功证明

### Action 5: manager-side worker baseline

- Before state:
  - manager 侧 worker 观测未核实
- Commands:

```bash
docker node ls --format '{{.Hostname}}\t{{.Status}}\t{{.Availability}}\t{{.ManagerStatus}}'
docker node inspect docker-desktop --format '{{json .Status}} {{json .Spec}}'
docker node ps docker-desktop --format '{{.Name}}\t{{.DesiredState}}\t{{.CurrentState}}\t{{.Error}}'
```

- After state:
  - `docker-desktop -> Ready / Active`
  - manager sees `Addr -> 10.66.66.10`
  - labels include:
    - `platform.compute_enabled = true`
    - `platform.compute_node_id = compute-user-a1741e87c5fe9eaa`
    - `platform.role = compute`
  - current task list includes:
    - `portainer_agent.ukdcii54j1xasu7okv7zgm8s0 -> Running / Running about a minute ago`
- Rollback:
  - none; read-only inspection
- What this verified:
  - manager 当前能看到 worker 与任务存在
  - 这仍然只是 baseline，不是同一条 seller-path rerun chain 的闭环证据

### Action 6: Windows bootstrap script drift check

- Before state:
  - 不确定是否需要 `deploy-to-windows`
- Commands:

```bash
sha256sum Seller_Client/bootstrap/windows/start_seller_client.ps1 Seller_Client/bootstrap/windows/attempt_manager_addr_correction_cycle.ps1 Seller_Client/bootstrap/windows/rejoin_windows_swarm_worker.ps1
ssh win-local-via-reverse-ssh "powershell -NoProfile -Command \"Get-FileHash 'D:\AI\Pivot_Client\seller_client\bootstrap\windows\start_seller_client.ps1','D:\AI\Pivot_Client\seller_client\bootstrap\windows\attempt_manager_addr_correction_cycle.ps1','D:\AI\Pivot_Client\seller_client\bootstrap\windows\rejoin_windows_swarm_worker.ps1' -Algorithm SHA256 | Select-Object Path,Hash | ConvertTo-Json -Compress\""
```

- After state:
  - local and remote hashes are identical for all three scripts
  - no verified script drift at baseline
- Rollback:
  - none; read-only inspection
- What this verified:
  - `deploy-to-windows` 目前不能用“脚本不一致”作为理由
  - 如果后续仍执行 `deploy-to-windows`，需要新的 before/after/why 证据

### Action 7: fresh onboarding session creation via local seller app

- Before state:
  - 当前死 session 基线仍是 `join-session-0001`
  - 该 session 的 backend direct read probe 已返回 `401 unauthorized`
  - 在 platform backend upgrade/restart green light 之前，不允许消耗 correction/proof run
- Command family:
  - `local seller app -> window/session/auth/onboarding-start`
  - 这是 `runtime` 执行的本地 GUI/manual step
  - `tester` 没有远程代执行这一步
  - `tester` 通过 read-only 方式验证 after-state
- After state:
  - new top session file:
    - `D:\AI\Pivot_Client\seller_client\sessions\join_session_7aafaead0385c9c6\session.json`
  - `LastWriteTime -> 2026/4/11 04:28:35 CST`
  - `session_id -> join_session_7aafaead0385c9c6`
  - `requested_compute_node_id -> compute-user-a1741e87c5fe9eaa`
  - `auth_token_present -> true`
  - local session file field `onboarding_status -> verified`
- Rollback:
  - close / abandon the fresh session if platform redirects the chain
- What this verified:
  - 已经存在一个新的 seller-path session，可作为后续 same-chain proof run 的起点
  - 这一步只证明 fresh session exists
  - 不证明 commercialization chain 已经在当前 active backend 上可靠持久化
  - correction-cycle / proof run 仍暂停，直到 `platform` 给出 backend upgrade/restart green light

### Action 7A: later invalidation of parked candidate `join_session_7aafaead0385c9c6`

- Before state:
  - Windows 本地仍保留 `join_session_7aafaead0385c9c6`
  - 它曾被当作 parked candidate 记录
- Command:
  - backend truth verification performed by `runtime`:
    - `GET /seller/onboarding/sessions/join_session_7aafaead0385c9c6`
    - with that session token
- After state:
  - backend returns `404 Onboarding session not found`
  - `join_session_7aafaead0385c9c6` 被降级为 drifted local artifact only
  - 它不能作为 Stage1 proof chain，也不能作为 canonical rerun anchor
- Rollback:
  - none on tester side
  - wait for `runtime` to mint one replacement fresh backend-visible session
- What this verified:
  - local Windows session file 的存在，不等于 backend truth 仍存在
  - parked candidate 必须从 Stage1 proof 完全剥离

### Block 1: recreate one fresh backend-visible onboarding session on upgraded backend

- Before state:
  - local candidate `join_session_7aafaead0385c9c6` still exists on Windows
  - backend `GET /seller/onboarding/sessions/join_session_7aafaead0385c9c6` returns `404`
  - therefore it cannot be the Stage1 chain
- Exact command family:
  - local seller app `auth/login` with the active temp seller
  - `window-session/open`
  - `onboarding/start` on the upgraded backend
- After state:
  - replacement `session_id -> join_session_733b69e1bf293c7a`
  - replacement `compute_node_id -> compute-user-8b7c0b9dd725cbc3`
  - latest local session file observed by tester:
    - `D:\AI\Pivot_Client\seller_client\sessions\join_session_733b69e1bf293c7a\session.json`
    - `LastWriteTime -> 2026/4/11 04:34:43 CST`
  - local session fields observed by tester:
    - `onboarding_status -> issued`
    - `auth_token_present -> true`
  - `runtime` declared this replacement anchor live for the real Stage1 rerun
- Rollback:
  - abandon / close the replacement session if creation or later same-chain verification fails
- What this verified:
  - a real rerunnable Stage1 chain exists again before the correction-cycle proof step
  - tester ledger is now rebound from provisional state to the canonical rerun session
  - all subsequent stateful proof blocks must stay on `join_session_733b69e1bf293c7a` / `compute-user-8b7c0b9dd725cbc3`

## Pending Same-Chain Stateful Blocks

- 当前进行中的 stateful proof block：
  - Block 2:
    - single Windows correction-cycle proof run
    - fixed chain: `join_session_733b69e1bf293c7a` / `compute-user-8b7c0b9dd725cbc3`
- Block 2 结束后仍需补齐：
  - post-correction proof outcome capture
  - backend commercialization chain verification
- 等 `runtime` 给出同一条 seller-path rerun 的 stateful step block 后，再按下面格式追加：
  - before state
  - exact command
  - after state
  - rollback
  - what it verified

### Block 2: single Windows correction-cycle proof run on the replacement chain

- Before state:
  - backend `GET /seller/onboarding/sessions/join_session_733b69e1bf293c7a` returns:
    - `200`
    - `status = issued`
    - `compute_node_id = compute-user-8b7c0b9dd725cbc3`
    - `manager_acceptance.status = pending`
  - active session file:
    - `D:\AI\Pivot_Client\seller_client\sessions\join_session_733b69e1bf293c7a\session.json`
- Exact command:

```powershell
powershell -ExecutionPolicy Bypass -File "D:\AI\Pivot_Client\seller_client\bootstrap\windows\attempt_manager_addr_correction_cycle.ps1" -SessionFilePath "D:\AI\Pivot_Client\seller_client\sessions\join_session_733b69e1bf293c7a\session.json" -JoinMode wireguard -AdvertiseAddress 10.66.66.10 -DataPathAddress 10.66.66.10 -ListenAddress 10.66.66.10:2377 -MinimumTcpValidationPort 8080
```

- After state:
  - current same-session blocker state:
    - backend status -> `verify_failed`
    - `manager_acceptance.status -> claim_failed`
    - detail -> `Refusing to change seller_user_id on claimed node docker-desktop.`
  - remaining post-run facts still pending from `runtime`:
    - exact join facts
    - manager monitor facts
    - `effective_target`
    - minimum TCP validation result
- Rollback:
  - `clear_windows_join_state.ps1` only if this chain becomes unusable after the run
- What this verified:
  - this is the single Stage1 same-chain seller-path proof run on the upgraded backend
  - the current canonical-chain failure mode is backend-side claim refusal, not a generic transport failure
  - tester must not improvise a fix; the next move must come from `runtime` on this same chain

### Block 2A: minimal manager-side stale-claim label removal on the canonical chain

- Before state:
  - canonical chain remains:
    - `session_id = join_session_733b69e1bf293c7a`
    - `compute_node_id = compute-user-8b7c0b9dd725cbc3`
  - current backend state on the same session:
    - `verify_failed`
    - `manager_acceptance = claim_failed`
    - detail = `Refusing to change seller_user_id on claimed node docker-desktop.`
  - current labels on manager worker `ukdcii54j1xasu7okv7zgm8s0`:
    - `platform.accelerator = gpu`
    - `platform.compute_enabled = true`
    - `platform.compute_node_id = compute-user-a1741e87c5fe9eaa`
    - `platform.control_plane = false`
    - `platform.managed = true`
    - `platform.role = compute`
    - `platform.seller_user_id = user_a1741e87c5fe9eaa`
- Command:

```bash
docker node update --label-rm platform.seller_user_id --label-rm platform.compute_node_id ukdcii54j1xasu7okv7zgm8s0
```

- After state:
  - command returned node id:
    - `ukdcii54j1xasu7okv7zgm8s0`
  - `docker node inspect ukdcii54j1xasu7okv7zgm8s0 --format '{{json .Spec.Labels}}'` now returns:
    - `platform.accelerator = gpu`
    - `platform.compute_enabled = true`
    - `platform.control_plane = false`
    - `platform.managed = true`
    - `platform.role = compute`
  - `platform.seller_user_id` no longer present
  - `platform.compute_node_id` no longer present
- Rollback:

```bash
docker node update --label-add platform.seller_user_id=user_a1741e87c5fe9eaa --label-add platform.compute_node_id=compute-user-a1741e87c5fe9eaa ukdcii54j1xasu7okv7zgm8s0
```

- What this verified:
  - the exact minimal stale ownership rewrite blocker named by `runtime` has been cleared on manager
  - the session anchor did not change
  - control can now return to `runtime` to re-run same-session reverify/claim on `join_session_733b69e1bf293c7a`

### Block 3: same-session backend reverify/claim after label clear

- Before state:
  - canonical chain remains unchanged:
    - `session_id = join_session_733b69e1bf293c7a`
    - `compute_node_id = compute-user-8b7c0b9dd725cbc3`
  - tester has already removed stale labels from manager node `ukdcii54j1xasu7okv7zgm8s0`:
    - `platform.seller_user_id` absent
    - `platform.compute_node_id` absent
  - backend session is still:
    - `verify_failed`
    - `manager_acceptance.status = claim_failed`
- Command:
  - same-session backend reverify/claim using existing locator fields:

```text
POST /api/v1/seller/onboarding/sessions/join_session_733b69e1bf293c7a/re-verify
```

  - payload:

```json
{"reported_phase":"repair","node_ref":"ukdcii54j1xasu7okv7zgm8s0","compute_node_id":"compute-user-8b7c0b9dd725cbc3","notes":["same-session reverify after tester removed stale seller/compute labels"],"raw_payload":{"source_surface":"runtime_same_chain_reverify_after_label_clear"}}
```

- After state:
  - same-session backend reverify recovered on `join_session_733b69e1bf293c7a`:
    - `manager_acceptance.status = matched`
    - `effective_target_addr = 10.66.66.10`
    - `effective_target_source = manager_matched`
    - `truth_authority = raw_manager`
  - backend `minimum_tcp_validation` is still `null`
- Rollback:
  - no session change
  - if reverify still fails, keep the same chain and report the next exact blocker
- What this verified:
  - clearing the stale manager claim labels was sufficient for backend claim/reverify to recover on the existing canonical session
  - the canonical chain stayed unchanged through recovery

### Block 4: same-session TCP validation and minimum-tcp-validation writeback

- Before state:
  - canonical chain remains unchanged:
    - `session_id = join_session_733b69e1bf293c7a`
    - `compute_node_id = compute-user-8b7c0b9dd725cbc3`
  - same-session backend reverify has already recovered to:
    - `manager_acceptance.status = matched`
    - `effective_target_addr = 10.66.66.10`
    - `effective_target_source = manager_matched`
    - `truth_authority = raw_manager`
  - backend `minimum_tcp_validation` is still `null`
- Command family:
  1. Open a fresh local window session on Windows if the old one expired.
  2. Reattach `join_session_733b69e1bf293c7a` if needed.
  3. Run local TCP validation to `10.66.66.10:8080`.
  4. Submit the same result to backend `minimum-tcp-validation` on `join_session_733b69e1bf293c7a`.
- After state:
  - same-session progression did not close with concrete `minimum_tcp_validation`
  - later same-session backend state moved to:
    - `manager_acceptance.status = claim_failed`
    - detail = `Refusing to claim node docker-desktop because swarm status is down, not ready.`
- Rollback:
  - no session change
  - if the writeback fails, keep the same session and report the exact failure hop
- What this verified:
  - `minimum_tcp_validation` still did not close on this chain before backend state moved to a later claim blocker
  - the session anchor still did not change

### Block 5: same-session backend reverify after transient down/not-ready claim failure

- Before state:
  - canonical chain remains unchanged:
    - `session_id = join_session_733b69e1bf293c7a`
    - `compute_node_id = compute-user-8b7c0b9dd725cbc3`
  - backend later same-session state is:
    - `manager_acceptance.status = claim_failed`
    - detail = `Refusing to claim node docker-desktop because swarm status is down, not ready.`
  - current manager truth from `runtime` side is:
    - `docker node ls -> ukdcii54j1xasu7okv7zgm8s0 Ready`
    - `docker node inspect` already shows canonical labels for:
      - `compute-user-8b7c0b9dd725cbc3`
      - `user_8b7c0b9dd725cbc3`
- Command:
  - repeat same-session backend reverify on `join_session_733b69e1bf293c7a`
  - same payload as Block 3
- After state:
  - same-session recovery completed on the canonical chain:
    - `manager_acceptance.status = matched`
    - `session.status = verified`
  - remaining blocker is no longer claim/reverify on this session
  - remaining blocker is commercialization only:
    - assessment status = `runtime_image_invalid`
    - detail = runtime image missing
- Rollback:
  - no session change
- What this verified:
  - the latest `down/not ready` claim failure was transient relative to current manager state
  - the canonical session recovered to `verified` without changing the session anchor
  - tester should not take new action until `runtime` names an exact commercialization-side move, if any tester-side action is needed

### Block 6: commercialization retrigger after confirming runtime tag is already present locally

- Before state:
  - canonical chain remains unchanged:
    - `session_id = join_session_733b69e1bf293c7a`
    - `compute_node_id = compute-user-8b7c0b9dd725cbc3`
  - commercialization is blocked on the same chain because assessment expects:
    - `registry.example.com/pivot/runtime:python-gpu-v1`
  - direct tester verification on manager shows the required local tag is already present:
    - `docker image inspect managed-runtime-test:local --format '{{.Id}} {{json .Config.Labels}}'`
      - `sha256:4fdad3abde037df984e9f164b59b88ccd7a7ad41e4341ffea7b93a5a5ee9beb4`
      - required runtime labels present
    - `docker image inspect registry.example.com/pivot/runtime:python-gpu-v1 --format '{{.Id}}'`
      - `sha256:4fdad3abde037df984e9f164b59b88ccd7a7ad41e4341ffea7b93a5a5ee9beb4`
    - both refs report the same `RepoTags`:
      - `managed-runtime-test:local`
      - `registry.example.com/pivot/runtime:python-gpu-v1`
  - `runtime` explicitly confirmed Block 6 step 1 should be treated as already satisfied on this same chain
- Command:
  - no tester-side manager mutation executed
  - no repeat `docker tag` was run
  - `runtime` proceeds directly to same-session commercialization retrigger for `join_session_733b69e1bf293c7a`
- After state:
  - local manager has the exact assessment tag:
    - `registry.example.com/pivot/runtime:python-gpu-v1`
    - points to contract-valid image id `sha256:4fdad3abde037df984e9f164b59b88ccd7a7ad41e4341ffea7b93a5a5ee9beb4`
  - same-session commercialization retrigger completed on:
    - `join_session_733b69e1bf293c7a`
  - latest same-chain assessment:
    - `assessment_0f118de7625f0bec`
    - `assessment_status = sellable`
    - `runtime_image_validation.validation_status = validated`
  - `apply_result = {"status":"listed","offer_id":"offer_76fff26fa2692634","compute_node_id":"compute-user-8b7c0b9dd725cbc3"}`
  - `/api/v1/offers` contains listed non-seed offer:
    - `offer_76fff26fa2692634`
    - `compute_node_id = compute-user-8b7c0b9dd725cbc3`
- Rollback:
  - none on tester side because no new manager mutation was performed for Block 6 step 1
- What this verified:
  - the current commercialization blocker is not the absence of the required local runtime tag on manager
  - tester correctly avoided an unnecessary retag mutation on the canonical chain
  - same-session commercialization recovered on the unchanged canonical session
  - the canonical chain now carries the commercialization facts needed for Stage1 closeout:
    - `assessment_status = sellable`
    - listed real offer exists for `compute-user-8b7c0b9dd725cbc3`

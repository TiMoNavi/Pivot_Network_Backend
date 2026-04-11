# CCCC Stage7 Tester Resilience Log

更新时间：`2026-04-11 13:31:40 CST` (`2026-04-11 05:31:40 UTC`)

## Scope

- 只服务于 `Stage7`
- 只验证当前 buyer 路径在真实链路上的韧性表现
- 只锚定到 Stage6 已真实出现过的扰动场景：
  - runtime reprovision churn
  - temporary gateway -> runtime upstream timeout
  - short availability drops
- 不扩散到新功能

## Real Chain Under Test

- `order_5d1236d1338ac6ab`
- `grant_a84b49a685609153`
- `runtime_session_bd6eab1e6279291f`

## Current Stage7 Position

- Scenario 1 已冻结为已完成证据：
  - data-plane readability 在基础设施恢复后自动回来
  - buyer 本地 control-plane state 仍需一次显式 `runtime-sessions/refresh`
  - refresh 后未观察到残余 degradation
- 当前只等待 Scenario 2 的 runtime 扰动窗口
- 仍锁定同一条真实链，不自行注入故障

## Baseline

### Baseline 1: current buyer-side Linux state before first disturbance

- Before state:
  - Stage6/Stage5 已证明这条真实链可用
  - Stage7 需要以同一条 buyer/runtime 链为基线观察扰动期间的 buyer 侧表现
- Commands:

```http
POST http://127.0.0.1:8912/local-api/window-session/open
POST http://127.0.0.1:8912/local-api/auth/login
POST http://127.0.0.1:8912/local-api/runtime/attach-active-grant
GET  http://127.0.0.1:8912/local-api/runtime/current
POST http://127.0.0.1:8912/local-api/runtime-shell/open
```

- After state:
  - local Linux buyer session opened successfully
  - buyer login succeeded for:
    - `stage2-buyer-a341c1804963@example.com`
    - `user_13e35642ec9f9f57`
  - active grant attach bound local state to:
    - `grant_a84b49a685609153`
    - `runtime_session_bd6eab1e6279291f`
  - current runtime access plan is ready for:
    - shell
    - workspace
    - task
  - shell resolution returns:
    - `http://10.66.66.1:32080/shell/`
- Rollback:
  - none yet; baseline only
- What this verified:
  - buyer-side baseline is healthy enough to observe the next real disturbance on the same chain

## Planned Disturbance Window

### Scenario 1: same-session reprovision churn via runtime-side bundle remove + same-key redeem

- Runtime-owned disturbance:
  - `POST /swarm/runtime-session-bundles/remove` for `runtime_session_bd6eab1e6279291f`
  - then immediate `POST /api/v1/access-grants/redeem` on `grant_a84b49a685609153`
  - use the existing lease key `Ewc6us66x8RJZc7xEaH0eAxjQBS2k0rEU0U4SAJyHB0=`
  - backend should reuse the same `runtime_session_id`
  - runtime should force same-session bundle teardown/recreate without changing buyer lease semantics
- Before-state anchor from runtime:
  - `GET /api/v1/runtime-sessions/runtime_session_bd6eab1e6279291f -> status=ready, runtime_bundle_status=running`
  - overlay network currently `10.0.21.0/24`
  - runtime task is `Running`
  - gateway task is `Running`
  - direct gateway `/health` is `200 OK`
  - current lease key on the session is `Ewc6us66x8RJZc7xEaH0eAxjQBS2k0rEU0U4SAJyHB0=`
- What tester will capture:
  - buyer sees what during the drop
  - whether local UI/API degrades cleanly
  - whether recovery is automatic
  - or whether manual retry is still required

## Scenario 1 Result

### Scenario 1A: disturbance window and degraded buyer-visible state

- Runtime-side disturbance facts:
  - adapter remove started:
    - `2026-04-11T04:57:00.449Z`
  - same-key redeem started:
    - `2026-04-11T04:57:04.308Z`
  - `/health` first went bad:
    - `2026-04-11T04:57:03.421Z`
  - by:
    - `2026-04-11T04:58:43.766Z`
    the chain was still degraded with:
    - backend `status = allocating`
    - `runtime_bundle_status = allocated`
    - no overlay network
    - no runtime / gateway services present
- Buyer-side degraded snapshot captured on the same chain:
  - local `runtime_session.status = allocating`
  - local `runtime_bundle_status = allocated`
  - local `wireguard_state.status = up`
  - shell URL still resolves from the cached plan:
    - `http://10.66.66.1:32080/shell/`
- What this verified:
  - degradation is real on the existing buyer path
  - buyer still sees cached session/shell material while backend/runtime truth is degraded
  - recovery was not automatic by the time runtime declared the disturbance window still bad

### Scenario 1B: recovery-half verification on the same chain

- Exact recovery point from runtime:
  - manual close-equivalent on stuck session row committed:
    - `2026-04-11T05:03:05.033Z`
  - same-key redeem on `grant_a84b49a685609153` started:
    - `2026-04-11T05:03:05.033Z`
    and returned `200` by:
    - `2026-04-11T05:03:09.075Z`
  - backend returned to:
    - `status = ready`
    - `runtime_bundle_status = running`
    by:
    - `2026-04-11T05:03:27.355Z`
  - gateway `/health` back to:
    - `200`
  - runtime + gateway services both:
    - `Running`
  - overlay restored on:
    - `10.0.22.0/24`
  - same buyer lease key restored:
    - `Ewc6us66x8RJZc7xEaH0eAxjQBS2k0rEU0U4SAJyHB0=`

- Buyer-side recovery verification commands:

```http
POST http://127.0.0.1:8912/local-api/window-session/open
POST http://127.0.0.1:8912/local-api/auth/login
POST http://127.0.0.1:8912/local-api/runtime/attach-active-grant
GET  http://127.0.0.1:8912/local-api/runtime/current
POST http://127.0.0.1:8912/local-api/runtime-shell/open
GET  http://127.0.0.1:8912/local-api/workspace/status
POST http://127.0.0.1:8912/local-api/runtime-sessions/refresh
GET  http://127.0.0.1:8912/local-api/runtime/current
GET  http://127.0.0.1:8912/local-api/workspace/status
POST http://127.0.0.1:8912/local-api/tasks/submit
GET  http://127.0.0.1:8912/local-api/tasks/{task_id}/logs
```

- Buyer-side recovery observations:
  - Before manual retry:
    - local runtime state was still stale:
      - `runtime_session.status = allocating`
      - `runtime_bundle_status = allocated`
    - shell URL was still present and resolvable from local plan
    - `GET /local-api/workspace/status -> 200`
      - `workspace_root = /workspace`
      - `files = []`
  - Manual retry used:
    - `POST /local-api/runtime-sessions/refresh`
  - After manual retry:
    - local runtime state updated to:
      - `runtime_session.status = ready`
      - `runtime_bundle_status = running`
      - `recent_error_summary = []`
    - `GET /local-api/workspace/status -> 200`
    - minimal task succeeded:
      - command = `echo stage7-recovered && pwd && ls -1`
      - `exit_code = 0`
      - stdout:
        - `stage7-recovered`
        - `/workspace`
      - stderr empty

- Recovery characterization:
  - What came back automatically:
    - buyer tunnel/readability was good enough that `workspace/status` returned `200` again on the same chain before any local refresh
    - shell URL remained available from the existing client state
  - What needed manual retry:
    - local Buyer_Client control-plane/runtime state did not self-heal from `allocating/allocated` back to `ready/running`
    - one explicit `runtime-sessions/refresh` was needed to restore the local state model before confidently continuing task use
  - What remained degraded after that:
    - no additional buyer-visible degradation was observed in this verification pass after the manual refresh

## Scenario 2 Result

### Scenario 2A: runtime-side bounded interruption package on the same chain

- Runtime-owned disturbance:
  - `docker service scale runtime-runtime-session-bd6eab1e6279291f=0`
  - short hold
  - `docker service scale runtime-runtime-session-bd6eab1e6279291f=1`
- Runtime-side timing package:
  - before healthy anchor:
    - `2026-04-11T05:11:53.146Z`
    - backend `ready/running`
    - overlay `10.0.22.0/24`
    - `/health = 200`
    - runtime `1/1`
    - gateway `1/1`
  - disturbance start:
    - `2026-04-11T05:11:53.970Z`
  - first bad `/health`:
    - `2026-04-11T05:11:56.604Z`
    - `502`
  - backend first left ready:
    - `2026-04-11T05:11:59.487Z`
    - `allocating/provisioning`
  - scale back to `1`:
    - `2026-04-11T05:12:05.209Z`
  - last bad `/health`:
    - `2026-04-11T05:12:22.266Z`
  - first good `/health` again:
    - `2026-04-11T05:12:23.279Z`
  - explicit recovery point:
    - `2026-04-11T05:12:27.132Z`
    - backend back to `ready/running`
    - runtime `1/1`
    - gateway `1/1`
    - overlay unchanged at `10.0.22.0/24`
- Runtime-side outage shape:
  - gateway logs showed upstream-only failures:
    - `connect: connection refused`
    - `no route to host`
    to:
    - `10.0.22.2:7681`
  - repeated clean run used for direct buyer-local capture:
    - scale-down issued:
      - `2026-04-11T05:19:11.811Z`
    - first bad runtime-side signal:
      - `2026-04-11T05:19:15.517Z`
      - same timestamp for first bad `/health = 502`
      - same timestamp for first backend non-ready transition `allocating/provisioning`
    - scale-up issued:
      - `2026-04-11T05:19:27.019Z`
    - first good `/health` again:
      - `2026-04-11T05:19:46.658Z`
    - explicit recovery point:
      - `2026-04-11T05:19:50.401Z`
    - same-chain invariants held:
      - overlay stayed `10.0.22.0/24`
      - gateway stayed `1/1`
      - runtime returned to `1/1`
      - backend returned to `ready/running`

### Scenario 2B: direct buyer-visible during-outage sample on the repeated bounded interruption

- Commands:

```http
POST http://127.0.0.1:8912/local-api/window-session/open
POST http://127.0.0.1:8912/local-api/auth/login
GET  http://127.0.0.1:8912/local-api/auth/me
GET  http://127.0.0.1:8912/local-api/access-grants/active
POST http://127.0.0.1:8912/local-api/runtime/attach-active-grant
GET  http://127.0.0.1:8912/local-api/runtime/current
GET  http://127.0.0.1:8912/local-api/workspace/status
POST http://127.0.0.1:8912/local-api/tasks/submit
```

- During-outage sample:
  - window session opened:
    - `a3934fa5-146f-4481-bfef-826111bf7457`
  - same buyer login remained valid:
    - `stage2-buyer-a341c1804963@example.com`
    - `user_13e35642ec9f9f57`
  - direct buyer-local bad sample landed at:
    - `2026-04-11T05:19:38.020954Z`
  - `GET /local-api/runtime/current -> 200`
    - top-level local `runtime_session.status = ready`
    - top-level local `runtime_bundle_status = running`
    - but attached order / grant truth inside the same payload had already shifted to:
      - `current_order.runtime_bundle_status = provisioning`
      - `current_access_grant.connect_material_payload.runtime_session_status = allocating`
      - `current_access_grant.connect_material_payload.runtime_bundle_status = provisioning`
  - `GET /local-api/workspace/status -> 502`
    - `code = workspace_status_failed`
    - detail shows:
      - `Server error '502 Bad Gateway'`
      - target URL:
        - `http://10.66.66.1:32080/api/workspace/status`
  - one direct task attempt during the bad window at:
    - `2026-04-11T05:19:41.032599Z`
    returned:
    - `POST /local-api/tasks/submit -> 502`
    - `code = task_submit_failed`
    - detail shows:
      - `Server error '502 Bad Gateway'`
      - target URL:
        - `http://10.66.66.1:32080/api/exec`
  - runtime corroboration on the same chain:
    - gateway logs recorded the buyer-lane
      - `GET /api/workspace/status`
      - `POST /api/exec`
      during the same bad window
    - both timed out to upstream:
      - `10.0.22.2:7681`
    - both returned:
      - `502`

### Scenario 2C: buyer-side recovery verification after the same bounded interruption

- Recovery-side commands:

```http
GET  http://127.0.0.1:8912/local-api/runtime/current
GET  http://127.0.0.1:8912/local-api/workspace/status
POST http://127.0.0.1:8912/local-api/tasks/submit
```

- After-recovery sample:
  - recovery poll landed at:
    - `2026-04-11T05:19:46.149896Z`
  - local `runtime/current` was already back to:
    - `status = ready`
    - `runtime_bundle_status = running`
  - `GET /local-api/workspace/status -> 200`
    - `workspace_root = /workspace`
    - `files = []`
  - one direct post-recovery task attempt at:
    - `2026-04-11T05:19:46.341018Z`
    succeeded:
    - `POST /local-api/tasks/submit -> 200`
    - `task_id = 3722e1d8-e343-4565-be9f-f8bc299580dc`
    - command = `echo stage7-s2-after && pwd`
    - `status = succeeded`
    - `exit_code = 0`
    - stdout:
      - `stage7-s2-after`
      - `/workspace`

### Scenario 2 Recovery Characterization

- What buyer sees during the bounded outage:
  - local control-plane read `runtime/current` does not fail hard; it stays readable at `200`
  - but the data plane degrades cleanly:
    - `workspace/status` fails with `502`
    - task execution fails with `502`
  - local runtime model is partially stale/partially drifting during the outage:
    - top-level `runtime_session` still says `ready/running`
    - nested order / grant truth has already moved to `allocating/provisioning`
- What came back automatically after runtime scale-up:
  - `runtime/current` returned to a clean `ready/running`
  - `workspace/status` returned to `200`
  - task execution succeeded again on the same session
- What needed manual retry:
  - none on the buyer side for Scenario 2
- What remained degraded after recovery:
  - no residual buyer-visible degradation was observed after the runtime service came back

## Scenario 3 Result

### Scenario 3A: bounded network-instability package on the same chain

- Runtime-owned disturbance:
  - inside the live gateway container netns only
  - temporary random-drop rule on upstream runtime VIP:
    - `OUTPUT -d 10.0.22.2/32 -p tcp --dport 7681 -m statistic --mode random --probability 0.30 -j DROP`
- Same-chain invariants:
  - session id unchanged:
    - `runtime_session_bd6eab1e6279291f`
  - lease unchanged
  - overlay stayed:
    - `10.0.22.0/24`
  - runtime service stayed present:
    - `1/1`
  - gateway service stayed present:
    - `1/1`
  - this was not a reprovision and not a service removal
- Runtime-side exact window:
  - rule inserted:
    - `2026-04-11T05:28:59.239Z`
  - first backend non-ready sample:
    - `2026-04-11T05:29:02.654Z`
    - `allocating/provisioning`
  - first bad `/health`:
    - `2026-04-11T05:29:06.208Z`
  - last bad `/health`:
    - `2026-04-11T05:29:13.654Z`
  - first good `/health` after a bad sample:
    - `2026-04-11T05:29:15.499Z`
  - rule removed:
    - `2026-04-11T05:29:17.343Z`
  - explicit recovery point:
    - `2026-04-11T05:29:17.611Z`
  - runtime-side recovery was automatic:
    - no manual runtime retry

### Scenario 3B: buyer-side live sampling on the same chain

- Commands:

```http
POST http://127.0.0.1:8912/local-api/window-session/open
POST http://127.0.0.1:8912/local-api/auth/login
POST http://127.0.0.1:8912/local-api/runtime/attach-active-grant
GET  http://127.0.0.1:8912/local-api/runtime/current
GET  http://127.0.0.1:8912/local-api/workspace/status
POST http://127.0.0.1:8912/local-api/tasks/submit
POST http://127.0.0.1:8912/local-api/window-session/heartbeat
```

- Before-window buyer baseline:
  - first healthy sample after binding the same chain:
    - `2026-04-11T05:27:57.689873Z`
  - `GET /local-api/runtime/current -> 200`
    - top-level `status = ready`
    - top-level `runtime_bundle_status = running`
    - nested order / grant truth also:
      - `running`
      - `ready`
      - `running`
  - `GET /local-api/workspace/status -> 200`
    - `workspace_root = /workspace`
  - first sampled task succeeded:
    - `task_id = 4aafa814-5548-444c-8441-2f387efed86b`
    - `exit_code = 0`

- During-window buyer-visible degradation:
  - direct buyer-local failure sample 1:
    - `2026-04-11T05:29:02.374323Z`
    - `GET /local-api/runtime/current -> 200`
      - top-level still:
        - `status = ready`
        - `runtime_bundle_status = running`
      - nested order / grant truth also still sampled as:
        - `running`
        - `ready`
        - `running`
    - `GET /local-api/workspace/status -> 502`
      - `code = workspace_status_failed`
  - direct buyer-local success sample during the same instability window:
    - `2026-04-11T05:29:04.673034Z`
    - `GET /local-api/workspace/status -> 200`
    - sampled task also succeeded:
      - `task_id = 87271087-10dd-40c8-850d-0175ce2bef1e`
      - `exit_code = 0`
  - direct buyer-local failure sample 2:
    - `2026-04-11T05:29:10.021847Z`
    - `GET /local-api/runtime/current -> 200`
      - top-level still:
        - `status = ready`
        - `runtime_bundle_status = running`
    - `GET /local-api/workspace/status -> 502`
      - `code = workspace_status_failed`

- Sampling summary across the same window:
  - `runtime/current` top-level `ready/running` samples:
    - `54 / 54`
  - `workspace/status`:
    - `200` on `52` samples
    - `502` on `2` samples
  - sampled `tasks/submit`:
    - succeeded on `15 / 15`
    - no sampled task failure was observed

- Runtime corroboration for the same window:
  - backend truth itself flapped to:
    - `allocating/provisioning`
  - gateway logs showed buyer-lane `/api/workspace/status` timing out upstream and returning `502`
  - runtime-side probes to workspace/task still had some `200` responses, but with elevated latency:
    - roughly `0.6s` to `1.08s`

### Scenario 3C: buyer-side after-window verification

- After-recovery spot-check commands:

```http
POST http://127.0.0.1:8912/local-api/window-session/open
POST http://127.0.0.1:8912/local-api/auth/login
POST http://127.0.0.1:8912/local-api/runtime/attach-active-grant
GET  http://127.0.0.1:8912/local-api/runtime/current
GET  http://127.0.0.1:8912/local-api/workspace/status
POST http://127.0.0.1:8912/local-api/tasks/submit
```

- After state:
  - after-window buyer sample landed at:
    - `2026-04-11T05:30:28.729783Z`
  - `GET /local-api/runtime/current -> 200`
    - top-level:
      - `status = ready`
      - `runtime_bundle_status = running`
    - nested order / grant truth also:
      - `running`
      - `ready`
      - `running`
  - `GET /local-api/workspace/status -> 200`
    - `workspace_root = /workspace`
  - sampled post-recovery task succeeded:
    - `task_id = 00d77f27-1710-42ff-8bb9-b9a3ab1fec55`
    - `exit_code = 0`

### Scenario 3 Recovery Characterization

- What degraded under unstable connectivity while services stayed present:
  - buyer data plane degraded partially, not totally:
    - `workspace/status` intermittently flipped `200 <-> 502`
  - backend/runtime truth flapped underneath, but the buyer local control-plane readout stayed superficially healthy:
    - sampled `runtime/current` remained `200`
    - sampled top-level `runtime_session.status` remained `ready`
    - sampled top-level `runtime_bundle_status` remained `running`
- What remained usable:
  - sampled `tasks/submit` remained usable in this window:
    - `15 / 15` sampled task attempts succeeded
  - `runtime/current` remained readable throughout the window
  - `workspace/status` was degraded intermittently, not permanently
- What recovered automatically:
  - after the rule was removed and runtime declared the recovery point, buyer-visible workspace and task use were healthy again on the same chain
  - no buyer-side `runtime-sessions/refresh` or other retry step was needed
- What remained degraded after recovery:
  - no residual buyer-visible degradation was observed in the post-window sample

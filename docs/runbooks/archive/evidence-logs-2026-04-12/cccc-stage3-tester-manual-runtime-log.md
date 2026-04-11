# CCCC Stage3 Tester Manual Runtime Log

更新时间：`2026-04-11 06:06:43 CST` (`2026-04-10 22:06:43 UTC`)

## Scope

- 只服务于 `Stage3`
- 只记录真实 grant 手工路径的验证事实
- 当前目标链固定为：
  - `offer_76fff26fa2692634`
  - `order_5d1236d1338ac6ab`
  - `grant_a84b49a685609153`
  - `runtime_session_bd6eab1e6279291f`
- 不进入 `Buyer_Client` 实现
- 不扩散到 `Stage4`

## Current Chain Status

- Stage2 真实 buyer 交易链已经通过
- Stage3 real grant/runtime-session chain 已被真实使用并留证：
  - `order_5d1236d1338ac6ab`
  - `grant_a84b49a685609153`
  - `runtime_session_bd6eab1e6279291f`
- same-session runtime truth:
  - `GET /runtime-sessions/runtime_session_bd6eab1e6279291f -> status = ready`
  - `runtime_bundle_status = running`
  - runtime service current task = `Running`
  - gateway current task = `Running`
  - buyer WireGuard lease metadata:
    - `status = applied`
    - `client_address = 10.66.66.201`
- manual Stage3 path evidence now exists on the unchanged chain:
  - real buyer-side WireGuard handshake observed
  - shell health reachable through the tunnel
  - minimal task completed with `exit_code = 0`
- tester remains confirm-only unless reviewer or lead asks for more evidence

## Manual-Action Ledger

### Block 7: smallest worker-side image-availability fix on the existing Stage3 runtime-session chain

- Before state on worker `docker-desktop`:
  - `docker image inspect registry.example.com/pivot/runtime:python-gpu-v1`:
    - no such image
  - `docker service ps runtime-runtime-session_bd6eab1e6279291f`
    - service name in practice: `runtime-runtime-session-bd6eab1e6279291f`
    - repeated `Rejected`
    - detail: `No such image: registry.example.com/pivot/runtime:python-gpu-v1`
  - worker already has:
    - `managed-runtime-test:local`
    - expected runtime contract labels present
- Command:
  - executed by `runtime`, not by `tester`:

```bash
docker tag managed-runtime-test:local registry.example.com/pivot/runtime:python-gpu-v1
```

- After state:
  - worker image fix applied
  - `registry.example.com/pivot/runtime:python-gpu-v1` is now available on the worker
  - same grant/session chain stays unchanged
  - next step became same-grant redeem reprovision
- Rollback:

```bash
docker image rm registry.example.com/pivot/runtime:python-gpu-v1
```

- What this verified:
  - this is the smallest worker-side image-availability fix for the existing runtime session chain
  - no new grant
  - no new runtime session
  - no Buyer_Client change

### Block 8: same-grant re-redeem into the existing runtime session chain after worker image fix

- Before state:
  - Stage3 real chain remains unchanged:
    - `order_5d1236d1338ac6ab`
    - `grant_a84b49a685609153`
    - `runtime_session_bd6eab1e6279291f`
  - worker image blocker is cleared by retagging:
    - `managed-runtime-test:local -> registry.example.com/pivot/runtime:python-gpu-v1`
  - backend redeem/runtime-session routes are live
  - same runtime session id is expected to be reprovisioned on re-redeem
- Command family:
  - executed by `runtime`, not by `tester`:
  1. buyer login with the real Stage2 buyer account from the tester log
  2. generate a real local WireGuard keypair
  3. `POST /api/v1/access-grants/redeem` on `grant_a84b49a685609153` with the generated `wireguard_public_key`
- After state:
  - same grant redeemed into existing `runtime_session_bd6eab1e6279291f`
  - redeem reprovision returned `200`
  - current Swarm runtime task is `Running` on `docker-desktop`
  - gateway is up
  - buyer WireGuard lease metadata is present
  - current same-chain blocker is not runtime task absence anymore
  - current same-chain blocker is backend runtime-session truth:
    - backend runtime session still reads `status = failed`
    - `recent_error_summary` still carries earlier rejected-task network errors on the same session
    - error detail includes:
      - `invalid endpoint settings: no configured subnet contains IP address 10.0.4.x`
- Rollback:
  - no new grant
  - no new session
  - if backend truth still fails, keep the same chain and report the exact failure hop
- What this verified:
  - the real grant can be manually redeemed into the existing runtime session chain once the worker image blocker is cleared
  - the next blocker is now same-chain inspect/backend-truth reconciliation, not grant redeem or worker image availability

### Block 9: runtime-owned manual WireGuard, shell, and minimal-task proof on the unchanged Stage3 chain

- Before state:
  - Stage3 real chain remains unchanged:
    - `order_5d1236d1338ac6ab`
    - `grant_a84b49a685609153`
    - `runtime_session_bd6eab1e6279291f`
  - backend runtime session now reads:
    - `status = ready`
    - `runtime_bundle_status = running`
  - runtime service task is running on `docker-desktop`
  - gateway service is running
  - buyer WireGuard lease metadata is present and applied for client address:
    - `10.66.66.201`
- Command family:
  - executed by `runtime`, not by `tester`:
  1. create a host-side temporary buyer netns
  2. add a veth uplink for that buyer netns
  3. create the buyer WireGuard interface inside that netns using the real lease from `runtime_session_bd6eab1e6279291f`
  4. verify shell-agent reachability over the tunnel
  5. run one minimal task via `POST /api/exec`
  6. do not continue using the earlier ad-hoc container package-install path
- After state:
  - same-session runtime truth:
    - `GET /runtime-sessions/runtime_session_bd6eab1e6279291f -> status = ready`
    - `runtime_bundle_status = running`
    - runtime service current task = `Running`
    - gateway current task = `Running`
    - buyer WireGuard lease metadata still:
      - `status = applied`
      - `client_address = 10.66.66.201`
  - buyer-side manual path evidence:
    - executed from isolated local netns:
      - `buyer3`
    - because client and server were co-resident on the same host, endpoint override was used for this local validation only:
      - `10.2.0.3:45182`
    - lease / public key / session chain stayed unchanged
    - `wg show wg3` reported:
      - latest handshake `2 seconds ago`
      - transfer `124 B received, 180 B sent`
    - `curl http://10.66.66.1:32080/health` over the tunnel returned:
      - `{"status":"ok","service":"pivot-shell-agent"}`
    - `POST http://10.66.66.1:32080/api/exec` with:
      - `echo stage3-ok && pwd && ls -1`
      returned:
      - `exit_code = 0`
      - `stdout = "stage3-ok\n/workspace\n"`
      - `stderr = ""`
  - rollback / cleanup completed:
    - temporary buyer netns/veth/WireGuard client state torn down
    - grant/session chain unchanged
- Rollback:
  - tear down the temporary buyer netns
  - tear down its veth uplink
  - remove only its WireGuard interface/config
  - keep the grant/session chain unchanged
- What this verified:
  - the manual Stage3 path can actually use the same runtime session through WireGuard, shell, and one minimal task without Buyer_Client code
  - proof stayed on the unchanged real chain:
    - `order_5d1236d1338ac6ab`
    - `grant_a84b49a685609153`
    - `runtime_session_bd6eab1e6279291f`

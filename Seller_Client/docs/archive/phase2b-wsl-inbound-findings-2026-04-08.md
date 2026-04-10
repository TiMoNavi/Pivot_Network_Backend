# Seller Client Phase 2B WSL Inbound Findings

Date: `2026-04-08`

## Scope Lock

This document records the live findings for the `Phase 2B` Windows seller onboarding blocker on `2026-04-08`.

Current scope is locked to:

- `Windows Host + dedicated WSL Ubuntu Compute + native WireGuard + native Docker Engine`
- the `WSL/Windows inbound exposure` blocker
- the question of whether this path is capable of forming a stable WireGuard-backed Swarm worker

This document is not about:

- backend reachability
- seller auth/session flows
- local seller client shell startup
- Swarm `--advertise-addr` tuning

Those areas were intentionally not treated as the current front blocker.

## Environment Snapshot

- Windows workspace: `D:\AI\Pivot_Client`
- Seller client workspace: `D:\AI\Pivot_Client\seller_client`
- Ubuntu distro: `Ubuntu` on `WSL 2`
- WSL version observed: `2.4.10.0`
- Windows version observed: `10.0.22631.6199`
- Manager public address: `81.70.52.75`
- Manager WireGuard address: `10.66.66.1`
- Seller WireGuard address: `10.66.66.10/32`
- Manager UDP listen port: `45182/udp`

## Findings First

### 1. Mirrored mode imported host tunnel state into Ubuntu and polluted route selection

The Ubuntu compute instance did not come up with a clean mirrored view of only the physical host NIC.

Observed mirrored interfaces inside Ubuntu included:

- `eth3 = 172.23.241.69/17` from the physical host NIC
- `eth9 = 10.66.66.2/32` from host interface `pc-pico-remote`
- `eth10 = 10.66.66.200/32` from host interface `pivot-buyer-c3ba7542`
- additional mirrored tunnel/VPN defaults from `Meta`, `Radmin`, and `ZeroTier`

Before route normalization, `ip route get 81.70.52.75` in Ubuntu resolved to:

```text
81.70.52.75 via 198.18.0.2 dev eth2 src 198.18.0.1
```

That meant WireGuard handshake traffic was leaving from the wrong mirrored host path instead of the physical NIC path.

### 2. After manager routing was pinned to the physical mirrored NIC, the manager did receive current traffic

We added a targeted host route for `81.70.52.75` inside Ubuntu so that manager-bound traffic uses:

```text
81.70.52.75 via 172.23.128.1 dev eth3 src 172.23.241.69
```

Manager-side evidence then showed fresh UDP traffic from the seller public IP:

```text
202.113.184.2:3557 -> 10.2.0.3:45182
10.2.0.3:45182 -> 202.113.184.2:3557
```

This is strong evidence that the seller side was no longer failing purely on outbound route selection.

### 3. Even after outbound correction, Ubuntu WireGuard still did not receive replies

Ubuntu-side `wg show` remained in the same broken state:

- `0 B received`
- send-only transfer growth
- no successful `latest handshake`
- `ping 10.66.66.1` still failed

At the same time, manager-side `wg show` for peer `10.66.66.10/32` still reported an old handshake timestamp instead of a fresh stable handshake.

This means the blocker moved from `wrong egress path` to `WSL/Windows inbound return path still not reaching the Ubuntu WireGuard socket`.

### 4. Ordinary TCP inbound was also not working, so this is not just a WireGuard config problem

Inside Ubuntu, a test listener was successfully started on:

```text
0.0.0.0:38081
```

But inbound tests still failed:

- host to mirrored IP access failed
- manager to seller public IP test port failed
- manager-side TCP probe returned `tcp-closed`
- manager-side HTTP probe timed out

This confirms that the live blocker is not limited to WireGuard cryptokey routing or peer config. The inbound exposure layer itself is not working reliably for ordinary TCP either.

### 5. Hyper-V inbound allow settings and explicit Hyper-V rule were not enough to recover the path

We successfully applied:

- Hyper-V VM firewall `Enabled=True`
- `DefaultInboundAction=Allow`
- `DefaultOutboundAction=Allow`
- `LoopbackEnabled=True`
- `AllowHostPolicyMerge=True`
- explicit Hyper-V rule `Pivot-WSL-Inbound-Allow-All`

Despite that, the network symptoms above remained.

So the current evidence does not support the theory that the blocker is only a missing Windows firewall checkbox.

### 6. The remaining failure pattern matches public WSL mirrored-mode limitations

The current behavior is consistent with public WSL mirrored-mode issues:

- `hostAddressLoopback` key confusion and placement issues
- host IP to WSL service reachability not working as expected
- mirrored mode not fully mirroring all packet classes, especially kernel-socket scenarios like WireGuard

Relevant references:

- Microsoft Learn WSL config docs:
  - <https://learn.microsoft.com/en-us/windows/wsl/wsl-config>
- WSL issue `#10965`:
  - <https://github.com/microsoft/WSL/issues/10965>
- WSL issue `#10841`:
  - <https://github.com/microsoft/WSL/issues/10841>
- WSL issue `#10842`:
  - <https://github.com/microsoft/WSL/issues/10842>
- WSL issue `#11034`:
  - <https://github.com/microsoft/WSL/issues/11034>

This does not prove the platform is impossible in all cases, but it is strong evidence that the current live failure is not just a repo-local misconfiguration.

## Evidence Summary

### Ubuntu-side route evidence

Before normalization, Ubuntu showed multiple defaults, including:

```text
default via 198.18.0.2 dev eth2
default via 172.23.128.1 dev eth3 metric 25
default via 26.0.0.1 dev eth5 metric 9257
default via 25.255.255.254 dev eth7 metric 10034
default via 25.255.255.254 dev eth6 metric 10034
```

After targeted manager route pinning:

```text
81.70.52.75 via 172.23.128.1 dev eth3 src 172.23.241.69
```

### Ubuntu-side WireGuard evidence

Broken state remained:

```text
peer: puGAoUTF0vyha+32vxQ+BBVOWXlCOUzhFoNe5tJ9hyo=
  endpoint: 81.70.52.75:45182
  allowed ips: 10.66.66.1/32
  transfer: 0 B received, <sent bytes only>
```

`ping 10.66.66.1` remained unsuccessful.

### Manager-side evidence

Manager-side `tcpdump` captured fresh UDP traffic from the seller public IP and manager responses:

```text
202.113.184.2:3557 -> 10.2.0.3:45182
10.2.0.3:45182 -> 202.113.184.2:3557
```

But manager-side `wg show` for peer `10.66.66.10/32` still showed an old handshake timestamp instead of a healthy current session.

### TCP listener evidence

Ubuntu listener:

```text
LISTEN 0 5 0.0.0.0:38081 0.0.0.0:* users:(("python3",pid=685,fd=3))
```

Manager-side external probe:

```text
tcp-closed
```

Manager-side HTTP probe:

```text
000
curl: (28) Connection timed out after 5001 milliseconds
```

## Changes Applied During Investigation

### Repo-side script changes

Updated:

- `seller_client/enable_mirrored_wsl.ps1`
- `seller_client/enable_mirrored_no_firewall.ps1`

Changes:

- moved `hostAddressLoopback=true` into the correct `[experimental]` block
- stopped Docker Desktop before `wsl --shutdown` to avoid repeated false-alarm popups

Added:

- `seller_client/normalize_wsl_mirrored_routes.ps1`
- `seller_client/configure_wsl_hyperv_inbound.ps1`

Purpose:

- normalize manager egress routing inside mirrored Ubuntu
- apply or roll back WSL Hyper-V inbound settings and explicit Hyper-V allow rule

### Host runtime changes

Applied on the live machine:

- `.wslconfig` updated to:

```ini
[wsl2]
memory=4GB
swap=1GB
networkingMode=mirrored
firewall=false

[experimental]
hostAddressLoopback=true
```

- Hyper-V VM firewall switched to allow inbound/outbound and loopback
- explicit rule `Pivot-WSL-Inbound-Allow-All` created

## Verification Status

### Passed

- manager route can be pinned to the physical mirrored NIC path
- manager sees current seller UDP traffic after route pinning
- Hyper-V inbound allow settings were successfully applied
- explicit Hyper-V rule was successfully created
- `.wslconfig` syntax was corrected so the `hostAddressLoopback` key no longer belongs to the wrong section

### Still failing

- Ubuntu `wg show` still has no receive bytes
- Ubuntu `ping 10.66.66.1` still fails
- manager does not see a fresh stable handshake for peer `10.66.66.10/32`
- ordinary TCP inbound to Ubuntu listener still fails from outside

## Conclusion

As of `2026-04-08`, the active front blocker remains:

`WSL/Windows inbound exposure on the mirrored-networking path`

The investigation established:

- the issue is not backend reachability
- the issue is not seller client shell startup
- the issue is not ordinary app/session logic
- the issue is not only a missing Hyper-V firewall toggle
- the issue is not only a WireGuard peer config typo

The current evidence supports this narrower conclusion:

`mirrored` can be made to send traffic out on the correct path, but the inbound return path needed for stable WireGuard and ordinary TCP exposure is still not reliable on this live machine.

## Recommended Next Step

Do not move to Swarm `--advertise-addr` yet.

First finish the network-layer decision:

1. Stop treating this as an app-layer or backend-layer blocker.
2. Treat the remaining mirrored inbound problem as platform-level unless new contradictory evidence appears.
3. Keep the approved formal runtime shape:
   - `Windows Host + dedicated WSL Ubuntu Compute + native WireGuard + native Docker Engine`
4. But consider changing the ingress strategy away from direct `mirrored` inbound dependence.
5. Only after the inbound network layer is stable should we resume:
   - worker formation validation
   - manager node identity checks
   - Swarm `--advertise-addr` pinning to the WireGuard IP

## Notes For The Next Handoff

Whoever continues from here should preserve the separation below:

- current blocker:
  - `WSL/Windows inbound exposure`
- next-layer blocker:
  - Swarm advertise address resolving to the wrong IP

Those are different problems and should not be debugged as one blended issue.

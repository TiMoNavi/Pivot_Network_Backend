# CCCC Recommended Team Template

## What the latest official guidance points to

For the latest CCCC line, the official guidance has two stable patterns:

1. `builder + reviewer` is the high-ROI minimal team.
2. For medium-complexity projects, use a foreman-led multi-agent group with clear specialization, explicit ownership, and a shared control plane.

For this repository, the second pattern fits better because the work naturally spans backend business rules, local runtime/bootstrap behavior, and infrastructure/network operations.

## Recommended default for Pivot Network

Use `6` actors total for `phase4 / phase5`:

| actor_id | effective role | ownership |
| --- | --- | --- |
| `lead` | `foreman` | decomposition, shared brief, milestones, integration, final acceptance |
| `platform` | `peer` | platform backend, API contracts, auth, DB, business workflow semantics |
| `buyer` | `peer` | Buyer_Client, buyer MCP, buyer local state, Linux/Windows buyer flow |
| `runtime` | `peer` | Docker Swarm, WireGuard, managed runtime contract, Windows operator validation surface |
| `reviewer` | `peer` | review, regression checks, docs drift, rollout risk |
| `scribe` | `peer` | current-state summaries, human-readable docs, runbook sync |

Why this split works here:

- it matches the repo's real fault lines
- it keeps network/runtime risk away from backend business truth
- it preserves an explicit reviewer lane instead of making review an afterthought
- it adds an explicit documentation lane so humans do not need to reverse-engineer the current state from raw code

## Important version note

In `cccc-pair 0.4.9`, `foreman` is a reserved actor id.  
So the first enabled actor should be `lead`, not `foreman`. It still becomes the effective foreman role when the group starts.

## Recommended startup documents

Use two layers:

1. Repo root `PROJECT.md`
2. Group-level `CCCC_HELP.md`

Suggested usage:

- `docs/runbooks/current-project-state-and-execution-guide.md` holds the front-door project status, architecture, module boundaries, Windows operator entry, and staged execution map
- `PROJECT.md` holds the active phase brief
- `CCCC_HELP.md` holds the active collaboration contract and actor instructions
- `docs/runbooks/cccc-phase4-current-state.md` holds the verified current project state
- `docs/runbooks/cccc-phase4-workplan.md` holds the fixed stage order, target folders, and success standards
- `docs/runbooks/cccc-phase4-task-prompts.md` holds actor kickoff prompts for phase4 / phase5
- `win_romote/windows 电脑ssh 说明.md` holds the verified Windows operator-access facts

Files prepared in this repo:

- `/root/Pivot_network/PROJECT.md`
- `/root/Pivot_network/docs/runbooks/current-project-state-and-execution-guide.md`
- `/root/Pivot_network/CCCC_HELP.md`
- `/root/Pivot_network/docs/runbooks/cccc-phase4-task-prompts.md`
- `/root/Pivot_network/docs/runbooks/cccc-phase4-current-state.md`
- `/root/Pivot_network/docs/runbooks/cccc-phase4-workplan.md`
- `/root/Pivot_network/win_romote/windows 电脑ssh 说明.md`
- `/root/Pivot_network/docs/runbooks/CCCC_HELP.example.md`
- `/root/Pivot_network/.cccc/README.md`

Current local CCCC home:

- `/root/Pivot_network/.cccc/home`

Group prompt override path pattern:

- `/root/Pivot_network/.cccc/home/groups/<group_id>/prompts/CCCC_HELP.md`

## Fresh-group CLI example

```bash
cd /root/Pivot_network
export CCCC_HOME=/root/Pivot_network/.cccc/home
cccc attach .
cccc setup --runtime codex
cccc actor add lead --runtime codex --title Foreman
cccc actor add platform --runtime codex --title "Platform Backend"
cccc actor add buyer --runtime codex --title "Buyer Client"
cccc actor add runtime --runtime codex --title "Runtime & Swarm"
cccc actor add reviewer --runtime codex --title "QA & Review"
cccc actor add scribe --runtime codex --title "State & Docs"
cccc group start
```

## Recommended kickoff message

这一段只适用于 fresh phase-start。
一旦 phase 已经跑起来，后续 actor 指令应以 `docs/runbooks/cccc-phase4-task-prompts.md` 为准。

When starting a real task from zero, send it to `@lead`, not to `@all` first:

```text
@lead 当前只做 phase4 / phase5。
请先读取 PROJECT.md、CCCC_HELP.md、docs/runbooks/cccc-phase4-current-state.md、docs/runbooks/cccc-phase4-workplan.md、docs/runbooks/cccc-phase4-task-prompts.md、Buyer_Client/docs/phase4-buyer-client-implementation-spec-cn.md、win_romote/windows 电脑ssh 说明.md。
先输出当前项目现状摘要、stage 1-6 顺序、owner 分配和每步成功标准，
再把 backend grant/runtime session 分给 @platform，把 Buyer_Client / buyer MCP 分给 @buyer，把 runtime / wireguard / Windows operator 验证面分给 @runtime，
让 @reviewer 做 drift 检查，再让 @scribe 产出给人看的阶段摘要和 Windows 验证记录。
```

## When to temporarily switch the shape

If the sprint is strongly UI/client-heavy, you can temporarily expand the buyer lane further or split `buyer` into `client` and `assistant`.

Preferred temporary variant:

- `lead`
- `platform`
- `client`
- `reviewer`

## Operational note

Official best-practice material prefers putting CCCC behind a safer remote-access layer such as Cloudflare Access or Tailscale Funnel instead of长期裸露 `8848`。  
The direct public port can be used operationally, but it should be treated as a transitional setup rather than the long-term recommended exposure model.

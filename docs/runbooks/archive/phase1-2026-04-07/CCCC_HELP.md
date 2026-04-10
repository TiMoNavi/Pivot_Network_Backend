# Pivot Network CCCC Help

## Phase Lock

- Current scope is `Phase 1` only.
- Current goal is `卖家闭环 + 平台后端`.
- Success anchor is: after `docker swarm join`, manager identifies the seller node by the expected `WireGuard IP`.
- Do not expand into buyer/order/access-grant/runtime-delivery phases unless the user explicitly asks.

## Read This First

Before planning or editing, read:

1. `PROJECT.md`
2. `docs/runbooks/cccc-phase1-current-state.md`
3. `docs/runbooks/cccc-phase1-workplan.md`

Do not start from the full human roadmap file by default.

## Current Project State You Must Respect

- `Plantform_Backend/` already has:
  - `seller_onboarding.py`
  - `seller_onboarding_service.py`
  - `seller_onboarding.py` router
  - `adapter_client.py`
  - `memory_store.py`
- Current backend seller onboarding path is not empty. It already has:
  - `JoinSession`
  - `LinuxHostProbe`
  - `LinuxSubstrateProbe`
  - `ContainerRuntimeProbe`
  - flat `join-complete` ingress
  - `inspect -> claim -> inspect` acceptance flow
- `Seller_Client/` is not empty. It already has:
  - `contracts/phase1.py`
  - `bootstrap/phase1.py`
  - `bootstrap/backend_payloads.py`
  - `layers/*`
  - `docs/phase1-bootstrap-contract.md`
  - `tests/test_phase1_contracts.py`
- `Docker_Swarm Adapter` already has real swarm/wireguard capabilities. Reuse them before inventing anything new.

## Hard Rules

- Use `Linux Host`, `Linux substrate`, and `Container Runtime` as the only phase-1 local layering terms.
- `Linux substrate` is where `WireGuard + Docker Engine + Swarm join` happen.
- Do not treat Swarm state or WireGuard reachability as business truth.
- Do not expose `/adapter-proxy/...` as a formal product API.
- Do not reintroduce seller custom-image upload as a phase-1 mainline.
- Shared contracts default to `platform` ownership. Cross-surface contract changes must go through `lead`.

## Team Shape

- `lead`: decomposition, integration, final acceptance
- `platform`: `Plantform_Backend/`, `Shared/`, backend contracts, onboarding API
- `runtime`: `Seller_Client/`, `Docker_Swarm/`, `wireguard/`, seller bootstrap and runtime operations
- `reviewer`: consistency review, regression scan, docs drift, rollout risk
- `scribe`: current-state summaries, human-readable docs, runbook sync

## @actor: lead

- First output:
  - current project state summary
  - phase-1 step order
  - owner per step
  - success standard per step
- Then split work exactly by the current-state and workplan docs.
- Do not let peers skip the “what exists now” check.

## @actor: platform

- Start from current backend reality, not a blank-slate design.
- Work on the existing seller onboarding surfaces under:
  - `Plantform_Backend/backend_app/schemas/seller_onboarding.py`
  - `Plantform_Backend/backend_app/services/seller_onboarding_service.py`
  - `Plantform_Backend/backend_app/api/v1/seller_onboarding.py`
  - `Plantform_Backend/backend_app/storage/memory_store.py`
  - `Plantform_Backend/tests/test_seller_onboarding_api.py`
- Phase-1 focus must center on:
  - `JoinSession`
  - `LinuxHostProbe`
  - `LinuxSubstrateProbe`
  - `ContainerRuntimeProbe`
  - `NodeProbeSummary`
  - `JoinCompleteWrite`
  - `ManagerAcceptance`

## @actor: runtime

- Start from current runtime reality, not an assumed existing seller bootstrap app.
- `Seller_Client/` already has a phase-1 contract/bootstrap/exporter baseline. Do not rebuild it from scratch.
- Reuse `Docker_Swarm Adapter` current capabilities:
  - `join-material`
  - `inspect`
  - `claim`
  - `wireguard`
- Keep the runtime side focused on:
  - bootstrap flow
  - probe points
  - runtime-local nested draft
  - backend flat exporter/mapping
  - rollback notes

## @actor: reviewer

- First verify whether the proposed work matches the actual repo state.
- Check directory reality before checking abstract architecture.
- Lead with findings if someone:
  - ignores the current backend skeleton
  - assumes Seller_Client already exists
  - redesigns Adapter control flow unnecessarily
  - drops the `WireGuard IP` success anchor

## @actor: scribe

- Own human-readable current-state summaries and operator-facing documentation cleanup.
- Do not invent implementation facts; summarize only verified repo state or cited decisions.
- Preferred outputs:
  - current state summaries for humans
  - docs drift fixes
  - runbook cleanup
  - concise status snapshots after a phase milestone
- When implementation and docs diverge, ask `lead` which one is canonical before rewriting prose around it.

# Pivot Network CCCC Phase 1 Brief

## Goal

This `PROJECT.md` is the active CCCC brief for `Phase 1` only.

Current goal:

- 先完成 `卖家闭环 + 平台后端`

Success anchor:

- `docker swarm join` 之后，manager 识别到的是预期 `WireGuard IP`

## Read Order

CCCC should read these files in this order before planning or editing:

1. `PROJECT.md`
2. `CCCC_HELP.md`
3. `docs/runbooks/cccc-phase1-current-state.md`
4. `docs/runbooks/cccc-phase1-workplan.md`

Do not default to the full human roadmap file `个人算力交易平台MVP技术方案.md` for this phase.

## Phase 1 Scope

Only these work items are in scope:

1. Define and align `JoinSession`
2. Define and align `LinuxHostProbe`
3. Define and align `LinuxSubstrateProbe`
4. Define and align `NodeProbeSummary`
5. Add seller onboarding API under `/api/v1/seller/onboarding/...`
6. Add seller bootstrap structure under:
   - `Linux Host`
   - `Linux substrate`
   - `Container Runtime`
7. Keep `detect -> prepare -> install -> repair` as the only bootstrap sequence in Phase 1

## Current Surfaces

- `Plantform_Backend/`
- `Seller_Client/`
- `Docker_Swarm/`
- `Shared/`
- `docs/`

## Current Working Rule

- Tell CCCC what exists now, then tell it what to add next.
- Do not ask CCCC to infer current module state from abstract architecture language.
- Do not expand to buyer/order/access-grant later phases unless the user explicitly asks.

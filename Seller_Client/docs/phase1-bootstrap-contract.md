# Seller Client Phase 1 Bootstrap Contract

## Scope Lock

This surface is locked to `Phase 1` only.

- Layers: `Linux Host`, `Linux substrate`, `Container Runtime`
- Sequence: `detect -> prepare -> install -> repair`
- Success anchor: `join 后 manager 识别到预期 WireGuard IP`
- Exclusions: no later-phase order/access flows, no Windows terms

## Directory Layout

- `seller_client_app/contracts/`
  - runtime-local draft contracts that can be serialized for backend consumption
- `seller_client_app/layers/`
  - per-layer probe points, stage operations, and rollback checkpoints
- `seller_client_app/bootstrap/`
  - phase-1 planner, runtime-local `join-complete` payload builder, and flat backend payload exporter
- `bootstrap/`
  - local entrypoint plus example `JoinMaterialEnvelope` input
- `tests/`
  - contract and state-machine coverage

## Adapter Boundary

Phase 1 keeps the infrastructure control chain fixed:

- `seller client`
  - runs local `detect -> prepare -> install -> repair`
  - records local probes and local join execution facts
  - submits `join-complete` to backend
- `backend`
  - requests `join-material`
  - runs `adapter_client.inspect / claim / inspect`
  - decides final acceptance
- `Docker Swarm Adapter`
  - stays behind `backend.adapter_client`
  - provides `join-material`, `inspect`, `claim`, and `wireguard` support

Seller client does not call Adapter directly.
Phase 1 assumes no Adapter `verify` endpoint and does not add one.

## Contracts

### `JoinMaterialEnvelope`

Runtime input draft built from backend-issued material.

Key fields:

- `join_session_id`
- `seller_user_id`
- `manager_addr`
- `manager_port`
- `swarm_join_command`
- `recommended_compute_node_id`
- `expected_swarm_advertise_addr`
- `expected_wireguard_ip`
- `required_labels`

### `LinuxHostProbe`

Local host facts only.

Key fields:

- `join_session_id`
- `seller_user_id`
- `reported_phase`
- `os_type`
- `hostname`
- `machine_id`
- `kernel_release`
- `architecture`
- `cpu_cores`
- `memory_gb`
- `disk_free_gb`
- `observed_local_ips`
- `probe_points`

### `LinuxSubstrateProbe`

WireGuard + Docker Engine + swarm join readiness facts.

Key fields:

- `join_session_id`
- `seller_user_id`
- `reported_phase`
- `wireguard_available`
- `wireguard_interface`
- `expected_wireguard_ip`
- `observed_wireguard_ip`
- `docker_available`
- `docker_version`
- `swarm_join_ready`
- `probe_points`

### `ContainerRuntimeProbe`

Runtime-local post-join correlation hints.

Key fields:

- `join_session_id`
- `seller_user_id`
- `runtime_name`
- `runtime_socket_access`
- `swarm_membership_state`
- `observed_swarm_advertise_addr`
- `swarm_node_id_hint`
- `probe_points`

### `NodeProbeSummary`

Aggregate runtime-local draft for backend consumption.

Key fields:

- `join_session_id`
- `seller_user_id`
- `bootstrap_sequence`
- `expected_wireguard_ip`
- `expected_swarm_advertise_addr`
- `linux_host`
- `linux_substrate`
- `container_runtime`
- `rollback_checkpoints`

### `JoinCompletePayload`

This payload is the runtime write shape for `join-complete`.

Stable blocks:

- `local_execution`
  - whether the join command ran
  - local result
  - `reported_phase`
  - observed local `WireGuard IP`
  - observed local swarm advertise address
  - optional local swarm node hint
- `backend_locator`
  - `compute_node_id`
  - optional `node_ref`
  - hostname
  - machine-id
  - observed addresses
  - required labels

- `node_probe_summary`
  - local `Linux Host` / `Linux substrate` / `Container Runtime` summary
  - rollback checkpoints
  - expected addressing hints copied from join-material

`expected_wireguard_ip` remains platform-owned from join-material / session state.
Runtime may report observed `WireGuard IP`, but that observation does not redefine the expected value.

Backend acceptance remains outside this runtime write payload.

## Backend Flat Export

Backend ingress currently stays flat and endpoint-shaped:

- `linux-host-probe`
- `linux-substrate-probe`
- `container-runtime-probe`
- `join-complete`

Current backend `JoinCompleteWrite` is a flat contract. Official ingress fields are:

- `reported_phase`
- `node_ref`
- `compute_node_id`
- `observed_wireguard_ip`
- `observed_advertise_addr`
- `observed_data_path_addr`
- `notes`
- `raw_payload`

Nested `local_execution / backend_locator` are runtime-local draft blocks, not the formal backend write shape.

Runtime keeps the nested `NodeProbeSummary` / `JoinCompletePayload` draft locally. The translation boundary in `seller_client_app/bootstrap/backend_payloads.py` is runtime-owned and must map runtime-local facts into the official flat backend ingress.

Current mapping rules are locked for phase 1:

- `join-complete` backend ingress uses flat fields sourced from `local_execution` and `backend_locator`
- nested `node_probe_summary` stays runtime-local and can only appear under `raw_payload` provenance
- `linux-substrate-probe` continues carrying `cpu_cores / memory_gb / disk_free_gb` because current backend `resource_summary` reads them there

## Stage Mapping

### `detect`

- capture `LinuxHostProbe`
- capture `LinuxSubstrateProbe`
- capture `ContainerRuntimeProbe` daemon-access baseline

### `prepare`

- validate privilege path
- stage WireGuard + Docker prerequisites
- create rollback checkpoints before local join

### `install`

- run backend-provided `swarm_join_command`
- capture runtime-local post-join hints
- build `join-complete` local facts

### `repair`

- reconcile local WireGuard / swarm / runtime mismatch
- re-run probes
- emit rollback guidance instead of inventing a new control chain

## Rollback Checkpoints

Current checkpoints:

- `host.prepare-context`
- `substrate.prepare-network`
- `substrate.join-worker`
- `substrate.repair-network`
- `runtime.post-join-state`

These checkpoints carry:

- trigger condition
- touched resources
- rollback actions
- whether manual intervention is required

## Alignment Points With `@platform`

Current runtime position after lead clarification:

- `JoinCompletePayload.local_execution` and `backend_locator` stay provisionally frozen unless `@platform` reports a concrete landing conflict
- `NodeProbeSummary` remains local-only and does not carry backend acceptance state
- flat backend ingress stays separate from the runtime-local nested draft; exporter code owns that translation boundary
- `reported_phase` is frozen to `detect / prepare / install / repair`
- `backend_locator` returns `compute_node_id` as the primary stable locator and `node_ref` as optional fallback
- `ContainerRuntimeProbe` remains a separate schema in phase 1

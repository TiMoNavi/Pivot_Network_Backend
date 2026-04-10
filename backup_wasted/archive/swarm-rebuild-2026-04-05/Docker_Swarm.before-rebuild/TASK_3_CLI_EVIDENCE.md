# Task 3 CLI Evidence

This file closes task 3 for the current `Swarm Adapter` mainline scope: a reproducible minimal CLI chain for current node operations, plus the evidence and honest stop point observed on the real Swarm as of 2026-03-24.

## Scope Boundary

- In scope: worker join info, node list/status, single-node inspect, safe compute-node claim, and guarded `availability` mutation for a non-control-plane worker.
- Out of scope: backend `docker_cli` execution, runtime service / benchmark service real implementation, and `remove_swarm_node()` destructive flow.
- Red lines held here: do not mutate `cw-NF5588M4` / manager / control-plane, do not pretend the backend already has Docker CLI/socket access, and do not record unverified hardware numbers as platform truth.

## Reproducible Command Chain

Run these commands from the repo root on the current Swarm manager host:

```bash
cd /home/cw/ybj/Pivot_backend_build_team/Docker_swarm
./scripts/print-worker-join.sh
./scripts/status.sh
./scripts/inspect-node.sh seller-local-001
./scripts/label-compute-node.sh seller-local-001 compute-local-001 seller-local-001 cpu
./scripts/set-node-availability.sh seller-local-001 drain
./scripts/set-node-availability.sh seller-local-001 active
```

What each step proves:

1. `print-worker-join.sh` reads the live worker join token from Swarm and reconstructs the real join command using the current manager address.
2. `status.sh` shows cluster state, node list, and current labels for every node.
3. `inspect-node.sh seller-local-001` gives an auditable snapshot of the current worker target, including labels and current tasks.
4. `label-compute-node.sh ...` safely re-asserts the compute-node claim on `seller-local-001` and refuses manager/control-plane mutation, duplicate `platform.compute_node_id`, or owner hijack.
5. `set-node-availability.sh ... drain` only allows a non-control-plane worker, and rejects the drain if the node still has running replicated workload.
6. `set-node-availability.sh ... active` restores the worker to `active` after the drain check.

## Verified Evidence On 2026-03-24

- `docker info --format ...` showed `state=active`, `node_addr=192.168.2.208`, and `control=true`, confirming this machine is the live manager/control-plane.
- `docker node ls` showed two nodes in `Ready/Active`: manager `cw-NF5588M4` and worker `seller-local-001`.
- `docker swarm join-token -q worker` returned a live non-empty `SWMTKN-1-...` worker token. The token is intentionally not committed in full to avoid storing a current join secret in the repo.
- `docker node inspect seller-local-001 --format '{{json .Spec}}'` showed `Role=worker`, `Availability=active`, and current compute labels:
  - `platform.role=compute`
  - `platform.control_plane=false`
  - `platform.compute_enabled=true`
  - `platform.compute_node_id=compute-local-001`
  - `platform.seller_user_id=seller-local-001`
  - `platform.accelerator=cpu`
- `docker node inspect cw-NF5588M4 --format '{{json .Spec}}'` showed manager/control-plane labels, which is why the new scripts refuse non-idempotent mutation there.
- `docker service ls` showed business services pinned on manager and `pivot-benchmark_benchmark_worker` at `0/1`, so there was no running replicated benchmark workload on `seller-local-001` during this verification pass.
- `docker node ps seller-local-001` showed only `portainer_agent` still running and the old benchmark task already `Shutdown/Complete`, which satisfies the current drain guard because global services are ignored and no replicated platform workload was active on the worker.
- `./scripts/set-node-availability.sh seller-local-001 drain` succeeded and read back the worker in `availability=drain`.
- `./scripts/set-node-availability.sh seller-local-001 active` succeeded immediately after and restored the worker to `availability=active`.

## Honest Stop Point

- This closes the CLI-side truth slice for current node operations only.
- The backend still does not have verified Docker CLI/socket prerequisites, so task 4 is still blocked until those preconditions are made true in `backend` and Swarm deployment assets.
- `remove_swarm_node()` is intentionally untouched here because task 7 still owns the destructive-flow safety design.
- Hardware values observed inside the local seller DinD worker remain operational observations, not platform-verified sale truth.

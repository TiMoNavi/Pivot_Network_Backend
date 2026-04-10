import json
import os
import socket
import time


def read_memory_limit_mb() -> int | None:
    cgroup_candidates = (
        "/sys/fs/cgroup/memory.max",
        "/sys/fs/cgroup/memory/memory.limit_in_bytes",
    )

    for path in cgroup_candidates:
        if not os.path.exists(path):
            continue

        with open(path, "r", encoding="utf-8") as file:
            raw_value = file.read().strip()

        if not raw_value or raw_value == "max":
            return None

        limit_bytes = int(raw_value)
        if limit_bytes <= 0:
            return None
        return limit_bytes // (1024 * 1024)

    return None


def main() -> None:
    keepalive_seconds = int(os.environ.get("BENCHMARK_KEEPALIVE_SECONDS", "1800"))

    payload = {
        "kind": "ai_benchmark_validation",
        "benchmark_job_id": os.environ.get("BENCHMARK_JOB_ID", "bench-local-001"),
        "listing_id": os.environ.get("LISTING_ID", "listing-local-001"),
        "requested_profile": os.environ.get("REQUESTED_PROFILE", "cpu-small"),
        "node_hostname": socket.gethostname(),
        "cpu_cores_visible": os.cpu_count(),
        "memory_limit_mb": read_memory_limit_mb(),
        "gpu_count": 0,
        "gpu_model": "none",
        "runtime_source": "docker-swarm-validation",
        "notes": [
            "low-overhead benchmark validation worker",
            "intended to prove placement onto a compute node",
        ],
    }

    print(json.dumps(payload, ensure_ascii=True, sort_keys=True), flush=True)
    time.sleep(keepalive_seconds)


if __name__ == "__main__":
    main()

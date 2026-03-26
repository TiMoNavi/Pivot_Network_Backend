# Docker Swarm 基础操作记录

更新时间：2026-03-24

## 1. 本次实际验证结论

- 本机 Docker Desktop 已成功初始化单机 Swarm manager。
- 成功验证了一次真实 `join`，加入的是本地临时 worker：`swarm-local-worker`。
- 已验证的基础操作包括：
  - `join`
  - 查看节点状态
  - 创建带资源限制的 Swarm service
  - 分析 service / container 的 CPU 与内存限制
  - 向容器内传入一段 Python 代码并执行
  - 删除测试 service，对应 task container 随之消失
  - 删除临时 worker 节点
- 远端腾讯云主机 `81.70.52.75` 没有成功加入当前本机 Swarm。

## 2. 远端腾讯云主机为什么没有加入成功

本次远端尝试时间：2026-03-24。

当时本机 manager 的实际地址是：

```text
192.168.65.3:2377
```

这是 Docker Desktop 内部地址，不是公网可直达地址。

从腾讯云主机测试得到的结果是：

- `192.168.65.3:2377`：超时
- `192.168.2.206:2377`：超时
- `1.161.54.93:2377`：`connection refused`

因此，本次失败不是腾讯云主机 Docker 本身的问题，而是当前本机网络与 Docker Desktop 地址模型不适合让公网机器直接加入。

如果以后还要让公网机器加入当前 Swarm，至少需要满足：

- manager 对公网有稳定可达地址
- `2377/tcp` 可达
- `7946/tcp`、`7946/udp` 可达
- `4789/udp` 可达
- manager 广播地址不能是 Docker Desktop 内部地址

更现实的方案通常是：

- 改成 Linux 主机做 manager
- 或者先打通 VPN / ZeroTier / Tailscale，再让远端加入

## 3. 初始化本机 Swarm manager

在仓库根目录执行：

```powershell
docker swarm init
```

查看当前 Swarm 状态：

```powershell
docker info --format "state={{.Swarm.LocalNodeState}} node_addr={{.Swarm.NodeAddr}} control={{.Swarm.ControlAvailable}}"
```

查看 worker join token：

```powershell
docker swarm join-token -q worker
```

查看节点列表：

```powershell
docker node ls
```

## 4. 创建一个本地临时 worker 并执行 join

本次验证使用的是 DinD 容器，不是额外物理机器。

创建 volume：

```powershell
docker volume create swarm-local-worker-data
```

启动临时 worker：

```powershell
docker run -d `
  --privileged `
  --restart unless-stopped `
  --name swarm-local-worker `
  --hostname swarm-local-worker `
  --cpus 0.5 `
  --memory 512m `
  -e DOCKER_TLS_CERTDIR= `
  -v swarm-local-worker-data:/var/lib/docker `
  docker:26.1-dind
```

等待 DinD 内部 Docker daemon 就绪：

```powershell
docker exec swarm-local-worker docker info
```

执行 join：

```powershell
$token = docker swarm join-token -q worker
docker exec swarm-local-worker docker swarm join --token $token 192.168.65.3:2377
```

验证节点已经加入：

```powershell
docker node ls
docker exec swarm-local-worker docker info --format "state={{.Swarm.LocalNodeState}} node_id={{.Swarm.NodeID}} control={{.Swarm.ControlAvailable}} node_addr={{.Swarm.NodeAddr}}"
```

## 5. 创建一个带资源限制的测试 service

为了验证状态查看、资源限制和容器执行，本次创建了一个轻量测试 service：

```powershell
docker service create `
  --name swarm-probe `
  --constraint node.hostname==docker-desktop `
  --limit-cpu 0.25 `
  --limit-memory 64M `
  --reserve-memory 32M `
  python:3.11-alpine `
  sh -c "sleep 600"
```

查看 service 状态：

```powershell
docker service ps swarm-probe --no-trunc
docker service inspect swarm-probe --format "cpu_limit={{.Spec.TaskTemplate.Resources.Limits.NanoCPUs}} mem_limit={{.Spec.TaskTemplate.Resources.Limits.MemoryBytes}} mem_reservation={{.Spec.TaskTemplate.Resources.Reservations.MemoryBytes}}"
```

查出对应 task container：

```powershell
docker ps --filter label=com.docker.swarm.service.name=swarm-probe --format "{{.ID}} {{.Image}} {{.Status}} {{.Names}}"
```

## 6. 分析容器性能配置

本次 service 配置的目标限制是：

- CPU：`0.25`
- Memory limit：`64M`
- Memory reservation：`32M`

查看实时资源占用：

```powershell
docker stats --no-stream <container_id>
```

查看 container 当前状态：

```powershell
docker inspect <container_id> --format "status={{.State.Status}} started={{.State.StartedAt}} image={{.Config.Image}}"
```

查看容器内实际 cgroup 值：

```powershell
docker exec <container_id> sh -lc "ls /sys/fs/cgroup && echo --- && cat /sys/fs/cgroup/memory/memory.limit_in_bytes && cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us && cat /sys/fs/cgroup/cpu/cpu.cfs_period_us"
```

本次实际读到的关键值是：

- `memory.limit_in_bytes = 67108864`
- `cpu.cfs_quota_us = 25000`
- `cpu.cfs_period_us = 100000`

也就是：

- 内存限制 `64 MiB`
- CPU 限制 `0.25`

## 7. 向容器内传一段代码并执行

先在本机临时目录创建一个脚本：

```powershell
$probe = Join-Path $env:TEMP "swarm_probe_exec.py"
@'
import os
from pathlib import Path

print("probe=ok")
print("cwd=", os.getcwd())
for path in [
    "/sys/fs/cgroup/memory/memory.limit_in_bytes",
    "/sys/fs/cgroup/cpu/cpu.cfs_quota_us",
    "/sys/fs/cgroup/cpu/cpu.cfs_period_us",
]:
    p = Path(path)
    print(f"{path}=", p.read_text().strip() if p.exists() else "missing")
'@ | Set-Content -Path $probe -Encoding UTF8
```

拷贝进容器：

```powershell
docker cp $probe <container_id>:/tmp/swarm_probe_exec.py
```

在容器里执行：

```powershell
docker exec <container_id> python /tmp/swarm_probe_exec.py
```

## 8. 删除测试 service 和对应 container

删除 service：

```powershell
docker service rm swarm-probe
```

确认对应 task container 已消失：

```powershell
docker ps -a --filter label=com.docker.swarm.service.name=swarm-probe --format "{{.ID}} {{.Status}} {{.Names}}"
```

如果没有输出，就说明对应测试 container 已删除。

## 9. 删除临时 worker

让临时 worker 离开 Swarm：

```powershell
docker exec swarm-local-worker docker swarm leave --force
```

从 manager 删除节点记录：

```powershell
docker node rm -f swarm-local-worker
```

删除 DinD 容器和 volume：

```powershell
docker rm -f swarm-local-worker
docker volume rm swarm-local-worker-data
```

再次确认当前节点状态：

```powershell
docker node ls
```

## 10. 建议

- 如果只是本地开发，不要默认把公网机器接进 Docker Desktop 里的 Swarm。
- 如果后面要做真实多机 Swarm，优先考虑 Linux manager。
- 如果必须跨公网组 Swarm，先把网络打通，再谈 join。
- 在资源较小的机器上做验证时，优先使用轻量镜像和显式 CPU / Memory 限制。

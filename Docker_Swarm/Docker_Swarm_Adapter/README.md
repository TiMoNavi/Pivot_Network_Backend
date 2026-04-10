# Docker Swarm Adapter

更新时间：`2026-04-10`

`Docker_Swarm_Adapter` 是当前项目的私有基础设施控制面 HTTP 服务。

它的职责已经固定为：

- 作为 `systemd` 常驻 HTTP 服务运行
- 监听 `0.0.0.0:8010`
- 以 `Plantform_Backend` 为唯一正式调用方
- 对 Docker Swarm / WireGuard 执行受控操作

当前正式边界：

- `Seller_Client` 不直接调用 adapter
- `Plantform_Backend` 通过 `AdapterClient` 调用 adapter

## 当前已暴露能力

### 只读 / 节点控制

- `GET /health`
- `GET /swarm/overview`
- `GET /swarm/nodes`
- `POST /swarm/nodes/inspect`
- `GET /swarm/nodes/by-ref/{node_ref}`
- `GET /swarm/nodes/by-compute-node-id/{compute_node_id}`
- `GET /swarm/nodes/search`
- `POST /swarm/nodes/join-material`
- `POST /swarm/nodes/claim`
- `POST /swarm/nodes/availability`
- `POST /swarm/nodes/remove`

### Runtime / 服务执行面

- `POST /swarm/runtime-images/validate`
- `POST /swarm/nodes/probe`
- `POST /swarm/services/inspect`
- `POST /swarm/runtime-session-bundles/create`
- `POST /swarm/runtime-session-bundles/inspect`
- `POST /swarm/runtime-session-bundles/remove`

### WireGuard

- `POST /wireguard/peers/apply`
- `POST /wireguard/peers/remove`

## 当前卖家接入语义

当前 `join-material` 已经按最新卖家客户端要求工作：

- `manager_addr` 使用 `SWARM_CONTROL_ADDR`
- 当前权威 join target 应是 `10.66.66.1:2377`
- 返回 `recommended_compute_node_id`
- 返回 `recommended_labels`
- 返回 `claim_required`

当前 adapter 不提供独立 `verify` 接口。

因此当前 seller onboarding 的服务端验收方式仍然是：

- backend 请求 `join-material`
- seller 本地执行 `docker swarm join`
- backend 再做 `inspect / claim / inspect`

## 当前不负责的事情

adapter 当前不负责：

- 保存 `JoinSession`
- 保存 `manager_acceptance`
- 保存 `effective_target / truth_authority`
- 定义 seller join 完成标准

这些都仍然由 `Plantform_Backend` 或 `Seller_Client` 编排层负责。

## 快速使用

```bash
cd /root/Pivot_network/Docker_Swarm/Docker_Swarm_Adapter
./scripts/install-venv.sh
./scripts/check.sh
./scripts/run-dev.sh
```

## 运行环境关键变量

- `SWARM_MANAGER_ADDR`
- `SWARM_CONTROL_ADDR`
- `ADAPTER_TOKEN`
- `REGISTRY_HOST`
- `REGISTRY_PORT`
- `WIREGUARD_INTERFACE`
- `WIREGUARD_CONFIG_PATH`

当前默认地址语义：

- `SWARM_MANAGER_ADDR=81.70.52.75`
- `SWARM_CONTROL_ADDR=10.66.66.1`

请不要把这两个地址混成一个含义。

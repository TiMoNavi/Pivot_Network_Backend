# Docker Swarm 中 Worker 节点 WireGuard 地址无法进入 Manager 真相层的官方分析

更新时间：`2026-04-09`

## 1. 这份文档回答什么问题

当前 Windows seller 节点已经多次出现同一个现象：

- worker 本机 Docker 引擎自报 `NodeAddr = 10.66.66.10`
- manager 侧 `docker node inspect <node> .Status.Addr` 长期仍是 `202.113.184.2`

这份文档要回答的是：

1. 从 Docker 官方文档看，这个现象可能意味着什么
2. 哪些思路符合 Docker Swarm 的官方模型
3. 哪些思路更像平台侧 workaround，而不是 Swarm 自己的原生解法
4. 下一步应该优先试哪几条路径

## 2. 当前机器上的真实证据

### 2.1 worker 本机引擎视角

`2026-04-09` 本机执行：

```powershell
& 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' info --format "{{json .Swarm}}"
```

观察到：

- `NodeID = 1mwnvgqrg72jocqihbkxjrvdl`
- `NodeAddr = 10.66.66.10`
- `LocalNodeState = active`
- manager 地址仍显示为 `81.70.52.75:2377`

### 2.2 manager 真相层视角

`2026-04-09` 在 manager 上执行：

```bash
docker node inspect 1mwnvgqrg72jocqihbkxjrvdl --format '{{json .Status}}'
```

观察到：

- `State = ready`
- `Addr = 202.113.184.2`

所以当前分裂非常明确：

- worker 本地视角：`10.66.66.10`
- manager 真相层：`202.113.184.2`

### 2.3 Docker daemon 所在环境的网络证据

这一步非常关键。之前一个常见怀疑是：“WireGuard 只在 Windows 宿主里，不在 Docker daemon 真正所在的系统里”。  
但这台机器的实际情况比这个更复杂。

`2026-04-09` 执行：

```powershell
wsl.exe -d docker-desktop -- sh -lc "ip addr; echo '---'; ip route"
```

观察到：

- `docker-desktop` 环境里确实存在接口 `wg-seller`
- `wg-seller` 地址就是 `10.66.66.10/32`
- 还有一条到 `10.66.66.1 dev wg-seller` 的路由
- 默认路由仍然是 `default via 172.23.128.1 dev eth0`

这说明：

- `10.66.66.10` 并不是只存在于 Windows 宿主里
- 它已经进入了 `docker-desktop` 这个 daemon 所在环境
- 但默认出口仍然不是走 `wg-seller`

## 3. Docker 官方文档能明确确认的约束

### 3.1 `--advertise-addr` 的官方定义

Docker 官方对 `docker swarm init` / `join` 的说明是：

- `--advertise-addr` 用来指定“向 swarm 其他成员通告的地址”
- 在多地址/多接口机器上，应显式指定
- 这个参数可以传 `IP`，也可以直接传 `interface name`

官方文档：

- `docker swarm init`: <https://docs.docker.com/reference/cli/docker/swarm/init/>
- `Manage swarm service networks`: <https://docs.docker.com/engine/swarm/networking/>

### 3.2 `--data-path-addr` 的官方定义

官方明确说：

- `--data-path-addr` 是给全局作用域网络驱动发布的数据面地址
- 它的目标是把 service/container 的数据流量和控制面流量分开
- 它不会限制 VXLAN socket 真正绑定哪个源地址

这意味着：

- `--data-path-addr` 不是“强制 manager 记住这个 worker 的原始地址”的开关
- 它更像“数据面告诉其他节点该从哪里找我”

### 3.3 Docker 官方并没有提供“修改 worker 节点地址”的原生命令

官方支持的节点变更主要是：

- `docker node update`
  - `labels`
  - `availability`
  - `role`
- `docker node rm`
  - 删除节点
- `docker swarm leave`
  - 离开 swarm

但 Docker 官方并没有提供：

- “直接把某个 worker 的 `Status.Addr` 改成另一个 IP”的命令
- “manager 侧强制覆写 worker 原始地址”的 swarm 原生命令

这说明如果要让 Swarm 真相层变地址，官方路线通常还是：

1. worker clean leave
2. manager remove old node
3. 重新 join

官方文档：

- `docker node inspect`: <https://docs.docker.com/reference/cli/docker/node/inspect/>
- `docker node rm`: <https://docs.docker.com/reference/cli/docker/node/rm/>
- `docker swarm leave`: <https://docs.docker.com/reference/cli/docker/swarm/leave/>

### 3.4 官方没有明确承诺 `node inspect .Status.Addr == advertise-addr`

这是一个非常重要但容易被忽略的点。

Docker 官方文档展示了 `docker node inspect` 的输出里有：

- `Status.Addr`
- `ManagerStatus.Addr`

但官方并没有明确写：

- worker 的 `Status.Addr` 必然等于我们传入的 `--advertise-addr`
- 或者一定等于 `--data-path-addr`

也就是说：

- `advertise-addr` 是“swarm 如何通告该节点”
- 但 `Status.Addr` 的最终呈现逻辑，官方文档并没有承诺与之一一对应

这会直接影响我们的预期管理：

- 如果我们的成功标准是“manager 的 `Status.Addr` 必须等于 WG IP”
- 那这个标准本身并不完全来自 Docker 官方的明确保证

### 3.5 官方更强调 manager 的静态地址，而不是 worker 的静态地址

在 Docker 的 admin guide 里，官方明确强调：

- manager 应使用静态 `advertise-addr`
- worker 使用动态 IP 是可以接受的

这意味着：

- “让 manager 永久按某个固定 WG IP 识别 worker”并不是 Docker Swarm 官方重点保证的路径
- 我们当前追逐的目标，可能比 Docker 官方典型使用方式更严格

官方文档：

- <https://docs.docker.com/engine/swarm/admin_guide/>

## 4. Docker Desktop 官方文档带来的额外复杂性

Docker Desktop 官方 FAQ 说明：

- Windows / WSL2 / Hyper-V 下，Docker Desktop 使用 VM 进程
- host 与 VM 的通信通过 `AF_VSOCK`
- 主机网络由 `com.docker.vpnkit.exe` 和 `com.docker.backend.exe` 这类 Desktop 进程完成

官方文档：

- <https://docs.docker.com/security/faqs/networking-and-vms/>

这带来一个关键推论：

- 即使 `docker-desktop` 环境里可以看到 `wg-seller`
- 也不代表 Swarm 控制面最终对外呈现的源地址，就一定完全由这个内层网络接口决定

这是一个推断，不是官方逐字原话。  
但结合当前现象，它是非常合理的解释：

- daemon 环境里有 `wg-seller=10.66.66.10`
- 本地 `NodeAddr` 也显示 `10.66.66.10`
- 但 manager 最终仍记录 `202.113.184.2`

这说明 Docker Desktop 的网络抽象层很可能参与了最终对外可见地址的形成。

## 5. 对当前现象的几种可能解释

下面是按“与当前证据匹配程度”排序的几种解释。

### 5.1 解释 A：`advertise-addr` 生效了，但 `Status.Addr` 并不等于它

这是最值得认真对待的一种解释。

理由：

- worker 本地已经自报 `NodeAddr = 10.66.66.10`
- 说明我们传入的地址并不是完全无效
- 官方文档又没有承诺 `Status.Addr` 必定等于 `advertise-addr`

如果这个解释成立，那么我们之前的一部分尝试，其实是在追一个 Docker 官方并未明确承诺一定会变化的字段。

### 5.2 解释 B：Docker Desktop 让控制面最终仍经由宿主公网出口呈现

这也非常符合当前证据。

理由：

- `docker-desktop` 里默认路由仍走 `eth0`
- Docker Desktop 官方又说明宿主网络是 Desktop 自己的 backend/vpnkit 过程在处理
- manager 最终看到的是公网 `202.113.184.2`

如果这个解释成立，那么：

- 即便 WG 接口已经进入 `docker-desktop`
- Docker Desktop 仍可能让 Swarm 控制面最终以宿主公网身份出现

### 5.3 解释 C：join / rejoin 过程不够“干净”，旧节点身份残留影响了 manager 真相层

这条解释不能排除，但当前证据支持度低于前两条。

理由：

- 我们确实看到过旧节点残留、`claim_failed`、同 hostname 多节点的现象
- Docker 官方路线本来也更偏向 `leave -> node rm -> rejoin`

但问题在于：

- 即使反复重试后，本地 `NodeAddr` 和 manager `Status.Addr` 的分裂仍然高度稳定
- 这更像是系统性网络选择问题，而不只是单次残留问题

### 5.4 解释 D：我们把 `data-path-addr` 的作用想大了

这条可以基本确认。

官方文档已经明确：

- `data-path-addr` 解决的是数据面
- 不是 manager 真相层地址覆写器

所以如果策略建立在“只要把 data-path 指到 WG，manager 看到的节点地址就会变”之上，那这条策略本身和 Docker 官方定义不一致。

## 6. 多种可能的解决思路

下面按“是否更贴近 Docker 官方模型”来分。

### 6.1 方案一：完整 clean reset，再用接口名重建 worker

这是最接近官方模型、且成本相对可控的方案。

做法：

1. worker 执行 `docker swarm leave --force`
2. manager 执行 `docker node rm <old-node>`
3. 重新 join 时，不传裸 IP，改传接口名
4. 优先尝试：

```bash
docker swarm join \
  --token <worker-token> \
  --advertise-addr wg-seller \
  --data-path-addr wg-seller \
  <manager>:2377
```

如果需要，也可以继续试：

- `--listen-addr wg-seller:2377`
- 或 `--listen-addr 0.0.0.0:2377`

为什么值得试：

- Docker 官方明确支持接口名
- 接口名在多网卡环境下往往比裸 IP 更接近官方预期用法
- 当前 `docker-desktop` 环境里已经确实存在 `wg-seller`

风险：

- 即使这样做，`Status.Addr` 仍然可能不变
- 因为官方并没有保证它一定跟 `advertise-addr` 同步

### 6.2 方案二：把 manager 的 join 入口也切到 WireGuard 控制面

这是更重，但更可能收敛真相层的一条路。

做法：

- manager 自己明确在 WG 地址上暴露 Swarm 控制面
- worker 不是 join 到 `81.70.52.75:2377`
- 而是 join 到 `10.66.66.1:2377`

为什么值得试：

- 当前 worker 本地 `RemoteManagers` 仍然是 `81.70.52.75:2377`
- 如果控制面本身始终经由公网建立，manager 侧真相层长期保留公网身份并不奇怪

风险：

- 需要改 manager 侧的 Swarm 暴露方式
- 有可能影响线上已有 swarm
- 这是服务端侧变更，风险明显高于方案一

### 6.3 方案三：接受 control plane 公网、只把 data plane 放到 WG

这是“更偏官方、但不追求 raw truth 的方案”。

做法：

- `--advertise-addr` 允许继续使用公网/manager 可稳定识别的地址
- `--data-path-addr` 指向 `wg-seller`
- 再检查 overlay 数据面是否能更多经由 WG

适合什么目标：

- 目标是“让服务真正能跑、买家能消费算力”
- 而不是“manager 的 `Status.Addr` 必须显示 WG IP”

优点：

- 更符合 Docker 官方对 control/data 分离的定义
- 不强求一个官方没有明确承诺的字段必须等于 WG IP

缺点：

- 无法解决“manager 真相层显示公网 IP”这个表象问题

### 6.4 方案四：重建 `docker_gwbridge` / ingress / 端口策略，解决 overlay 可达性

这条更像配套修复，而不是直接改 `Status.Addr` 的主解法。

官方文档明确说：

- `docker_gwbridge` 可以在 join 前或临时离群后重建
- overlay/ingress 有自己的端口与桥接要求

适合什么问题：

- `minimum_tcp_validation` 不通过
- overlay 服务可达性异常
- 端口 `7946 / 4789` 或 bridge 状态不稳定

但这条路不应该被误认为：

- “重建 bridge 就能让 manager 把 raw addr 改成 WG IP”

### 6.5 方案五：放弃 Docker Desktop 作为 Swarm worker 宿主，改用原生 Linux dockerd

这是最重，但从工程确定性上最强的一条路。

做法可以是：

- 独立 Ubuntu / WSL 发行版里运行原生 Docker Engine
- 或直接用 Linux VM / Linux 主机做 seller worker

为什么它很重要：

- Docker Swarm 官方教程和主流路径本来就是按 Linux host 设计的
- Docker Desktop 在 Windows 上多了一层 VM / backend / host networking 抽象
- 当前问题恰好就发生在“Swarm 节点身份地址”这一类对网络层非常敏感的环节

如果目标是：

- `manager 真相层必须稳定显示 WG IP`

那么从确定性角度看，原生 Linux dockerd 比 Docker Desktop 更有希望。

代价：

- 实施成本最高
- 可能要重做当前 Windows seller 本地工作流的一部分

### 6.6 方案六：承认 Swarm 原生真相层改不动，改走平台 authoritative target

这不是 Docker Swarm 原生解法，而是平台 workaround。

做法：

- backend 继续记录 `effective_target_addr = 10.66.66.10`
- buyer/平台连接链路尽量依赖 backend authoritative target
- 不再把 `docker node inspect .Status.Addr == 10.66.66.10` 当成唯一成功标准

适合什么前提：

- 平台真正目标是“卖家算力能被消费”
- 而不是“Swarm 自己的节点视图一定长成 WG IP”

局限：

- 这不是修好 Swarm 真相层
- 它只能算 Swarm 之外的补丁路径

## 7. 我对几条路径的判断

### 7.1 最值得先试的

优先级建议：

1. `方案一`
2. `方案二`
3. `方案五`

原因：

- 方案一成本最低，而且仍处在 Docker 官方模型内
- 如果方案一失败，说明“只是 join 参数写法不对”的概率已经不高
- 这时再试方案二，判断“是不是控制面入口本身必须走 WG”
- 如果二者都失败，继续在 Docker Desktop 上追 `Status.Addr = WG IP` 的性价比就会明显下降

### 7.2 最容易浪费时间的

最容易继续消耗时间、但不一定解决核心问题的是：

- 单纯继续调 `data-path-addr`
- 在不 clean remove old node 的情况下重复 rejoin
- 把 backend correction 当作已经修好 Swarm 真相层

### 7.3 一个必须明确的现实

如果 Docker 官方并没有承诺：

- `Status.Addr` 必定等于 `advertise-addr`

那么我们就需要区分两种目标：

1. `Swarm 官方模型目标`
   - 让节点稳定 join、overlay 通、服务能调度、流量能跑
2. `平台业务目标`
   - 让 buyer 最终能连到 seller 并消费算力

这两者有重叠，但并不完全等价。

## 8. 推荐的下一步执行顺序

### 8.1 第一轮：做一次“最官方”的干净重建

建议按这个顺序：

1. manager 记录当前节点 ID 与标签
2. worker `docker swarm leave --force`
3. manager `docker node rm <old-node>`
4. 在 `docker-desktop` 环境内再次确认 `wg-seller` 存在
5. 用接口名重新 join：

```bash
docker swarm join \
  --token <worker-token> \
  --advertise-addr wg-seller \
  --data-path-addr wg-seller \
  81.70.52.75:2377
```

6. 重新看：
   - worker 本机 `docker info .Swarm`
   - manager `docker node inspect .Status`
   - overlay / tcp validation

### 8.2 第二轮：如果仍失败，再改 manager 入口到 WG

如果第一轮后：

- worker 本地还是 `NodeAddr = 10.66.66.10`
- 但 manager 侧仍是公网

那就说明单纯 worker 端传参已经不够。  
这时再评估是否把 manager 的 control plane 也切到 WG。

### 8.3 第三轮：如果还不行，就要重新评估 Docker Desktop

如果：

- `wg-seller` 已经进入 `docker-desktop`
- `advertise-addr` 也用接口名重建过
- manager 入口也试过 WG
- 结果 `Status.Addr` 仍旧稳定锁到公网

那就应当把结论收敛成：

- Docker Desktop 路径大概率不适合承担“让 Swarm 真相层精确显示 WG IP”这个目标

这时要么：

- 切原生 Linux dockerd
- 要么改平台目标，不再把这个字段当硬指标

## 9. 一句话结论

当前最重要的判断不是“我们有没有再多试几次 join 参数”，而是：

- Docker 官方模型并没有明确承诺 worker 的 `Status.Addr` 必定等于 `advertise-addr`
- 当前这台机器又处在 Docker Desktop 的额外网络抽象之下

因此，最合理的下一步不是继续盲试，而是：

1. 用接口名做一次最干净的官方重建
2. 失败后再评估是否让 manager 控制面也进入 WG
3. 如果还不收敛，就应接受“Docker Desktop 可能不是这个目标的合适宿主”这个结论

## 10. 官方参考

- Docker Swarm init: <https://docs.docker.com/reference/cli/docker/swarm/init/>
- Docker Swarm networking: <https://docs.docker.com/engine/swarm/networking/>
- Docker Swarm tutorial: <https://docs.docker.com/engine/swarm/swarm-tutorial/>
- Docker node inspect: <https://docs.docker.com/reference/cli/docker/node/inspect/>
- Docker node rm: <https://docs.docker.com/reference/cli/docker/node/rm/>
- Docker Swarm leave: <https://docs.docker.com/reference/cli/docker/swarm/leave/>
- Docker Swarm admin guide: <https://docs.docker.com/engine/swarm/admin_guide/>
- Docker Desktop networking / VM FAQ: <https://docs.docker.com/security/faqs/networking-and-vms/>

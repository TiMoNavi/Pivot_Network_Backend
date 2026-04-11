# Windows SSH 卖家 Join 执行与留证 Runbook

更新时间：`2026-04-11`

## 1. 文档定位

这份文档定义：

- 如何通过 operator SSH / reverse SSH 进入 Windows 主机
- 如何在 Windows 上执行 seller join / correction cycle
- 如何检查 session / auth / backend 写入链是否仍然可用
- 如何记录一轮 seller-path join 的完整证据

它服务于：

- `phase3` 末期 seller 真实 join 与平台上架验证
- `phase5` 前的 seller-path 真实联调留证

它不服务于：

- 买家产品正式入口
- backend 真相替代路径

## 2. 用途边界

Windows SSH 入口只用于：

- deployment
- diagnostics
- verification

它不等于：

- seller 产品主入口
- buyer 产品主入口
- 平台成功标准

当前 seller 正式成功标准仍然是：

1. backend 看见真实 `join`
2. manager 侧确认 worker `Ready`
3. manager 侧确认该 worker 上存在可执行或运行中的 task
4. backend 最终把 session 写成 `verified`
5. backend 后置触发 capability assessment / offer commercialization

## 3. 前置条件

执行本 runbook 前，默认满足：

- Linux 侧可访问当前 repo：`/root/Pivot_network`
- Windows operator 入口可用
- Windows 上已有 seller client 工作区：
  - `D:\AI\Pivot_Client\seller_client`
- Windows 上 seller client 已安装：
  - `.venv\Scripts\python.exe` 存在
- backend / adapter 当前可用

## 4. 当前推荐读文顺序

1. `docs/runbooks/current-project-state-and-execution-guide.md`
2. `Seller_Client/docs/current-seller-onboarding-flow-cn.md`
3. `win_romote/windows 电脑ssh 说明.md`
4. 本文

## 5. Linux -> Windows 入口

### 5.1 首选入口

```bash
ssh win-local-via-reverse-ssh
```

### 5.2 等价命令

```bash
ssh -p 22220 -i /root/.ssh/id_ed25519_windows_local 550w@127.0.0.1
```

### 5.3 备用入口

```bash
ssh win-local-via-wg
```

### 5.4 登录后切到工作区

```cmd
cd /d D:\AI\Pivot_Client
```

seller client 项目根：

```text
D:\AI\Pivot_Client\seller_client
```

## 6. 需要关注的 Windows 路径

### seller client 根目录

```text
D:\AI\Pivot_Client\seller_client
```

### session 文件目录

```text
D:\AI\Pivot_Client\seller_client\sessions
```

### seller client 日志目录

```text
D:\AI\Pivot_Client\seller_client\logs
```

### 当前关键 bootstrap 脚本

```text
D:\AI\Pivot_Client\seller_client\bootstrap\windows\start_seller_client.ps1
D:\AI\Pivot_Client\seller_client\bootstrap\windows\attempt_manager_addr_correction_cycle.ps1
D:\AI\Pivot_Client\seller_client\bootstrap\windows\rejoin_windows_swarm_worker.ps1
```

## 7. 第一步：确认 Windows 入口和工作区

在 Linux 上执行：

```bash
ssh win-local-via-reverse-ssh "hostname && whoami"
ssh win-local-via-reverse-ssh "powershell -NoProfile -Command \"Test-Path 'D:\AI\Pivot_Client'; Test-Path 'D:\AI\Pivot_Client\seller_client'\""
```

期望：

- `hostname -> 550W`
- `whoami -> 550w\550w`
- 两个 `Test-Path` 都返回 `True`

## 8. 第二步：同步当前 repo 的 Windows 脚本

如果你要把当前 Linux repo 的 seller Windows 脚本同步到远端 Windows：

```bash
cd /root/Pivot_network/Seller_Client
./scripts/deploy-to-windows.sh
```

只执行单个脚本时，可用：

```bash
scp /root/Pivot_network/Seller_Client/bootstrap/windows/attempt_manager_addr_correction_cycle.ps1 \
  win-local-via-reverse-ssh:'D:/AI/Pivot_Client/seller_client/bootstrap/windows/attempt_manager_addr_correction_cycle.ps1'

scp /root/Pivot_network/Seller_Client/bootstrap/windows/rejoin_windows_swarm_worker.ps1 \
  win-local-via-reverse-ssh:'D:/AI/Pivot_Client/seller_client/bootstrap/windows/rejoin_windows_swarm_worker.ps1'
```

同步后建议校验修改时间：

```bash
ssh win-local-via-reverse-ssh "powershell -NoProfile -Command \"Get-Item 'D:\AI\Pivot_Client\seller_client\bootstrap\windows\attempt_manager_addr_correction_cycle.ps1','D:\AI\Pivot_Client\seller_client\bootstrap\windows\rejoin_windows_swarm_worker.ps1' | Select FullName,LastWriteTime | Format-List\""
```

## 9. 第三步：启动或确认 seller client 本地服务

### 9.1 启动 seller client

在 Windows 上执行：

```powershell
powershell -ExecutionPolicy Bypass -File "D:\AI\Pivot_Client\seller_client\bootstrap\windows\start_seller_client.ps1"
```

默认端口：

- `127.0.0.1:8901`

### 9.2 检查本地服务是否可用

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8901/ | Select-Object StatusCode
```

期望：

- `StatusCode = 200`

## 10. 第四步：确认当前 session file / auth token 仍然可写 backend

这一步很关键。

不要直接把：

- `join-complete -> 401`

写成：

- “join 失败”

必须先区分是：

- token 失效
- session stale
- 本地 seller app refresh 面不可用
- 还是 join 本身失败

### 10.1 找当前 session 文件

```powershell
Get-ChildItem 'D:\AI\Pivot_Client\seller_client\sessions' -Recurse -Filter session.json |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 5 FullName,LastWriteTime
```

### 10.2 读取关键字段

```powershell
$sessionFile = 'D:\AI\Pivot_Client\seller_client\sessions\<session_id>\session.json'
$session = Get-Content -Raw -Encoding UTF8 $sessionFile | ConvertFrom-Json
$session | Select-Object backend_base_url, backend_api_prefix, auth_token
$session.onboarding_session | Select-Object session_id, status, requested_compute_node_id
```

至少要确认：

- `session_id`
- `backend_base_url`
- `backend_api_prefix`
- `auth_token`

### 10.3 直接试 backend 读面

```powershell
$headers = @{ Authorization = "Bearer $($session.auth_token)" }
$url = "$($session.backend_base_url)$($session.backend_api_prefix)/seller/onboarding/sessions/$($session.onboarding_session.session_id)"
Invoke-RestMethod -Headers $headers -Uri $url -Method GET
```

如果这里已经 `401 unauthorized`：

- 先记为 auth/session blocker
- 不要继续把 host 侧 rerun 结论写成 join 失败

### 10.4 如果 session stale，怎么办

优先级固定为：

1. 如果 seller client 本地 app refresh / attach 面还可用，优先切 fresh session 再跑
2. 如果 app 仍不可用，先单独回报 auth/session blocker

## 11. 第五步：执行 seller-path correction cycle

当前正式脚本：

```text
D:\AI\Pivot_Client\seller_client\bootstrap\windows\attempt_manager_addr_correction_cycle.ps1
```

### 11.1 最小执行方式

```powershell
$sessionFile = 'D:\AI\Pivot_Client\seller_client\sessions\<session_id>\session.json'
powershell -ExecutionPolicy Bypass -File "D:\AI\Pivot_Client\seller_client\bootstrap\windows\attempt_manager_addr_correction_cycle.ps1" `
  -SessionFilePath $sessionFile
```

### 11.2 常用显式参数

```powershell
powershell -ExecutionPolicy Bypass -File "D:\AI\Pivot_Client\seller_client\bootstrap\windows\attempt_manager_addr_correction_cycle.ps1" `
  -SessionFilePath $sessionFile `
  -JoinMode wireguard `
  -AdvertiseAddress 10.66.66.10 `
  -DataPathAddress 10.66.66.10 `
  -ListenAddress 10.66.66.10:2377 `
  -MinimumTcpValidationPort 8080
```

### 11.3 脚本会做什么

它会尝试串起：

1. seller 侧 WG-target rejoin / idempotent join
2. `join-complete`
3. manager monitor
4. backend correction
5. backend `re-verify`
6. 必要时 `authoritative-effective-target`
7. backend `minimum-tcp-validation`

## 12. 第六步：固定要回传的 exact facts

每次 seller-path run，回传必须至少包含这组事实：

- `session_id`
- `join_result.join_exit_code`
- `join_result.join_idempotent_success`
- `join_result.join_idempotent_reason`
- 本地 `docker info .Swarm` 的：
  - `NodeID`
  - `NodeAddr`
  - `LocalNodeState`
- `manager_monitor.raw_success`
- selected candidate 的：
  - `status_state`
  - `status_addr`
- backend `reverify` 后的：
  - `manager_acceptance.status`
  - `manager_acceptance.observed_manager_node_addr`
- `authoritative-effective-target` 后的：
  - `effective_target_addr`
  - `effective_target_source`
  - `truth_authority`
- `minimum_tcp_validation` 是否已写回
- 如果没有写回，卡在哪一跳

## 13. 推荐记录模板

建议把每轮结果写成下面这个最小记录：

```markdown
## Windows Seller Join Run

- run_at:
- operator_entry: `win-local-via-reverse-ssh`
- session_id:
- session_file:
- backend_base_url:
- auth_token_valid: true/false
- fresh_session_used: true/false

### Join
- join_exit_code:
- join_idempotent_success:
- join_idempotent_reason:

### Local Swarm
- node_id:
- node_addr:
- local_node_state:

### Manager Monitor
- raw_success:
- selected_candidate.status_state:
- selected_candidate.status_addr:

### Backend Truth
- manager_acceptance.status:
- manager_acceptance.observed_manager_node_addr:
- effective_target_addr:
- effective_target_source:
- truth_authority:

### TCP Validation
- minimum_tcp_validation_written_back: true/false
- target_addr:
- target_port:
- reachable:
- blocker_hop:
```

## 14. 常见失败跳点

### 14.1 `join-complete -> 401 unauthorized`

结论应写成：

- auth/session blocker

不要写成：

- join 失败

### 14.2 Windows 本地 seller client 不可用

先记：

- local seller-app blocker

然后再决定：

- 是恢复 app
- 还是先切 fresh session

### 14.3 `already part of a swarm`

要结合：

- `join_idempotent_success`
- `join_idempotent_reason`
- 本地 `LocalNodeState`
- 本地 `NodeAddr`

不能只看到这句报错就判整轮失败。

### 14.4 raw manager 仍 mismatch

不能直接写成功。

要继续看：

- backend `re-verify`
- `authoritative-effective-target`
- `minimum_tcp_validation`

## 15. 回滚与清理

如果要清 seller join 状态：

```powershell
powershell -ExecutionPolicy Bypass -File "D:\AI\Pivot_Client\seller_client\bootstrap\windows\clear_windows_join_state.ps1"
```

如果要从零重来：

1. 清理本地 join 状态
2. 不复用旧 session
3. 创建 fresh onboarding session
4. 再跑本 runbook

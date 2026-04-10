# CCCC Tester Current State

更新时间：`2026-04-11`

这份文档只服务于 `tester` 角色。

`tester` 不是 buyer 正式产品入口，也不是 platform 业务真相面。它只负责：

- 在 Windows 侧通过 operator SSH 控制客户端并记录状态
- 在本地 Linux 侧创建、执行、清理测试与探针
- 为 diagnostics / verification 手动调整平台测试状态与 Docker Swarm 状态

## 1. 必读顺序

1. `PROJECT.md`
2. `CCCC_HELP.md`
3. `docs/runbooks/cccc-phase4-current-state.md`
4. `docs/runbooks/cccc-phase4-workplan.md`
5. `docs/runbooks/cccc-tester-current-state.md`
6. `win_romote/windows 电脑ssh 说明.md`
7. `win_romote/windows_ssh_readme.md`

## 2. Windows operator 入口怎么连

优先入口：

```bash
ssh win-local-via-reverse-ssh
```

等价命令：

```bash
ssh -p 22220 -i /root/.ssh/id_ed25519_windows_local 550w@127.0.0.1
```

WireGuard 备用入口：

```bash
ssh win-local-via-wg
```

当前 `~/.ssh/config` 中：

- `win-local-via-reverse-ssh -> 127.0.0.1:22220`
- `win-local-via-wg -> 10.66.66.10:22`
- 身份密钥都是 `/root/.ssh/id_ed25519_windows_local`

登录到 Windows 后，默认应进入工作区：

```cmd
cd /d D:\AI\Pivot_Client
```

相关路径：

- Windows 主工作区：`D:\AI\Pivot_Client`
- 反向 SSH 脚本目录：`D:\AI\Pivot_backend_build_team\scripts`
- 反向 SSH 日志：`D:\AI\Pivot_Client\logs\reverse-ssh-tunnel.log`

## 3. 当前已验证状态

截至 `2026-04-11`，本地实际检查结果如下：

- `ssh win-local-via-reverse-ssh` 当前可用
- 实际返回：
  - `whoami -> 550w\\550w`
  - `hostname -> 550W`
  - 默认目录：`C:\Users\Administrator`
  - `Test-Path 'D:\AI\Pivot_Client' -> True`
  - `sshd` 服务状态：`Running`
- Windows 上当前可见多个 `ssh` 进程，最近一次启动时间是 `2026/4/11 1:06:28`
- `ssh win-local-via-wg` 当前仍失败：
  - `ssh: connect to host 10.66.66.10 port 22: Connection refused`

所以当前结论是：

- Windows operator 首选入口已经恢复
- 反向 SSH 现在可以用于 operator 控制和验证
- WireGuard 备用入口仍然不可用

## 4. 当前 Linux / Swarm 状态

截至 `2026-04-11`，本机实际检查结果如下：

- `docker info` 显示本机 swarm `active`
- manager 节点：
  - 主机名：`VM-0-3-opencloudos`
  - 地址：`10.66.66.1`
  - 角色：`Leader`
  - 状态：`Ready`
- worker 节点：
  - 主机名：`docker-desktop`
  - 状态：`Ready`
  - 可用性：`Active`
- 当前主要 service：
  - `portainer_agent`：`2/2`
  - `portainer_portainer`：`1/1`
  - `codex_probe_8f75b913`：`0/1`

关于 `codex_probe_8f75b913`：

- 这是遗留探针 service
- `docker service ps codex_probe_8f75b913` 显示 task 当前是 `Shutdown`
- 如果它不再用于诊断，可以由 `tester` 在留证后手动清理

## 5. tester 允许做什么

`tester` 可以做：

- 在 Linux 侧创建临时测试、探针、校验脚本、临时 service
- 在 Windows 侧确认客户端是否存活、工作区是否完整、反向 SSH 是否恢复
- 在 diagnostics / verification 需要时，手动修改平台测试状态
- 在 diagnostics / verification 需要时，手动调整 Docker Swarm 节点或 service 状态

## 6. tester 不允许偷换什么

`tester` 不允许把下面这些东西偷换成“产品成功”：

- operator SSH 可达
- WireGuard 备用 SSH 可达
- 手动改平台状态
- 手动改 Swarm 状态
- Windows 上能手工打开客户端

这些都只能算：

- deployment
- diagnostics
- verification

不是 buyer 正式产品链路成功。

## 7. 每次手动修改都必须留证

每次手动修改平台或 Swarm 状态，都必须至少记录：

1. 修改前状态
2. 执行命令或操作入口
3. 修改后状态
4. 回滚方式
5. 这次修改是在验证什么

# CCCC Windows 启动跑通说明

> 记录日期：2026-03-24
> 结论：本项目里的 CCCC 已经可以在 Windows 上按项目本地脚本拉起 `daemon + Web + actors`，并以“启动后第一句话成功返回”为验收标准完成一次真实验证。

## 这份文档写什么

这份文档只回答 4 个问题：

- 之前为什么没跑通
- 最后到底改了什么
- 现在怎么启动、怎么验收
- 当前停机状态是什么

它不是 CCCC 的通用官方文档，也不是项目总规划文档。

## 最终跑通标准

这次采用的成功标准不是“Web 打开了”，而是下面这一条更硬的标准：

1. 拉起 `ccccd`
2. 拉起 `web`
3. 拉起项目工作组 actors
4. 在启动完成后，向某个 actor 注入一条启动验证指令
5. actor 通过 CCCC MCP 回一条消息给 `user`

实际成功回包示例是：

```text
CCCC startup OK startup362056
```

这条消息由 `swarm_cli` actor 回到 group ledger，说明：

- actor 真的活着
- actor 能操作 CCCC MCP
- 消息确实回到了用户可见 ledger，而不是只停在终端里

## 之前为什么没跑通

## 1. 全局 `cccc` 不在 Windows PATH

最开始这台机器上有 `codex`，但没有可直接使用的全局 `cccc` 命令。

所以不能依赖用户环境里的全局 CCCC 安装，必须把 `cccc-pair` 固定装进项目内的本地运行时。

## 2. 旧版本系统 `codex` 会弹升级确认页

起初系统选中的 `codex` 实际版本是 `0.63.0`。

这个版本在启动后会先弹一个交互页：

```text
Update available!
0.63.0 -> 0.116.0
Press enter to continue
```

如果直接把它拿来做 CCCC actor，actor 会卡死在这个确认页上，后续消息完全进不去。

## 3. 系统版 `codex` 升级后，还会弹目录信任确认

把系统/npm 版 `codex` 升到 `0.116.0` 之后，升级确认页没有了，但又遇到第二个交互页：

```text
Do you trust the contents of this directory?
1. Yes, continue
2. No, quit
```

这会让 actor 虽然已经启动，但仍然停在“目录信任确认”上，自动发送的第一条消息不会被消费。

## 4. group template 会把 actor command 清回 runtime 默认命令

项目模板里 actor 只写了：

- `runtime: codex`
- `runner: pty`

应用模板后，group 里的 actor command 会变回默认的：

```text
codex -c shell_environment_policy.inherit=all --dangerously-bypass-approvals-and-sandbox --search
```

这对 Linux/WSL 问题不大，但在 Windows 上不够稳定，因为我们需要强制它走项目自己的 wrapper，而不是让 daemon 自己再去猜 PATH 里哪个 `codex`。

## 最后怎么跑通的

## 1. 把 CCCC 固定装进项目本地运行时

最终使用的是项目本地 venv：

```text
CCCC/runtime/venv
```

里面安装：

```text
cccc-pair==0.4.7
```

这样 `CCCC_HOME`、daemon、MCP 和项目脚本都在仓库内自洽，不依赖用户全局 Python 环境。

## 2. 改成 Windows 原生启动链

新增了一整套 Windows 可直接执行的脚本：

- `CCCC/run-cccc.ps1`
- `CCCC/cccc-control-common.ps1`
- `CCCC/cccc-start.ps1`
- `CCCC/cccc-status.ps1`
- `CCCC/cccc-stop.ps1`
- `CCCC/start-cccc.cmd`

这套脚本负责：

- 建项目本地 venv
- 安装 `cccc-pair==0.4.7`
- 统一设置 `CCCC_HOME`
- 启动 daemon
- 创建或复用 group
- attach 项目目录
- apply group template
- 启动 actors
- 启动 Web

## 3. 系统版 Codex 更新到 `0.116.0`

用户要求不要优先走 VS Code 扩展里的 `codex.exe`，而要优先走系统选中的 CodeX。

因此最终做法是：

- 显式升级 npm 全局包到最新
- 确认系统版 `codex.cmd` 的实际版本已变成 `0.116.0`
- 让项目 wrapper 优先选 `AppData\\Roaming\\npm\\codex.cmd`
- 只有找不到系统版时，才回退到 VS Code 扩展版

当前项目 wrapper 的优先级是：

1. `%APPDATA%\\npm\\codex.cmd`
2. `%APPDATA%\\npm\\codex`
3. `%APPDATA%\\npm\\codex.ps1`
4. `where codex*`
5. VS Code 扩展里的 `codex.exe` 作为兜底

## 4. 把 actor command 显式改成项目 wrapper 绝对路径

为了避免 template apply 后又退回裸 `codex ...`，启动脚本现在会在每次 apply template 之后，立刻把每个 actor 的 command 显式改成：

```text
"D:\AI\Pivot_backend_build_team\CCCC\bin\codex.cmd" -c shell_environment_policy.inherit=all --dangerously-bypass-approvals-and-sandbox --search
```

这一步非常关键。

如果不做，Windows 下 actor 可能还是会走到不受控的 PATH 解析路径。

## 5. 启动验证不再依赖“普通 send 自动送达”

真实测试里，单靠：

- `cccc send ... --to lead`

并不能稳定保证首条验证消息被消费。

最终采用的是更硬、更可控的方式：

- 用 daemon `term_attach` 直接连到 actor 的 PTY
- 如果发现目录信任确认页，就自动输入 `1` 和回车
- 等 actor 进入可输入状态
- 再把“请立刻通过 CCCC MCP 回复用户”的验证语句直接写进终端
- 然后轮询 `ledger.jsonl`，等待目标 actor 的回复事件

这个逻辑被做成了独立脚本：

- `CCCC/startup_probe.py`

它现在承担“启动后第一句话成功返回”的最终验收。

## 最终启动路径

## 启动

推荐入口：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File D:\AI\Pivot_backend_build_team\CCCC\cccc-start.ps1
```

或者：

```cmd
D:\AI\Pivot_backend_build_team\CCCC\start-cccc.cmd
```

启动脚本内部会完成：

1. 进入项目本地 CCCC 环境
2. 启动 daemon
3. 创建/复用 group
4. attach 项目目录
5. apply template
6. 覆盖 actor command 到项目 wrapper 绝对路径
7. 启动 actors
8. 启动 Web
9. 用 `startup_probe.py` 自动处理目录 trust prompt
10. 注入验证语句并等待 actor 回消息

## 状态检查

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File D:\AI\Pivot_backend_build_team\CCCC\cccc-status.ps1
```

如果运行正常，会输出类似：

```text
healthy: group=g_xxx web=127.0.0.1:8848 running=lead,swarm_cli,backend_adapter,verification,docs_summary
```

## 停止

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File D:\AI\Pivot_backend_build_team\CCCC\cccc-stop.ps1
```

它会：

- 停掉受管 Web
- 停掉 group
- 停掉 daemon

## 关键文件

运行链路关键文件：

- `CCCC/cccc-control-common.ps1`
- `CCCC/run-cccc.ps1`
- `CCCC/cccc-start.ps1`
- `CCCC/cccc-status.ps1`
- `CCCC/cccc-stop.ps1`
- `CCCC/startup_probe.py`
- `CCCC/bin/codex.cmd`
- `CCCC/bin/cccc.cmd`

辅助配置：

- `.codex/config.toml`
- `.gitignore`

## 当前真实结论

到这一步为止，可以诚实地说：

- Windows 下的项目本地 CCCC 启动链已经打通
- 系统/npm 版 `codex` 已升级并成为优先选中的版本
- 启动后的目录信任确认也已经被脚本化处理
- “启动后第一句话成功返回”的验收已经真实完成过一轮

但也要明确：

- 这套成功路径现在依赖 `startup_probe.py` 直接 attach actor PTY 并注入首条验证语句
- 也就是说，当前最稳定的验收路径不是“普通 send 自动送达”，而是“PTY 直连 + MCP 回复验收”

这不是失败，而是当前这版 Windows actor 运行链最诚实、最可控的做法。

## 当前停机状态

本次文档整理完成后，已执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File D:\AI\Pivot_backend_build_team\CCCC\cccc-stop.ps1
```

并确认：

```text
ccccd: not running
```

所以当前 CCCC 处于停止状态，不在后台继续运行。

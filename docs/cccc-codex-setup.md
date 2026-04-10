# Pivot Network CCCC + Codex Setup

本项目已经按 `ChesterRa/cccc` 的官方 CLI 流程接入 CCCC，并统一使用 `codex` 作为 agent runtime。

当前项目明确使用项目内本地 `CCCC_HOME`：

- `/root/Pivot_network/.cccc/home`

不再使用：

- `~/.cccc`

## 本次采用的官方路径

下面这条链路和官方 Quick Start 一致，只是把 runtime 统一成了 `codex`：

```bash
export CCCC_HOME=/root/Pivot_network/.cccc/home
python3 -m pip install -U cccc-pair
cccc setup --runtime codex --path /root/Pivot_network
cccc attach /root/Pivot_network
cccc actor add lead --runtime codex
cccc actor add platform --runtime codex
cccc actor add runtime --runtime codex
cccc actor add reviewer --runtime codex
cccc actor add scribe --runtime codex
```

说明：

- `cccc-pair` 使用的是稳定安装通道。
- `cccc setup --runtime codex` 会把 `cccc mcp` 自动注册到 Codex CLI。
- 第一名 actor 会成为 `foreman` 角色，其余 actor 自动作为 `peer`。
- 在 `cccc-pair 0.4.9` 中，`foreman` 已经是保留字，所以 actor id 改成了 `lead`，但它承担的仍然是 `foreman` 角色。
- 本项目默认使用 `lead + platform + runtime + reviewer + scribe` 五 actor 形态。

## Codex 模型配置

仓库内模板文件：

- `/root/Pivot_network/env_setup_and_install/codex.config.toml`

模板内容对应本项目要求：

- `model_provider = "OpenAI"`
- `model = "gpt-5.4"`
- `review_model = "gpt-5.4"`
- `model_reasoning_effort = "xhigh"`
- `disable_response_storage = true`
- `network_access = "enabled"`
- `windows_wsl_setup_acknowledged = true`
- `model_context_window = 1000000`
- `model_auto_compact_token_limit = 900000`
- `base_url = "https://xlabapi.top/v1"`
- `wire_api = "responses"`

认证文件仍然放在本机：

- `~/.codex/auth.json`

不把 API key 写进仓库。

## 一键复用

可直接运行：

```bash
bash /root/Pivot_network/env_setup_and_install/setup_cccc_codex.sh
```

如果你想在配置完成后顺手启动整个 group：

```bash
START_GROUP=1 bash /root/Pivot_network/env_setup_and_install/setup_cccc_codex.sh
```

这个脚本会做这些事情：

1. 安装或升级最新稳定版 `cccc-pair`
2. 把仓库内的 Codex 模板写入 `~/.codex/config.toml`
3. 检查 `~/.codex/auth.json`
4. 导出 `CCCC_HOME=/root/Pivot_network/.cccc/home`
5. 自动执行 `cccc setup --runtime codex`
6. 把当前项目 attach 到 CCCC working group
7. 确保存在 `lead / platform / buyer / runtime / reviewer / scribe` 六个 Codex actor
8. 把仓库根 `CCCC_HELP.md` 同步到本地 group prompt override
9. 让 CCCC 默认按 `current-project-state-and-execution-guide.md -> PROJECT.md -> CCCC_HELP.md -> cccc-phase4-current-state.md -> cccc-phase4-workplan.md -> Buyer_Client phase4 spec -> win_romote/windows 电脑ssh 说明.md` 的顺序开工

## 常用命令

启动 group：

```bash
cccc group start
```

停止 group：

```bash
cccc group stop
```

查看状态：

```bash
cccc status
```

打开 Web UI：

```bash
cccc
```

给所有 agent 发消息：

```bash
cccc send "Split the task and begin." --to @all
```

## 备注

- CCCC 的持久化状态默认保存在 `/root/Pivot_network/.cccc/home`
- 仓库根 `PROJECT.md` 和 `CCCC_HELP.md` 现在作为 `phase4 / phase5` 的 CCCC brief
- `docs/runbooks/archive/phase1-2026-04-07/` 保留 phase 1 归档文档
- `docs/runbooks/cccc-phase4-current-state.md` 和 `docs/runbooks/cccc-phase4-workplan.md` 是给 CCCC 的当前现状与阶段作战文档
- `win_romote/windows 电脑ssh 说明.md` 是 Windows operator 验证的必读事实源
- `scribe` actor 只负责总结现状和给人类可读文档，不负责业务实现
- Codex 的运行配置保存在 `~/.codex`
- 脚本默认会在配置完成后执行一次 `cccc group stop`，避免 actor 空跑消耗

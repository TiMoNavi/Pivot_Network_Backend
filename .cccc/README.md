# Pivot Network Local CCCC Home

这个目录用于项目内 CCCC 配置。

约定：

- `CCCC_HOME` 固定指向 `/root/Pivot_network/.cccc/home`
- `docs/runbooks/current-project-state-and-execution-guide.md` 是当前项目的一号入口
- 仓库根的 `PROJECT.md` 和 `CCCC_HELP.md` 现在服务于 `phase4 / phase5`
- `docs/runbooks/archive/phase1-2026-04-07/` 保留 phase 1 归档
- `docs/runbooks/cccc-phase4-current-state.md` 负责告诉 CCCC 当前项目已经有什么
- `docs/runbooks/cccc-phase4-workplan.md` 负责告诉 CCCC 按什么 stage 开工
- `docs/runbooks/cccc-phase4-task-prompts.md` 负责告诉 CCCC 当前 actor kickoff 和约束
- `win_romote/windows 电脑ssh 说明.md` 是 Windows operator 验证必读事实源
- 当前阶段分成：
  - `phase3` 末期：seller 真 join 与商品化验证
  - `phase4`：buyer client 实施
  - `phase5`：seller-platform-buyer 闭环联调
- 运行态 group、daemon、ledger、prompt override 都写入 `.cccc/home/`
- 不再使用 `/root/.cccc` 作为本项目的 CCCC_HOME

推荐启动方式：

```bash
source /root/Pivot_network/.cccc/use-local-cccc.sh
bash /root/Pivot_network/env_setup_and_install/setup_cccc_codex.sh
```

这个脚本会自动：

1. 导出本地 `CCCC_HOME`
2. attach 当前项目
3. 创建或更新本地 group
4. 把仓库根 `CCCC_HELP.md` 同步到本地 group prompt override
5. 确保 `lead / platform / buyer / runtime / reviewer / scribe / tester` 七个 actor 存在

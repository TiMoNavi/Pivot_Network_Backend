# AI Benchmark

> 历史规划保留项，当前不激活。

## 任务定义

当用户提交一个算力任务，但还不知道应该租什么规格节点时，系统需要通过一个专用 benchmark worker service 测出：

- 平均算力需求
- 峰值算力需求
- 推荐节点规格

这里的“算力任务”可以是代码仓库、镜像、执行说明，或其他能代表工作负载的输入。

## 核心执行方式

当前路线是建立一个专用 benchmark worker service。

当前 Docker 侧已经有一个轻量 benchmark 验证底座，用于验证：

- benchmark worker 镜像可构建和分发
- benchmark service 可部署
- benchmark service 可被调度到 compute 节点

这层只说明 Docker / Swarm 链路已经打通，不等于最终的 `AI Benchmark` 后端模块已经完成。

这个 service 的镜像中直接预装：

- `Codex`
- benchmark 所需系统工具
- 项目固定 prompt 模板
- 结果导出脚本

默认工作方式：

- 后端创建 benchmark job
- 后端通过 `Swarm Adapter` 创建 benchmark worker service
- service 被调度到目标 benchmark 节点或目标 compute 节点
- 容器内的 `Codex` 根据预置提示词自动分析任务并做压测
- 容器导出结构化结果

默认路线不是专门手写一套 benchmark 业务脚本，而是通过“容器内预装 `Codex` + 固定 prompt + 工具链”来完成自动测算。

## 完成标准

- 能创建 benchmark job
- 能通过 `Swarm Adapter` 创建 benchmark worker service
- worker 能被调度到目标节点或目标标签节点
- 能输出结构化测算结果
- 测算结果至少包含平均需求、峰值需求和推荐节点规格
- 本机至少有 2 到 3 个可重复模拟测试

## 第一版结果字段建议

- `average_cpu_requirement`
- `peak_cpu_requirement`
- `average_memory_requirement_mb`
- `peak_memory_requirement_mb`
- `gpu_required`
- `average_gpu_memory_requirement_mb`
- `peak_gpu_memory_requirement_mb`
- `recommended_node_spec`
- `benchmark_summary`
- `generated_at`

## 明确边界

- `AI Benchmark` 的目标是估算“任务需要什么规格节点”
- 它不是“卖家节点能力评估模块”
- 容器算力需求估算不依赖外部价格平台，主要依赖专用 benchmark worker service

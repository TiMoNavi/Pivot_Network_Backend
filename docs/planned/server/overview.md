# 服务器规划

## 未来要完成

- WireGuard 节点接入闭环
- 节点审核与可用性控制
- runtime service 业务编排
- buyer runtime gateway / relay
- registry HTTPS 或信任自动化
- 监控、日志、告警
- 生产级安全加固

## 当前阶段目标

- 把 manager 从“已可用”推进到“可持续接入卖家节点”

## 流程图

```mermaid
flowchart TD
    A[manager 已可用] --> B[WireGuard 接入闭环]
    B --> C[节点审核与标签策略]
    C --> D[runtime service 编排]
    D --> E[监控与安全]
```

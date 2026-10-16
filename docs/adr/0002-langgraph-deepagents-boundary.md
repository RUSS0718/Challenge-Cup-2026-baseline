# ADR-0002：LangGraph 管理 Run，DeepAgents 提供角色级 Agent

**状态：accepted**  
**日期：2026-10-15**  
**范围：V0.1 Agent Workbench**

## 背景

DeepAgents 适合提供规划、工具和子 Agent 能力。产品还需要统一控制 Run 状态、checkpoint、interrupt、resume、预算和 Evidence Pack。

## 决策

- LangGraph 作为产品的 Run 控制层；
- DeepAgents 通过 `AgentAdapter` 作为 Planner、Solver 或 Researcher 的角色级实现；
- LangGraph 节点只依赖 Adapter，不直接依赖 DeepAgents 内部状态；
- 工具调用统一经过产品 Tool Registry。

## 理由

Spike 已验证 DeepAgents 可以完成当前 Intern 的文本调用和工具调用，也验证了 LangGraph 可以承载工具失败、interrupt、resume 和 checkpoint。两者职责不同，分层可以保留高级 Agent 能力，同时让产品状态和恢复语义可控。

## 后果

- 需要实现状态和错误映射；
- DeepAgents 的内部持久化能力不等于产品 checkpoint；
- 产品可以在后续替换 Agent Harness，而不修改 Run 状态接口。



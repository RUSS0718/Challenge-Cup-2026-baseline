# ADR-0001：分离 official 与 showcase Profile

**状态：accepted**  
**日期：2026-10-15**  
**范围：V0.1 Agent Workbench**

## 背景

官方评分路径已经有稳定的入口、预算、输出合同和 baseline。主观评测需要额外的 Agent 编排、工具、持久化和展示能力。

## 决策

保留两个运行 Profile：

- `official`：只运行现有官方路径；
- `showcase_mvp`：运行 V0.1 产品侧架构。

产品侧组件不得被根 `user_agent.py` 导入，也不得改变官方模型调用次数、输出格式或 baseline 文件。

## 理由

Risk Spike 已确认产品依赖可以在独立环境中安装，且导入根 `user_agent` 不会加载 DeepAgents 或 LangGraph。分离 Profile 可以让主观展示独立演进，同时保留官方结果的可追踪性。

## 后果

- Showcase 需要独立入口、配置和验收；
- Showcase 的运行结果不能直接解释为官方正确率结果；
- 未来如果要合并任何模块，必须重新进行官方路径审查。



# 开源智能体项目景观（2026-10-11）

> 证据范围：仅使用项目官方文档、官方 GitHub 仓库或官方文档源码。
> “已确认”是来源直接描述的能力；“建议”是面向本分支的工程推断，不代表数学正确率提升。

本分支的官方 user_agent.py、调用预算和返回合同保持不变。以下能力只作为主观评测 Demo/实验模块候选；未完成独立评测前，不接入默认官方路径。

## 总览

| 项目 | 已确认核心能力 | 可迁移原语 | MVP 适用性 |
| --- | --- | --- | --- |
| LangGraph | 状态图、checkpointer/store、interrupt、事件流 | 显式状态、可恢复暂停、幂等节点 | 高（借鉴原语）；低（直接引入整套框架） |
| AutoGen GraphFlow / Studio | 顺序/并行/条件/循环图；消息过滤；可视化 Studio | 声明式流程图、fan-in/out、上下文边界 | 中；GraphFlow 实验性，Studio 非生产 |
| CrewAI Flows / Memory / Tracing | 事件流、结构化状态、SQLite 持久化、usage metrics、统一记忆、追踪 | typed state、成本指标、脱敏事件 | 高（本地展示）；外部 Memory/AMP 需谨慎 |
| OpenHands SDK / Runtime | Action/Observation 事件、工具/工作区、Docker/Kubernetes 沙箱 | 工具协议、事件审计、受限执行器 | 中（事件协议）；低（完整沙箱） |
| Letta（可选） | Git 版本化 MemFS、跨会话身份、后台 dreaming | 可审计长期记忆、回滚 | 低（当前 MVP） |

## LangGraph：可恢复的状态图

**已确认。** LangGraph 将自己定位为构建长时运行、有状态 Agent 的低层编排框架，提供 durable execution、streaming、human-in-the-loop、persistence 和 memory。[Reference](https://langchain-ai.github.io/langgraph/reference/)
其持久化分为 checkpointer（单 thread 图状态快照）和 store（跨 thread 应用数据），分别覆盖会话连续性/故障恢复与用户偏好/共享知识。[Persistence](https://langchain-ai.github.io/langgraph/concepts/durable_execution/)、[官方文档源码](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/persistence.mdx)
interrupt 可以暂停节点、持久化状态、等待输入并用 Command 恢复；恢复会回到检查点边界，因此副作用必须幂等。[Interrupts](https://langchain-ai.github.io/langgraph/concepts/breakpoints/)、[Graph API 源码](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/graph-api.mdx)
流式接口可按 state updates、values、LLM messages、custom、tools 和 debug 等投影消费，并能携带子图命名空间。[Streaming](https://langchain-ai.github.io/langgraphjs/how-tos/stream-multiple/)

**建议。** 本分支只需定义小型 FlowState（题目、阶段、候选摘要、校验结果、预算、错误）和有限状态图；展示层消费脱敏阶段事件。暂停恢复前的写入必须幂等，快照必须 JSON 可序列化。

**MVP 判断。** 高度适合借鉴，低度适合直接依赖。直接引入会扩大依赖和入口面；checkpointer/store 还需要生命周期、清理和题间隔离设计。它保证的是恢复语义，不是数学正确性。

## AutoGen GraphFlow / Studio：声明式协作流程

**已确认。** GraphFlow 以 DiGraphBuilder/GraphFlow 构建有向图，支持顺序、并行 fan-out/fan-in、条件分支和循环；边可按消息条件触发，activation group 可设置等待 all 或 any。MessageFilterAgent 可限制每个 Agent 接收的消息。[GraphFlow](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/graph-flow.html)
官方将 GraphFlow 标为实验性功能。AutoGen Studio 提供 Team Builder、Playground、Gallery、Deployment：可用 JSON/拖拽定义 agents、teams、tools、models 和 termination conditions；Playground 支持实时消息流、控制转移图和暂停/停止。官方明确 Studio 用于快速原型和展示，不是生产应用。[Studio](https://microsoft.github.io/autogen/stable/user-guide/autogenstudio-user-guide/)、[Studio usage](https://microsoft.github.io/autogen/dev/user-guide/autogenstudio-user-guide/usage.html)

**建议。** 用受限 JSON 描述节点、允许的下一节点、条件标签和最大循环次数；把执行图和消息图分开，让验证节点只接收必要摘要。页面可以复用控制转移图的数据模型，后端仍使用本地执行器。

**MVP 判断。** 中等适用。适合展示“规划→独立验证→收束”的协作结构；实验性 API 和额外模型调用预算使得直接接入官方路径不合适。

## CrewAI：事件流、状态、记忆与追踪

**已确认。** Flows 用 @start/@listen 连接事件驱动任务，支持条件/循环/分支和 Pydantic 结构化状态；@persist 在类或方法级保存状态，默认 SQLite，并可 resume/fork；flow.usage_metrics 汇总一次 Flow 中所有 Crew、工具和直接 LLM 调用的 token 与成功请求数。[Flows](https://docs.crewai.com/en/concepts/flows)
统一 Memory API 会分析保存内容的 scope、category、importance，召回分数混合语义、recency、importance，提供 scope tree 和可插拔 StorageBackend，默认本地 LanceDB。[Memory](https://docs.crewai.com/en/concepts/memory)
内置 tracing 可记录 Agent 决策、任务时间线、工具、LLM、token/成本和错误；支持本地缓冲、明确同意后上传和 OpenTelemetry spans，宿主负责脱敏。[Tracing](https://docs.crewai.com/en/observability/tracing)

**建议。** 复刻 typed FlowState、统一 usage 摘要和本地脱敏事件，而不是引入完整 CrewAI。跨题长期 Memory 默认关闭；只保留当前题短期状态。AMP tracing 不进入官方路径，因为文档提示 trace 可能含 prompt/input/output。

**MVP 判断。** 本地展示适用性高：状态、SQLite 快照和指标都能用很小实现获得；统一 Memory、嵌入和外部 AMP 会增加调用、依赖和隐私治理成本。

## OpenHands：Action/Observation 与沙箱

**已确认。** OpenHands Software Agent SDK 提供 Python、TypeScript、REST API，核心仓库拥有 agents、tools、conversations、workspaces、events 和 REST/WebSocket API；工作区可在本地或 Docker/Kubernetes 临时环境中运行。[SDK README](https://github.com/OpenHands/software-agent-sdk)、[SDK docs](https://docs.openhands.dev/sdk/)
SDK 提供 Bash、文件编辑、浏览器、MCP 等工具和 REST Agent Server。早期 Runtime 架构将 Agent 与执行环境解耦：接收 Action，在沙箱中执行后回传 Observation；官方架构文档描述了 Docker、Action Executor、事件流、REST 通信和插件。[Runtime architecture](https://github.com/OpenHands/docs/blob/main/openhands/usage/architecture/runtime.mdx)
官方说明 Docker 沙箱提供安全、隔离、一致性、资源控制和可复现性；本地 Runtime 没有隔离。[Custom sandbox](https://docs.openhands.dev/openhands/usage/advanced/custom-sandbox-guide.mdx)

**建议。** 采用 Action（工具名、参数、调用 id）/Observation（状态、摘要、错误、耗时）协议和内存事件列表；数学 MVP 只允许纯函数验证器或受限计算器，禁止任意 shell。workspace/runtime 作为可替换接口，默认不创建容器。

**MVP 判断。** 事件协议中等适用，完整 Runtime 低适用。OpenHands 面向软件工程，Docker/Kubernetes、挂载、端口、插件和权限管理过重；沙箱本身不证明数学能力提升。

## Letta（可选）：版本化长期记忆

**已确认。** Letta 定位为带持久记忆、身份和长期适应能力的 stateful agents；活跃代码迁移到 Letta Code。[Letta](https://github.com/letta-ai/letta)、[Letta Code](https://github.com/letta-ai/letta-code)
Letta Code 的 MemFS 是 Git-backed memory filesystem，可查看/编辑记忆和技能，并通过 GitHub 同步；官方文档描述 /remember、/doctor、后台 dreaming 和 Agent review。[Memory & dreaming 源码](https://github.com/letta-ai/letta-docs-md/blob/main/configuration/memory/index.md)、[Memory prompt](https://github.com/letta-ai/letta-code/blob/main/src/agent/prompts/letta_root_memfs.md)

**建议与边界。** 可借鉴“长期记忆是可 diff、可回滚资源”，但当前数学评测不应开启自动 dreaming 或跨题记忆：自修改上下文会污染题间独立性。若实验，需单题 scope、白名单字段、reset 和审计。

## 面向本分支的最小组合

1. 用 LangGraph/CrewAI/OpenHands 的共同原语定义 JSON 可序列化 FlowState、ActionEvent、ObservationEvent，包含 run id、phase、budget、status 和脱敏摘要。
2. 用有限状态图实现顺序节点、一个条件分支和硬循环上限；未启用时不改变 solve 调用数。
3. 以本地快照和 usage metrics 支撑 Demo 审计，运行产物写入被忽略的 artifacts/run_id 目录。
4. 只提供数学验证器/纯函数计算器等受限工具，所有结果通过 Observation 返回。
5. 页面展示阶段图和脱敏事件；默认关闭外部 tracing、长期记忆和容器沙箱。

这些工程证据可以支持主观评分中的流程清晰度、模块协同、稳定性和可扩展性；任何能力提升结论仍需适用数据上的独立 A/B、成本和失败门验证。

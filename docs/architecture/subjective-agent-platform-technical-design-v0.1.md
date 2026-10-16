# 主观评测 Agent Workbench V0.1 技术设计

**状态：accepted，PRD 与技术方案已审核**  
**关联 PRD：** [V0.1 PRD](../prd/subjective-agent-platform-prd-v0.1.md)  
**关联风险记录：** [Risk Assessment](../risk-assessment-v0.1.md)  
**关联实验：** [Risk Spike Results](../risk-spike-v0.1-results.md)

## 1. 设计目标

V0.1 建立 Showcase Profile 的基线架构：LangGraph 管理可恢复的 Run，DeepAgents 提供角色级 Agent 能力，Tool Registry 管理工具调用，产品层保存事件和证据。

官方 Profile 保持独立。根目录 `user_agent.py` 不导入产品侧编排器、工具、存储或 Web 入口。

Spike 只验证了最小连接路径。本文把连接结果转换为产品接口，但不把产品 Adapter、SQLite 持久化、真实题目流程或 Python 完整隔离描述为已完成能力。

## 2. 总体架构

```text
Showcase API / Demo
        │
        ▼
Run Manager
        │
        ▼
LangGraph Orchestrator
        │
        ├─ Intake Node
        ├─ Planner DeepAgent
        ├─ Agent Execution Loop
        │    ├─ Solver DeepAgent
        │    ├─ Vision Adapter
        │    ├─ PythonMathTool
        │    ├─ Search Adapter（可选）
        │    └─ Human Review
        ├─ Lightweight VerificationHook
        └─ Synthesizer
        │
        ├─ Event Store / Checkpoint Store
        └─ Evidence Pack Exporter
```

### 2.1 分层职责

| 层 | 职责 | V0.1 状态 |
| --- | --- | --- |
| Profile | 选择 official 或 showcase 行为 | 必须实现 |
| Run Manager | 创建 Run、阶段、预算和结果 | 必须实现 |
| LangGraph | 状态图、Agent Loop、interrupt、resume | 已完成最小 Spike |
| DeepAgents | Planner、Solver 等角色级 Agent | 已完成最小 Spike，Adapter 待实现 |
| Model Adapter | 将 Intern API 转为统一模型接口 | 文本已验证，多模态 Adapter 待实现 |
| Tool Registry | 工具注册、权限、调用和结果记录 | 必须实现 |
| Persistence | 事件、checkpoint、产物索引 | 内存已验证，产品持久化待实现 |
| Evidence Export | 导出可回放的 JSON 结果 | 必须实现 |

## 3. Profile 与边界

### `official`

- 只加载现有官方入口和 baseline 依赖；
- 不加载 LangGraph、DeepAgents、Tool Registry 或产品存储；
- 不增加模型调用；
- 保持既有 JSON 输出和请求预算。

### `showcase_mvp`

- 开启 Run Manager、LangGraph、DeepAgents Adapter、Tool Registry 和 Evidence Pack；
- 可以使用 Intern 文本和多模态 Adapter；
- 可以按需调用 PythonMathTool；
- 使用独立产品预算；
- 结果不能解释为官方评分结果。

### `research_experimental`

V0.1 只保留 Profile 名称和扩展点，不实现 Debate、Reflection、长期记忆或生产级沙箱。

## 4. 核心状态

```text
RECEIVED
  → PLANNING
  → RUNNING
  → VERIFYING
  → SYNTHESIZING
  → COMPLETED

RUNNING / VERIFYING
  → NEEDS_REVIEW
  → RESUMED
  → RUNNING

任意阶段
  → FAILED
```

每次状态变化都生成事件。`RUNNING` 内部允许多个 Agent Loop 步骤，但每一步必须受运行时间、步数、工具调用数和重试次数限制。

## 5. 核心数据模型

```python
RunState = {
    "run_id": str,
    "profile": str,
    "status": str,
    "input_ref": str,
    "asset_refs": list[str],
    "plan": dict,
    "messages": list[dict],
    "tool_results": list[dict],
    "verification": dict,
    "evidence_refs": list[str],
    "budget": dict,
    "error": dict | None,
}
```

State 只保存产品需要恢复和导出的字段。完整 prompt、凭证、隐藏答案和完整图片不进入普通事件或 Evidence Pack。

## 6. Agent 与 Adapter 接口

```python
class ModelAdapter(Protocol):
    name: str

    def invoke(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        metadata: dict | None = None,
    ) -> ModelResult: ...
```

```python
class AgentAdapter(Protocol):
    name: str

    def run(self, state: RunState) -> AgentResult: ...
```

```python
class ToolAdapter(Protocol):
    name: str
    capabilities: tuple[str, ...]

    def invoke(self, request: ToolRequest) -> ToolResult: ...
```

DeepAgents 通过 `AgentAdapter` 接入，LangGraph 节点只依赖 Adapter，不直接依赖 DeepAgents 的内部状态结构。

## 7. Agent Execution Loop

每次循环执行以下步骤：

1. 从 `RunState` 读取当前任务和预算；
2. 调用当前 Agent 或模型 Adapter；
3. 判断返回的是最终结果、工具请求、复核请求还是错误；
4. 工具请求交给 Tool Registry；
5. 将工具结果以摘要形式写回状态；
6. 生成结构化事件并保存 checkpoint；
7. 判断是否继续、暂停或完成。

工具不是固定流水线的一部分。Agent 可以在任务需要计算时调用 PythonMathTool，在有图片时调用 Vision Adapter，在遇到冲突时请求人工复核。

## 8. Tool Registry 与 PythonMathTool

Tool Registry 统一处理：

- 工具注册和能力声明；
- Profile 权限；
- 参数摘要；
- 调用预算和超时；
- 结果状态；
- 事件写入。

`PythonMathTool` V0.1 采用实验性实现：独立 Python 子进程、AST 检查、SymPy/mpmath 白名单、超时和输出捕获。它不是完整沙箱，不能用于不可信任的任意代码执行。完整容器或远程隔离属于后续设计。

## 9. Vision Adapter

Vision Adapter 将文字和图片转换为模型消息。图片使用内容哈希和 `asset_ref` 管理，普通 trace 只保存类型、大小、哈希和结果摘要。

V0.1 已验证当前端点接受文字加 Base64 PNG 的最小请求，但以下能力仍属于实现任务：真实题目流程、多图输入、大小限制、超时处理和 Evidence Pack 关联。

## 10. Persistence 与 Evidence

V0.1 需要持久化以下对象：

- `runs`：Run 基本信息和当前状态；
- `events`：追加式运行事件；
- `checkpoints`：可恢复状态；
- `tool_calls`：工具摘要、耗时和结果状态；
- `artifacts`：Evidence Pack 和其他产物索引；
- `review_requests`：等待人工决定的请求。

首选 SQLite。内存 Checkpointer 只作为测试和 Spike 参考，不作为产品完成标准。

Evidence Pack 至少包含：

- Run ID、Profile 和版本；
- 阶段时间线；
- Agent 和工具摘要；
- 验证状态；
- 最终答案；
- 失败、恢复和人工决定记录。

## 11. Lightweight VerificationHook

V0.1 不实现完整数学证明器。Hook 只负责：

- 输出结构检查；
- 工具执行状态检查；
- 工具结果与最终答案的明显一致性检查；
- 变量、单位和数值冲突提示；
- 返回 `pass`、`conflict` 或 `unknown`。

接口必须允许后续替换为符号检查、数值反例、独立 Solver 或论文方案。

## 12. 预算与失败处理

产品 Profile 使用独立预算：

- 最大运行时间；
- 最大 Agent 步数；
- 最大工具调用数；
- 最大重试次数；
- 最大 Python 执行时间。

预算耗尽后停止新调度，保存原因并进入 `FAILED` 或 `NEEDS_REVIEW`。恢复时必须使用 checkpoint，不重复覆盖原始 Run 记录。

## 13. 依赖与安装

- `official` 依赖保持 baseline 不变；
- DeepAgents、LangGraph 和相关模型适配依赖只进入 Showcase 或本地扩展依赖；
- 干净环境需要单独验证安装；
- 产品依赖不得被根 `user_agent.py` 间接导入。

## 14. 验收

### 自动验收

- 现有测试继续通过；
- `python demo_server.py --help` 成功；
- official Profile 导入图不包含产品依赖；
- Showcase 可以创建 Run、调用工具、保存 checkpoint 并导出 JSON；
- Python 工具的正常、超时和明显危险输入有测试覆盖。

### 手工验收

- 文本数学题可以完成一次 live Run；
- Agent 至少主动调用一次 PythonMathTool；
- 工具失败后可以恢复或明确失败；
- 多模态端点状态有明确标识；
- Evidence Pack 可被回放，且不包含敏感信息。

## 15. 未决项

- 产品级 DeepAgents 状态映射字段；
- SQLite checkpoint 的迁移和并发策略；
- Vision Adapter 的真实题目输入限制；
- PythonMathTool 是否需要提前升级为容器沙箱；
- Verifier 后续研究路线。


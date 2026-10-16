# V0.1 Risk Spike Results

**日期：** 2026-10-15（Asia/Shanghai）  
**关联文档：** [V0.1 Risk Assessment](risk-assessment-v0.1.md)  
**实验范围：** 最小可行连接验证，不代表产品功能已经完成。

## 1. 环境

- Python：项目 `.venv`；
- 基础数学依赖：`sympy`、`mpmath` 已存在；
- Spike 依赖：在 `.venv` 中安装 `deepagents`、`langgraph`、`langchain-openai`；
- Intern：使用当前环境中的 API 配置，实验日志不保存凭证；
- 项目依赖文件和 official Profile 没有修改。

## 2. 结果总览

| Spike | 结果 | 结论 |
| --- | --- | --- |
| S1 DeepAgents + Intern Adapter | 通过（最小路径） | 当前 Intern API 可以完成文本调用和一个工具调用；产品 Adapter 仍需实现 |
| S2 LangGraph Agent Loop + Checkpoint | 通过（内存检查点） | 动态工具失败、interrupt、resume 和状态恢复可行；持久化和 DeepAgent 状态映射仍未验证 |
| S3 PythonMathTool 最小安全路径 | 通过（原型） | SymPy 计算、超时和明显危险代码拦截可行；AST 方案不是完整沙箱 |
| S4 Intern 多模态最小请求 | 通过（端点请求） | 当前配置接受文字加 Base64 PNG 请求；产品 Vision Adapter 和真实题目流程仍需实现 |

## 3. S1：DeepAgents + Intern Adapter

### 实验内容

使用 `langchain-openai` 构造 OpenAI 兼容模型客户端，并传入当前 Intern API。先执行一次文本请求，再通过 DeepAgents 注册一个最小函数工具，让 Agent 根据提示调用该工具并继续生成结果。

### 观察结果

- 文本请求成功；
- 模型返回 `AIMessage`；
- DeepAgents 工具调用成功；
- Agent 运行产生 4 条消息，其中包含 1 条工具消息；
- 工具调用结果可以从运行结果中读取。

### 结论

S1 的底层连接可行。V0.1 可以把 DeepAgents 放在角色级 Agent 层，把当前 Intern 客户端包装为模型 Adapter。

### 未覆盖

- 尚未接入项目自己的 `Tool Registry`；
- 尚未接入 Evidence Pack；
- 尚未验证长上下文、重试、流式输出和产品事件映射；
- 尚未验证 Agent 内部状态的持久化。

## 4. S2：LangGraph Agent Loop + Checkpoint

### 实验内容

构造一个最小 LangGraph：Planner 请求工具，工具第一次故意失败，图进入 `interrupt`，恢复时重新调用工具并完成。使用内存 Checkpointer 保存状态。

### 观察结果

- 首次运行进入 interrupt；
- checkpoint 显示下一步为 review；
- resume 后工具第二次调用成功；
- 工具调用次数为 2；
- 最终状态为 `completed:42`；
- 状态历史包含 7 个检查点记录。

### 结论

LangGraph 可以承载 V0.1 所需的基本 Agent Loop、失败暂停和恢复语义。LangGraph 适合作为 Run 控制层。

### 未覆盖

- 使用的是内存 Checkpointer，不是 SQLite；
- 节点使用确定性测试逻辑，不是 DeepAgent 实例；
- 尚未验证服务重启后的恢复；
- 尚未验证工具幂等键和重复执行保护。

## 5. S3：PythonMathTool 最小安全路径

### 实验内容

使用独立 Python 子进程运行受限代码。执行前检查 AST，只允许 `sympy`、`mpmath` 和少量数学调用；设置 3 秒超时；捕获标准输出和错误。

### 观察结果

| 输入 | 结果 |
| --- | --- |
| SymPy 解 `x**2 - 1` | 成功，输出 `[-1, 1]` |
| `while True: pass` | 3 秒后返回 `tool_timeout` |
| `import os` | 执行前拒绝 |
| `open(...).read()` | 执行前拒绝 |
| `import subprocess` | 执行前拒绝 |

### 结论

受限子进程可以支持 V0.1 的数学计算演示，并能提供超时和错误结果。`PythonMathTool` 可以进入 Showcase 设计，但必须保留显式限制和实验状态。

### 风险边界

这只是原型验证。AST 白名单不是完整安全边界，不能把它描述为生产级沙箱。对于不可信代码，后续仍需要容器或远程隔离环境。

## 6. S4：Intern 多模态最小请求

### 实验内容

生成一张无敏感信息的测试 PNG，将其编码为 Base64，构造包含文字和 `image_url` 的消息，通过当前 Intern 模型端点发送。

### 观察结果

- 请求成功；
- 模型返回 `yes`；
- 总响应时间约 25.57 秒；
- 请求使用当前配置的 `intern-s2` 模型；
- 图片没有写入实验日志。

### 结论

当前配置下，文字加 Base64 PNG 的最小请求路径可行。V0.1 可以保留 Vision Adapter，并把多模态能力标记为已完成端点级验证。

### 未覆盖

- 尚未测试真实几何题或函数图；
- 尚未验证多图输入；
- 尚未验证图片大小、格式和超时边界；
- 尚未接入 Intake、事件流和 Evidence Pack。

## 7. 边界与回归检查

额外执行了与 R8、R9 相关的检查：

- `scripts/check_workspace.py --offline`：通过；
- `python -m unittest discover -s tests -p "test_*.py"`：11 个测试通过；
- 导入根 `user_agent` 后，没有加载 `deepagents` 或 `langgraph` 模块；
- baseline 相关测试通过；
- 官方入口仍可在离线客户端下返回非空、可序列化结果。

## 8. 对 PRD Lite 的影响

### 可以保留

- LangGraph 作为 Run 控制层；
- DeepAgents 作为角色级 Agent 层；
- Agent 按需调用工具；
- PythonMathTool 的 Showcase 原型；
- Vision Adapter 接口和最小图文请求；
- Lightweight VerificationHook。

### 需要补充的约束

- V0.1 仍需要实现产品自己的 Adapter、Tool Registry、事件和 Evidence Pack；
- Checkpoint 必须从内存版本升级为产品持久化版本；
- Python 工具需要标明原型安全边界，不能称为完整沙箱；
- 多模态能力需要真实题目和输入限制测试；
- Agent Loop 需要步数、时间、工具次数和重试预算。

## 9. Spike 决策

本轮没有高风险失败，因此可以进入技术设计和 ADR 定稿阶段，但只能把结论写成“最小连接已验证”。以下内容仍保持 `proposed` 或 `experimental`：

- 产品级 DeepAgents Adapter；
- SQLite checkpoint；
- 生产级 Python 沙箱；
- 复杂数学 Verifier；
- 真实 Demo 的完整多模态题目流程。

# V0.1 Risk Assessment

**状态：accepted，Spike 结论已纳入设计**  
**关联需求：** [V0.1 PRD](prd/subjective-agent-platform-prd-v0.1.md)  
**目的：** 在正式技术设计和 ADR 定稿前，识别会改变 V0.1 架构、范围或验收标准的风险。

## 1. 评估方法

每个风险从两个维度评估：

- **影响**：风险发生后对架构、V0.1 交付或官方边界的影响；
- **不确定性**：当前是否缺少真实运行证据。

等级含义：

| 等级 | 含义 |
| --- | --- |
| 高 | 可能迫使我们更换架构、缩小 V0.1，或破坏官方边界 |
| 中 | 需要调整接口、验收方式或演示范围，但不一定改变总体架构 |
| 低 | 可以通过实现细节、文档或后续迭代处理 |

只有同时具有高影响和高不确定性的风险，才默认进入 Risk Spike。中风险问题可以在设计时处理，低风险问题不阻塞 V0.1。

## 2. 风险总表

| ID | 风险 | 影响 | 不确定性 | 决策 |
| --- | --- | --- | --- | --- |
| R1 | DeepAgents 无法稳定接入当前 Intern Chat API，或无法保留工具调用结果 | 高 | 高 | 最小路径通过；产品 Adapter 待实现 |
| R2 | LangGraph 无法可靠保存和恢复包含动态 Agent Loop 的状态 | 高 | 高 | 内存路径通过；持久化和幂等保护待验证 |
| R3 | Intern 当前可用端点不支持 V0.1 所需的图文输入 | 高 | 高 | 端点请求通过；真实题目流程待验证 |
| R4 | PythonMathTool 的受限执行边界不足，无法同时支持计算、超时和基本安全要求 | 高 | 高 | 原型通过；不是完整沙箱 |
| R5 | Agent Loop 无限调用工具、重复重试或消耗不可控 | 高 | 中 | 设计阶段处理，并做小型压力验证 |
| R6 | DeepAgents 内部状态无法映射到 Evidence Pack | 高 | 中 | 未关闭；纳入产品 Adapter 设计 |
| R7 | Verifier 产生错误安全感，或无法发现任何有意义的问题 | 中 | 高 | 未关闭；低成本实现后再验证 |
| R8 | 新增依赖导致干净环境安装失败或影响官方依赖 | 高 | 中 | 当前环境通过；仍需记录依赖边界 |
| R9 | Showcase 组件被根 `user_agent.py` 间接导入，破坏 official Profile | 高 | 中 | 已通过当前边界检查 |
| R10 | Trace、Evidence Pack 或错误日志泄露 prompt、凭证、图片或隐藏答案 | 高 | 中 | 设计阶段处理，并做脱敏测试 |
| R11 | Demo 依赖真实凭证、网络或模型响应，现场运行不稳定 | 中 | 中 | 设计真实模式和标注 replay 模式 |
| R12 | V0.1 范围扩张到完整前端、搜索、记忆和复杂协作 | 中 | 高 | 通过范围闸门控制，不做 Spike |

## 3. Spike 结果

S1–S4 已完成最小连接验证，结论记录在 [Risk Spike Results](risk-spike-v0.1-results.md)。没有高风险 Spike 失败，因此可以进入技术设计和 ADR 定稿，但不能把原型验证写成产品功能完成。

## 4. 原 Spike 记录

### Spike S1：DeepAgents + Intern Adapter

**对应风险：** R1、R6

**问题：** DeepAgents 是否能调用当前 Intern 模型，并把模型响应、工具调用和错误转换为产品可以记录的结果。

**最小实验：**

1. 用当前 `INTERN_API_BASE` 和 `INTERN_MODEL` 发起一次文本请求；
2. 接入一个最小函数工具；
3. 让 Agent 触发工具并继续生成最终结果；
4. 记录模型 ID、工具名、输入摘要、输出摘要、耗时和错误；
5. 如果端点支持，再发送一次文字加图片请求。

**通过条件：**

- 文本调用成功；
- 工具调用可以被 Tool Registry 观察；
- 失败可以转换为结构化错误；
- 结果可以进入 Evidence Pack；
- 图片能力明确标记为 `supported`、`unsupported` 或 `unverified`。

**失败处理：**

- DeepAgents 保留为可选角色层；
- 使用自定义 LangGraph 节点包装当前客户端；
- V0.1 降级为文本 Showcase，不修改 official Profile。

### Spike S2：LangGraph Agent Loop + Checkpoint

**对应风险：** R2、R5、R6

**问题：** 动态工具调用、失败、恢复和事件记录能否使用同一个可序列化状态。

**最小实验：**

```text
Planner
  → Agent 请求 Python 工具
  → 工具故意失败
  → 保存 checkpoint
  → resume
  → Agent 改变路径
  → 完成
```

**通过条件：**

- checkpoint 可以保存 Run 状态；
- resume 后不会重复执行已经成功的工具；
- 工具失败和恢复都有事件；
- Agent Loop 有最大步数或运行时间限制；
- 恢复后的结果可以导出。

**失败处理：**

- 将 Agent Loop 简化为有限状态节点；
- 暂不支持复杂子 Agent；
- 保留 checkpoint 和 Evidence Pack 接口。

### Spike S3：PythonMathTool 最小安全路径

**对应风险：** R4

**问题：** 受限 Python 执行是否足以支持数学演示，并能处理危险代码、异常和超时。

**最小实验：**

- 在独立子进程运行 SymPy 或 mpmath 计算；
- 先检查 AST 白名单；
- 设置运行时间限制；
- 捕获标准输出和错误；
- 测试正常计算、死循环、危险导入、任意文件读取和子进程创建。

**通过条件：**

- 正常数学计算可完成；
- 超时可以终止并返回 `tool_timeout`；
- 明显危险代码在执行前被拒绝；
- 工具进程失败不会让主服务退出；
- 结果、耗时和错误可以写入事件。

**边界：**

AST 白名单不是完整沙箱。如果实验无法提供足够的隔离，V0.1 只能把工具限制为受控演示，并将容器或远程沙箱列为后续前置条件。

### Spike S4：Intern 多模态最小请求

**对应风险：** R3

**问题：** 当前实际模型和端点是否接受文字与图片组成的消息。

**最小实验：**

1. 准备一张无敏感信息的几何图或函数图；
2. 构造文字加图片消息；
3. 发起一次请求；
4. 检查响应、错误、耗时和模型 ID；
5. 保存脱敏的请求摘要和结果摘要。

**通过条件：**

- 端点是否接受该消息格式有明确结论；
- 失败时能返回可诊断错误；
- 图片不进入普通 trace 的完整内容；
- Showcase 可以明确显示多模态能力状态。

**失败处理：**

V0.1 保留 `Vision Adapter` 接口，但演示降级为文本输入，不伪装成已支持多模态。

## 5. 设计阶段处理的风险

### R5：Agent Loop 预算失控

V0.1 即使不受官方 token 预算限制，也必须有产品级运行预算：

- 最大运行时间；
- 最大 Agent 步数；
- 最大工具调用数；
- 最大重试次数；
- 最大 Python 执行时间。

预算耗尽必须进入 `failed` 或 `needs_review`，并保留原因。

### R8：依赖和安装风险

DeepAgents、LangGraph 及其依赖应只进入 Showcase 或本地开发依赖。需要验证：

- 干净环境是否可以安装；
- 现有 `requirements.txt` 是否保持官方基线；
- `user_agent.py` 是否不导入产品侧依赖；
- Windows 环境是否支持所需运行方式。

### R9：官方边界风险

验收必须检查：

- 根 `user_agent.py` 的导入图不包含 Showcase 模块；
- official Profile 不创建产品数据库或工具注册中心；
- official Profile 不增加模型调用；
- baseline 文件没有变化。

### R10：证据泄露风险

Trace 和 Evidence Pack 只允许包含：

- 脱敏的阶段和状态；
- 工具名称、状态、耗时和摘要；
- 内容哈希和 Evidence ID；
- 可公开的最终结果。

不得写入 API key、完整 prompt、隐藏答案、完整图片或个人信息。

### R11：现场 Demo 风险

Demo 需要区分：

- `live`：真实调用模型或工具；
- `replay`：使用已保存运行记录；
- `unavailable`：凭证、网络或模型不可用。

Replay 不能伪装成实时运行。现场演示至少准备一条 live 路径和一条标注清楚的 replay 路径。

## 6. 非阻塞风险

以下项目不阻塞 V0.1：

- 最终 Verifier 论文路线；
- 长期记忆；
- Debate 或 Reflection；
- React/Vite 完整 Workbench；
- 多 Solver 比较；
- OpenTelemetry；
- 分布式执行。

这些内容只在 V0.1 基线稳定后重新评估。

## 7. Spike 后的设计门槛

在进入正式 `/to-spec` 和 accepted ADR 前，需要完成：

- 产品 Adapter 的状态和错误映射设计；
- SQLite 或其他产品持久化 checkpoint 设计；
- PythonMathTool 的实验性安全边界和运行预算；
- Vision Adapter 的真实题目输入限制；
- R6、R7 的剩余验证计划；
- R8、R9 的依赖和官方边界记录。

如果产品实现阶段发现 Spike 结论不适用，先更新 PRD Lite 的范围和成功标准，再修改技术设计。

## 8. 当前结论

V0.1 的高风险集中在四个底层连接点：

```text
DeepAgents ↔ Intern
LangGraph ↔ Agent Loop / checkpoint
Agent ↔ PythonMathTool
Intern ↔ 多模态输入
```

Verifier 目前不是架构阻塞项。它应先保持为轻量、可替换 Hook，等后续论文调研和独立实验决定投入方向。当前可以进入 `/to-spec` 和 ADR 草案定稿，但以下内容仍应标记为 `proposed` 或 `experimental`：产品级 DeepAgents Adapter、SQLite checkpoint、生产级 Python 沙箱、复杂数学 Verifier 和真实多模态题目流程。





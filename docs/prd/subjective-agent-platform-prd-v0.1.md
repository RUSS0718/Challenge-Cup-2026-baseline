# 主观评测 Agent Workbench V0.1 PRD

**状态：accepted，V0.1 产品范围已审核**  
**版本：V0.1**  
**适用 Profile：`showcase_mvp`**  
**官方 Profile：保持不变**

## 1. 产品目标

为数学智能体建立一个可恢复、可观察、可扩展的基线骨架，用于主观评测 Demo 和后续 Agent 能力迭代。

V0.1 的重点是验证底层架构边界，而不是证明数学正确率提升。系统需要能够把一次数学任务组织成可追踪的 Run，允许 Agent 按需调用工具，并保存可以回放的阶段状态和结果证据。

## 2. 用户与核心场景

### 2.1 评委演示者

在有限时间内展示一条真实运行链路：输入数学问题，规划任务，调用 Agent 或工具，记录运行状态，并导出结果证据。

### 2.2 Agent 工程师

查看一次 Run 的阶段、工具调用、失败原因和恢复位置，为后续替换 Agent、工具或 Verifier 提供稳定接口。

### 2.3 核心场景

1. **文本数学题求解**：输入题目，Planner 规划任务，Solver Agent 生成候选解，系统输出结构化结果。
2. **文字加图片题目**：输入题目文字和图片，Intake 保存图片引用，Intern Vision Adapter 将图文输入交给模型。
3. **按需计算**：Agent 判断需要数值或符号计算时调用 `PythonMathTool`，读取结果后继续任务。
4. **失败与恢复**：工具或 Agent 步骤失败后保存 checkpoint，Run 可以恢复、重试或进入人工复核状态。
5. **证据导出**：将阶段、工具结果、检查状态和最终答案导出为 JSON Evidence Pack。

## 3. V0.1 产品范围

### 3.1 包含范围

- `showcase_mvp` Profile；
- LangGraph Run 控制层；
- DeepAgents 角色级 Agent Adapter；
- Intern 文本模型 Adapter；
- Intern 多模态输入 Adapter 的最小可行接口；
- Agent 按需调用工具的执行循环；
- Tool Registry；
- `PythonMathTool` 的受限最小实现或可替换执行接口；
- Run、Stage、Event 和 checkpoint 数据模型；
- 失败、重试、恢复和人工复核的状态接口；
- Lightweight VerificationHook；
- JSON Evidence Pack 导出；
- 面向 Demo 的最小运行入口和健康检查。

### 3.2 架构边界

- LangGraph 管理 Run 生命周期、状态转移、checkpoint、interrupt 和 resume。
- DeepAgents 管理 Planner、Solver 或 Researcher 等角色级 Agent 能力。
- Agent 可以根据任务需要请求 Python、视觉或搜索工具，但所有工具调用必须经过 Tool Registry。
- Verifier 在 V0.1 只提供低成本、可替换的检查 Hook，不承诺完整数学证明。
- `official` Profile 不导入或调用上述 Showcase 组件。
- V0.1 不改变根目录 `user_agent.py`、官方调用预算、官方输出合同或 baseline 文件。

## 4. 运行模型

```text
Run
  → Intake
  → Planner Agent
  → Task Execution Loop
       ├─ Solver Agent
       ├─ Vision Adapter（有图片时）
       ├─ PythonMathTool（Agent 判断需要时）
       ├─ Search Tool（启用时）
       └─ Human Review（冲突或失败时）
  → Lightweight VerificationHook
  → Synthesizer
  → Evidence Pack
```

角色不是固定顺序执行的流水线。Agent 可以在执行循环中选择工具、继续推理、重试或请求复核。所有可观察动作都必须生成结构化事件。

## 5. 成功标准

### 5.1 架构成功标准

- `showcase_mvp` 可以创建一个带唯一 Run ID 的任务；
- Run 至少支持 `received`、`planning`、`running`、`verifying`、`completed` 和 `failed` 状态；
- Agent 可以通过 Adapter 调用当前 Intern 文本接口；
- 多模态 Adapter 可以表达文字加图片请求，真实端点能力由 Risk Spike 验证；
- Agent 可以按需请求 Python 工具；
- 每次工具调用都有工具名、状态、耗时、参数摘要和结果摘要；
- checkpoint 可以保存并恢复一次未完成 Run；
- 失败不会改变 `official` Profile 的行为。

Risk Spike 已验证以下最小连接路径：DeepAgents 文本与工具调用、LangGraph 内存 checkpoint / interrupt / resume、PythonMathTool 原型、Intern 文字加 Base64 PNG 请求。上述结果只证明连接可行，不证明产品 Adapter、持久化、真实题目流程或生产级安全已经完成。

### 5.2 展示成功标准

- 本地 Demo 可以完成一次文本数学题运行；
- 至少有一个场景展示 Agent 主动触发 Python 工具；
- 至少有一个场景展示工具失败后的恢复或明确失败结果；
- 可以导出 JSON Evidence Pack；
- 导出内容不包含 API key、完整 prompt、隐藏答案或个人信息；
- 页面或命令行可以清楚区分 `implemented`、`experimental`、`replay` 和 `planned` 状态。

### 5.3 质量成功标准

- 现有单元测试和 Demo 合同测试继续通过；
- `python -m unittest discover -s tests -p "test_*.py"` 继续通过；
- `python demo_server.py --help` 继续成功；
- 新增产品侧代码不会被根目录 `user_agent.py` 导入；
- 没有凭证时，Showcase 入口返回可诊断错误，不无限等待。

## 6. Verifier 的 V0.1 定义

V0.1 不选择最终数学验证理论，只保留可替换接口，并实现以下低成本检查：

- 输出是否满足结构合同；
- 工具是否成功返回；
- 最终答案是否引用工具结果；
- 变量、单位和数值是否出现明显冲突；
- 检查结果是否为 `pass`、`conflict` 或 `unknown`。

Verifier 的存在不等于数学结论已经被证明，也不用于宣称官方正确率提升。

## 7. 风险与待验证假设

以下问题已通过最小连接验证，但仍需在产品实现中完成：

1. 将 DeepAgents / Intern 最小连接包装成产品 Adapter；
2. 将内存 checkpoint 升级为产品持久化 checkpoint，并验证服务重启后的恢复；
3. 将图文请求包装为 Vision Adapter，并测试真实几何题、图片大小和超时边界；
4. 将 PythonMathTool 原型接入 Tool Registry，并保留其非沙箱声明；
5. 定义 DeepAgent 状态到 Evidence Pack 的字段映射；
6. 验证 Lightweight VerificationHook 至少能发现一类明显候选答案错误。

如果产品实现暴露出连接限制，应优先缩小 Showcase 范围或替换 Adapter，不直接修改官方 Profile。

## 8. 明确不包含

- 官方评分路径的框架替换或 Prompt 重写；
- 正确率提升结论；
- 完整数学证明系统；
- 多 Agent 框架并存；
- 生产级任意代码沙箱；
- 长期记忆和向量数据库；
- Debate、Reflection 或 RSI 自动改进；
- 分布式执行和多机调度；
- 面向所有数学题型的专门 Verifier。

## 9. 交付物

V0.1 交付以下可审查材料：

- 本 PRD Lite；
- Risk Assessment 和 Spike 记录；
- 经 Spike 修订后的技术设计文档；
- accepted ADR；
- V0.1 运行入口和最小 Demo；
- JSON Evidence Pack 示例；
- 对官方 Profile 隔离和测试结果的说明。

## 10. 产品决策与后续入口

Risk Spike 完成后，再决定：

- DeepAgents 与 LangGraph 的准确边界；
- 多模态模型的实际 Model ID 和 Adapter 形式；
- PythonMathTool 是否在 V0.1 提供真实执行，还是先提供接口和受控 Demo；
- Verifier 下一阶段采用符号、数值、独立 Solver 或其他路线；
- 是否需要进入 React/Vite Workbench，而不是继续使用轻量 Demo 页面。



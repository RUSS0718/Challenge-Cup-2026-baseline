# Challenge Cup 2026 — 88分数学推理基线

本仓库保存2026年10月11日官方评测得到 **88 correct / 12 incorrect / 0 invalid** 的数学推理智能体运行骨架。
来源提交为 `447a3a26b13141844bd1c529abd6f69d68db33a8`。运行代码与依赖清单逐字节导出；
本仓库使用独立的 Git 历史，`main` 为该基线，不包含旧仓库历史、实验数据、答案库或评测产物。

88分是一次官方观测结果，不保证复跑分数。完整旧仓库与原始评测证据保存在本地归档。
文件来源和 SHA-256 校验值见 [BASELINE.json](BASELINE.json)。

## 评分入口

平台从根目录导入 `user_agent.ReasoningAgent`，注入模型 client，然后调用：

```python
from user_agent import ReasoningAgent

agent = ReasoningAgent(client=official_client)
result = agent.solve(problem, metadata)
# result 为可 JSON 序列化字典；final_response 为非空字符串。
```

模型访问由注入的 client 提供。仓库不保存凭证、不提供本地 HTTP client，也不读取题集或标准答案。
安装运行依赖：

```shell
python -m pip install -r requirements.txt
```

依赖为 `sympy==1.13.3`、`mpmath==1.3.0`；其他运行依赖均为 Python 标准库。

## 架构与执行流程

1. **入口与截止控制**：根 `user_agent.py` 继承求解器，为每道题建立1150秒共享截止。
   支持 POSIX 主线程信号抢占；Windows或工作线程使用协作式截止。每次 solve 重置本题状态。
2. **首路独立求解**：识别题型、条件、定义域和答案形式，给出完整且紧凑的推导；
   完成一次必要复核后收束为“最终答案：...”。首路温度0.2，主调用最多16384 tokens。
3. **受控恢复**：根据返回内容决定是否续写、纠错或简短收口。所有路径共享最多6次 Agent 调用，
   续写不重置整题截止；平台 client 内部重试可能产生额外物理请求。
4. **条件式加路**：首路有可用答案、完整首路耗时占预算4%–28%、调用与时间预测均放得下时，
   尝试第二、第三路；每路启动前再次核对剩余时间，因此第三路可能不执行。
5. **候选选择与输出**：对答案做保守规范化，通过文本、受限 SymPy 等价判断分组投票；
   票数相同时优先首路。本地 verifier 的适用范围有限，不能视为通用正确性证明。

这里“可用答案”只表示通过该版本的可用性检查，不等于数学正确。
首路无可用答案时不启动额外独立路径，这是原始基线行为。

### 三路提示

| 路径 | 温度 | 提示重点 |
| --- | ---: | --- |
| 第一路 | 0.2 | 通用严谨求解、必要复核、及时收束 |
| 第二路 | 0.6 | 在通用提示后增加条件、解集完整性、必要充分性和边界检查 |
| 第三路 | 0.6 | 与第一路相同的提示，独立采样 |

第二、第三路不接收首路答案。基础提示见求解器的 `SYSTEM_PROMPT`；
第二路增量见 [path_prompts.py](implementations/candidates/sl_v3_cont/path_prompts.py)。
没有加入新增复算提示或草图规划提示。

### 预算

| 项目 | 上限 / 配置 |
| --- | ---: |
| 整题共享截止 | 1150秒 |
| 整题累计 Agent 调用 | 6次 |
| 主调用输出预算 | 16384 tokens |
| 完整推导续写 | 8192 tokens |
| 普通续写 / 纠错 | 各3072 tokens |
| 简短收口 | 512 tokens |
| 加路耗时窗口 | 首路耗时占整题4%–28% |

主调用配置 `thinking_mode=True`；部分恢复调用请求关闭思考。
实际思考模式与 token 统计取决于平台 client；不能把输出长度限制解释为内部推理预算保证。
保留的特殊题号分支不会增加预算，因为普通与扩展截止均为1150秒。

## 文件布局

```text
user_agent.py                         平台入口、单题截止
requirements.txt                      评分运行依赖
BASELINE.json                         原始提交与运行文件哈希
implementations/
  candidates/sl_v3_cont/
    user_agent.py                     求解、恢复、加路与选择
    path_prompts.py                   第二路提示增量
    postprocess.py                    输出规范化与收口辅助
    verifier.py                       受限确定性验证
  postprocess/normalizer.py            保守答案规范化
tests/                                无模型调用的冻结与路径回归
```

## 已知边界

- 原始版本向 client 传入请求级 `thinking_mode`。严格只接受
  `chat(messages, temperature, max_tokens)` 的 client 与该版本不兼容；
  导出不修复该问题，避免改变88分对应的行为。迁移至其他平台前需独立验收接口。
- Windows或工作线程的协作式截止不能保证抢占阻塞请求，调用超时需要平台 client 配合。
- 没有启用旧 Protection、答案库、RAG、Skills、旧架构回退或实验 selector。
- 规范化和候选一致不能证明数学正确；官方汇总日志无法提供逐题组件归因。
- 本仓库在 GitHub 上用于私有开发与保存基线；创建它不会自动更换赛事关联的提交仓库。

## 本地回归

无需 API key 或真实模型请求，使用 Python 标准库 unittest：

```shell
python -m unittest discover -s tests -v
```

测试检查运行文件哈希，以及真实入口下的第二路提示隔离、共享调用预算、续写、异常回退和状态重置。
它们确认导出结构与脚本行为，不产生新的数学能力或官方成绩结论。

## 产品设计文档

- [主观评测 Agent Workbench PRD](docs/prd/subjective-agent-platform-prd.md)
- [技术架构与开源项目机制映射](docs/architecture/subjective-agent-platform-technical-design.md)
- [开源 Agent 项目调研](docs/research/open_source_agent_landscape.md)
- [Codespace 初始化调研](docs/research/codespace-bootstrap-landscape.md)
- [成熟工程初始化蓝图](docs/engineering-bootstrap-plan.md)
- [黑客松冠军仓库调研](docs/research/hackathon-winning-repo-landscape.md)

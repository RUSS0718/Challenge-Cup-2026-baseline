# 主观评测工程分支说明

本文件把《基于 Intern-S1 的数学智能体设计与推理创新》比赛方案中与主观评测有关的要求，转换为本分支的开发边界。比赛方案是评分依据；本文件才是本分支的执行说明。

## 评分目标

客观评测的答案正确性占 60%。本分支的新增工程模块默认关闭，不能改变根目录 `user_agent.ReasoningAgent` 的官方评测路径。主观评测占 40%，分为：

- **推理策略与系统设计（10 分）**：考察系统架构完整性、任务拆解、推理规划、过程校验或模块协同、策略与数学问题的匹配度，以及稳定性、可复现性和工程完成度。A 档为 8–10 分，B 档为 5–7 分，C 档为 0–4 分。
- **展示质量（20 分）**：考察 Demo 是否稳定运行且交互完整，视频与技术报告是否清晰完整，结果文件是否规范、可复现。A 档为 16–20 分，B 档为 10–15 分，C 档为 0–9 分。
- **创新性与可扩展性（10 分）**：考察数学智能体机制、推理范式、协作方式、验证机制、应用场景延展的创新价值，以及迁移和持续扩展潜力。A 档为 8–10 分，B 档为 5–7 分，C 档为 0–4 分。

总分相同先比较客观正确性，再比较推理策略与系统设计，最后比较创新性与可扩展性。系统仍需输出可解析的 JSON 结果；接口或格式错误会导致客观题无法判分。

## 本分支边界

1. 根目录 `user_agent.py`、`implementations/` 和其默认请求预算是官方评分骨架。没有经过独立验收的改动不得接入默认路径。
2. 主观评测功能必须通过显式入口运行；任何新路由、校验器、工具、记忆或协作模块都以关闭为默认值，且未启用时不增加官方模型调用。
3. `demo_server.py` 只服务本地展示，不会被 `user_agent.py` 导入。Demo 的 trace 只能包含脱敏的步骤、状态和摘要，不得包含凭证、完整 prompt、隐藏答案或个人信息。
4. 本分支不携带实验题集、答案库、运行 raw、废弃 solver、旧脚本和历史实验文档。运行产物写入被忽略的 `artifacts/<run_id>/`，不进入提交分支。
5. 任何声称“能力提升”的结论都必须有独立、可复现的评测证据；Demo 可运行或结构测试通过只能证明工程可达性。

## 验收最低线

- `user_agent.py` 可导入；`ReasoningAgent(client=...).solve(problem, metadata)` 返回带非空 `final_response` 的可 JSON 序列化字典。
- 默认官方路径的调用预算、输出边界和失败回退保持可追踪。
- `python -m unittest discover -s tests -p "test_*.py"` 通过；若环境未安装 pytest，不以此为理由改变运行时依赖。
- `python demo_server.py --help` 成功；本地 Demo 的 `/health` 和 `/solve` 合同有测试覆盖。

## 合并纪律

本分支的目标是工程化和创新性展示，不是用主观功能换取客观分数。合入 `RUSS0718/MathAgent` `main` 前必须单独审查官方路径差异、默认开关、调用/令牌预算、依赖安装和干净环境入口；没有这组证据时只保留在本分支。

## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues at `RUSS0718/MathAgent`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the five canonical state labels `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, and `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: read the root `GLOSSARY.md` and relevant records in `docs/adr/` when present. Add them when domain terms or consequential decisions need recording. See `docs/agents/domain.md`.

## Development workflow

Follow the Matt Pocock engineering flow and keep every phase reviewable:

```text
Product Goal
  → Research
  → Risk Spike
  → Technical Design + Spec
  → Repository Inspection
  → Implementation Plan + Acceptance Contract
  → Short-lived branch
  → Vertical Slice
  → Incremental TDD Implementation
  → Eval / Regression
  → Demo Hardening
  → Code Review + Simplification
  → Release Gate
  → Retro / Environment Improvements
```

Each phase writes an artifact and an exit condition. A failed risk spike returns to design; a failed acceptance gate returns to the smallest owning slice. Do not start product implementation before the PRD, technical design, task contract and acceptance cases are reviewable.

For each slice: write a failing test or executable acceptance case, implement the smallest change, run the focused check, run the relevant full suite, review the diff, and commit one logical change. Keep official baseline files byte-stable unless a release decision explicitly authorizes a new baseline.

The repository setup contract is documented in `docs/engineering-bootstrap-plan.md`; the baseline and product-sidecar boundary are documented in `BASELINE.json`, `docs/release-boundary.md`, and `GAP.md`.

## 搜索与检查入口

搜索代码时使用 `rg` 或 `rg --files`，默认排除 `.venv/`、`__pycache__/`、`.pytest_cache/`、`.ruff_cache/`、`artifacts/` 和构建产物；不要递归读取虚拟环境。运行仓库合同检查使用 `python scripts/check.py --offline`，产品发布检查使用 `python scripts/check_showcase_release.py`。

## Git 分支与提交规范

创建或重命名分支、提交代码、合并分支或记录发布时，先读取 [`docs/engineering/commit-convention.md`](docs/engineering/commit-convention.md)。集成分支不使用工具前缀；提交主题使用 `type(scope): 中文描述`，例如 `feat(showcase): 增加 Run 快照与 Profile 边界`。新提交遵循该规范，已有历史不主动重写。

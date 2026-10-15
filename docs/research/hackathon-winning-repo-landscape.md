# 黑客松冠军仓库的工作流调研

**日期：2026-10-13**
**目的：提取高质量黑客松仓库的交付习惯，转化为本分支的初始化标准**

## 观察到的共同结构

### 1. README 是评委入口，不是项目简介

[BlackBox DataHub](https://github.com/alejandro-publius/blackbox-datahub) 把架构、验收、无编辑真实运行、评测结果、评委评分卡和 Demo 脚本直接放在仓库入口；仓库还把后端、前端、评测、示例运行和文档清楚分开。

[PostPrism](https://github.com/zelinewang/postprism) 的 README 同时提供 Quick Start、Hosted Demo、Architecture、Setup、Technical Deep Dive，并明确区分 credentialed backend 和 front-end-only simulation。

[HackathonHero](https://github.com/GengGao/hackathon-agent) 提供一条命令启动、Demo 视频、截图、Gap/Roadmap、分类论证、跨平台 setup 脚本和本地运行说明。

### 2. 先交付一个垂直切片，再展示完整架构

[Multi-App AI Agent Hackathon 的工作文档](https://github.com/SaurabhVelankar/multi-app-ai-agent-hackathon/blob/main/Hackathon.md) 明确要求：一个端到端流程、至少三个外部应用、显式状态/Agent/边/人工复核/失败模式、可靠性说明和两分钟 Demo。它把“架构很大”和“当天能跑通一条链路”同时作为完成条件。

### 3. 运行结果必须可观察、可验证、可复盘

BlackBox 提供 `docs/ACCEPTANCE.md`、`evals/results/`、真实运行样例和 `docs/JUDGE_SCORECARD.md`；PostPrism 提供并行运行、进度事件、截图和循环保护；HackathonHero 提供 SQLite、SSE、工具调用、产物生成、Gap tracker 和跨平台 setup。

### 4. Demo 可以有模拟模式，但必须诚实标注

PostPrism 明确说明 hosted demo 是前端模拟，不访问账号、不发布内容；它同时保留真实后端路径和局限说明。这个做法适合我们的联网搜索、工具调用和人工复核展示：可以提供 replay，但不能把 replay 伪装成实时模型结果。

### 5. README 要先讲问题、证据和限制，再讲技术栈

成熟仓库通常先说明：解决什么具体问题、用户如何运行、一次运行怎样证明完成、失败时会发生什么。框架、模型和供应商放在架构说明中，而不是让评委先阅读依赖列表。

## 转化为本项目的仓库形态

```text
README.md                    # 30 秒定位、5 分钟启动、Demo 入口
DEMO_SCRIPT.md               # 2–5 分钟现场演示脚本
GAP.md                       # 当前完成、缺口、下一步

.devcontainer/
  devcontainer.json           # 一键 Codespace 环境
  post-create.sh              # 幂等安装和离线检查

backend/ / product/          # 产品侧车（待实现）
frontend/                    # Workbench UI（待实现）
evals/                       # 可提交的合成/演示验收，不放官方 raw
examples/                    # 可检查的运行证据和导出样例
docs/
  ARCHITECTURE.md
  ACCEPTANCE.md
  JUDGE_SCORECARD.md
  RELIABILITY.md
  DEMO_SCRIPT.md
scripts/
  bootstrap.ps1
  bootstrap.sh
  check_workspace.py
.github/
  workflows/quality.yml
  CODEOWNERS
```

当前分支已具备产品 PRD、技术架构、开源项目调研和最小 Web Demo；后续初始化应补齐上面的评委入口文档和可复现 setup。

## 推荐工作流

1. **开工前**：写一页问题定义、评审标准和 Demo 场景；不先堆框架。
2. **第一条链路**：从输入到一个可观察、可导出的真实结果，保持垂直切片。
3. **工程包装**：加入状态、事件、失败、重试、产物和一键 setup。
4. **证据补齐**：每个核心功能有 acceptance case、运行样例和已知限制。
5. **演示彩排**：准备 happy path、故障 path 和 replay path；演示失败不会让系统卡死。
6. **评委材料**：README、架构图、评分卡、Demo 脚本、视频、技术方案和结果包保持同一术语。
7. **发布前**：干净 Codespace 从零启动，运行 quality checks，检查秘密和大文件，再创建 PR。

## 对数学 Agent 的具体要求

- 快速启动必须展示一个数学题的完整闭环：条件 → 规划 → 求解 → 验证 → 解答；
- 复杂架构中的每个角色都要绑定数学职责，不能只有空壳名称；
- 真实搜索、工具调用和子 Agent 要显示输入摘要、输出摘要、状态和耗时；
- 失败演示要说明是搜索失败、工具失败、模型失败还是验证不适用；
- `success` 只表示流程完成，不自动表示数学结论正确；
- README 和评分卡同时列出已验证、结构已实现、计划中的能力；
- 官方评分入口、产品 Demo、实验 Profile 和运行产物分别管理。

## 采用的冠军模式与本项目边界

| 模式 | 本项目采用 | 说明 |
| --- | --- | --- |
| 一键启动 | 采用 | Codespace/本地 setup，离线检查先成功 |
| 2–5 分钟 Demo | 采用 | 数学闭环、研究检索、故障恢复三段脚本 |
| 架构大、垂直切片小 | 采用 | 展示完整图，先实现一条真链路 |
| 运行证据目录 | 采用 | 只放脱敏、可提交的样例；原始运行仍进 ignored artifacts |
| 前端模拟/replay | 采用 | 必须标记 replay，不能伪装实时结果 |
| 真实集成路径 | 采用 | Search/Tool/Official Solver 分别有 Adapter 和失败边界 |
| 大量依赖同时引入 | 不采用 | 只选一个主编排实现，其余能力通过接口搬运 |
| 没有失败限制的“成功” | 不采用 | 所有 success 都要说明语义、验证范围和局限 |

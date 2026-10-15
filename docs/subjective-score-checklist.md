# 主观评分证据清单

该清单把比赛方案的主观评分要求落到可审查材料上。

## 推理策略与系统设计（10）

- [x] 根入口、预算边界、候选完整性保护和输出归一化有清晰职责。
- [x] 调用图与默认开关记录在 `docs/architecture.md`。
- [ ] 过程校验、题型路由和协作机制进入默认路径前完成独立证据。

## 展示质量（20）

- [x] `demo_server.py` 提供稳定的 `/health`、`/solve` 和浏览器页面。
- [x] 输入错误和模型错误有可复现的 HTTP 状态与脱敏响应。
- [ ] 视频、技术报告和最终结果包由提交阶段补齐。

## 创新性与可扩展性（10）

- [x] Demo 与官方入口分离，未来模块可以单独展示而不改变客观评分。
- [x] 新模块必须有显式开关、单独测试和可追踪的调用成本。
- [ ] 任何具体创新机制都要在适用数据上完成独立评测后再宣称有效。

## 下一阶段文档

- 产品范围与 MVP：[PRD](prd/subjective-agent-platform-prd.md)
- 技术实现与评分映射：[技术架构文档](architecture/subjective-agent-platform-technical-design.md)
- 开源机制来源：[项目调研](research/open_source_agent_landscape.md)

# Git 分支与提交规范

**状态：** accepted  
**适用范围：** 本仓库后续创建分支、提交、合并和发布记录。  
**权威入口：** 根目录 `AGENTS.md` 指向本文件；规则变化时只修改本文件和入口摘要。

## 分支命名

集成分支使用产品或版本名称：

```text
showcase-agent-v0.1
```

短期工作分支使用工作类型前缀：

```text
feat/<scope>-<slug>
fix/<scope>-<slug>
docs/<slug>
chore/<slug>
```

示例：

```text
feat/showcase-run-contract
feat/langgraph-loop
fix/redaction-summary
docs/release-guide
```

分支名使用小写英文、数字和连字符；不使用个人、工具或聊天平台前缀。

## 提交格式

每个提交使用：

```text
<type>(<scope>): <中文描述>
```

`type` 使用以下固定集合：

| type | 用途 |
| --- | --- |
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `refactor` | 不改变行为的重构 |
| `test` | 测试变更 |
| `docs` | 文档变更 |
| `chore` | 依赖、脚本和维护工作 |
| `build` | 构建配置 |
| `ci` | CI/CD 配置 |
| `perf` | 性能优化 |
| `revert` | 回滚 |

`scope` 使用小写英文模块名，例如 `showcase`、`graph`、`tools`、`vision`、`evidence`、`api`、`redaction`、`deps`、`release`、`docs`。

主题使用中文动词开头，直接说明结果，不以句号结尾：

```text
feat(showcase): 增加 Run 快照与 Profile 边界
feat(graph): 增加 LangGraph 动态执行循环
fix(redaction): 修复完整图片字段泄漏
test(api): 增加 Showcase API 合同测试
docs(spec): 发布 V0.1 实现规范
chore(deps): 锁定 Showcase 产品依赖
```

## 提交边界

- 一个提交只表达一个可回滚的逻辑变化。
- 行为修复必须包含对应的回归测试或可执行验收证据。
- 文档、测试、依赖和代码可以分开提交，除非它们共同构成一个不可拆分的切片。
- 提交正文只在需要解释原因、边界或验证方式时添加，正文使用中文。
- 不使用 `update`、`misc`、`临时提交`、`完成所有功能` 等无法说明结果的主题。
- 新提交使用本规范；已有历史提交不主动重写，除非用户明确要求整理历史。

## Issue 关联

在正文或 PR 描述中使用：

```text
Refs: #9
```

只有确实完成并希望关闭 issue 时使用：

```text
Closes: #9
```

破坏性变更在正文末尾使用 `BREAKING CHANGE:` 说明迁移影响。

## 完成检查

提交前确认：提交主题符合格式、改动只覆盖一个逻辑切片、测试或验收证据已运行、官方 baseline 未被意外修改、没有凭证或运行 raw 进入提交。

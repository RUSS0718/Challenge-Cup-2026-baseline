# Acceptance Gates

每个垂直切片必须通过对应门禁后才能进入下一阶段。

| Gate | 证据 |
| --- | --- |
| Entry | `user_agent.py` 可导入，最小 `solve()` 返回非空 `final_response` |
| Offline | 无 API Key 时 `scripts/check_workspace.py --offline` 通过 |
| Quality | `uv run pre-commit run --all-files` 和 `uv run pytest -q` 通过 |
| Demo | `/health`、`/solve`、错误状态和最小浏览器流程可运行 |
| Evidence | 每个阶段有结构化事件，结果可导出和回放 |
| Release | clean Codespace 重建通过，官方文件哈希/返回合同无变化 |

失败门必须保留证据，修复后重新运行同一门禁；不得用删除失败记录替代修复。

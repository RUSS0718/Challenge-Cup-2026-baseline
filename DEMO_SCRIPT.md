# MathAgent Demo Script

目标是用 3–5 分钟展示一个完整数学任务，而不是只展示模型输出。

1. 打开 Workbench，说明题目和目标格式。
2. 展示 Intake 提取的条件、未知量、定义域和子问题。
3. 展示 Planner 生成的有限求解步骤和预算。
4. 展示 Solver/Verifier 的候选、检查依据、工具调用和状态事件。
5. 人为触发一次工具或搜索失败，展示 checkpoint、重试或 needs-review。
6. 恢复运行，导出 JSON/Markdown 证据包。
7. 最后说明：官方 `user_agent.py` 仍保持独立基线；产品侧车服务数学求解的工程连续性、解释性和复核性。

演示必须明确区分实时运行、回放运行和计划中的功能。

## V0.1 Showcase 路径

无凭证时使用确定性的回放证据：

```shell
python showcase_server.py --host 127.0.0.1 --port 8090
python scripts/check_showcase_release.py
```

浏览器页面通过 `POST /api/runs` 创建 live Run，随后读取事件和 Evidence
Pack；`docs/replay/showcase-replay-v0.1.json` 明确标为 replay，其中包含一次
Python 工具超时、checkpoint 恢复和最终结果。Python 工具显示为 experimental，
多模态端点在没有真实题目输入或凭证时显示为 unavailable。

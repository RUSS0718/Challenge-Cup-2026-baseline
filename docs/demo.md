# Demo 使用说明

Demo 是主观评测的展示入口，不是官方提交入口。它使用同一个根 `ReasoningAgent`，便于展示实际 trace 和失败回退；它不会读取题集或答案库。

## 启动

```shell
$env:INTERN_API_KEY = "..."
python demo_server.py --host 127.0.0.1 --port 8080
```

打开 `http://127.0.0.1:8080/`，输入题目后点击“求解”。

## HTTP 合同

- `GET /health`：返回 `{"status":"ok"}` 类健康信息，不访问模型。
- `POST /solve`：接收 `{"problem": "...", "metadata": {}}`，返回官方 `solve()` 字典。
- 非法 JSON、空题目和非对象 metadata 返回 400；模型或配置错误返回脱敏的 502。

访问日志不记录题目、答案或请求头。凭证只由 `llm_client.py` 从环境变量或未跟踪 `.env` 读取。

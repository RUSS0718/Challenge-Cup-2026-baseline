"""Local-only Web Demo for the official mathematical reasoning entry.

The Demo is a presentation surface. It is never imported by ``user_agent`` and
therefore cannot change the platform scoring path or its default call budget.
"""

from __future__ import annotations

import argparse
import html
import json
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from llm_client import InternChatClient
from user_agent import ReasoningAgent

MAX_BODY_BYTES = 1_000_000


class MathAgentServer(ThreadingHTTPServer):
    """Serve the Demo with a lazy agent factory so health stays credential-free."""

    def __init__(
        self,
        address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        agent_factory: Callable[[], ReasoningAgent] | None = None,
    ) -> None:
        """Bind the listening address and optional testable agent factory."""

        super().__init__(address, handler)
        self.agent_factory = agent_factory or (lambda: ReasoningAgent(InternChatClient()))


class DemoHandler(BaseHTTPRequestHandler):
    """Expose a small HTML page, health probe, and JSON solve endpoint."""

    server_version = "MathAgentDemo/1.0"

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler protocol
        """Return the page or a credential-free health response."""

        if self.path == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok", "service": "math-agent-demo"})
            return
        if self.path == "/":
            body = self._page().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler protocol
        """Validate one problem and return the agent's JSON result."""

        if self.path != "/solve":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY_BYTES:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_body_size"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
            return
        if not isinstance(payload, dict) or not isinstance(payload.get("problem"), str):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "problem_must_be_string"})
            return
        problem = payload["problem"].strip()
        if not problem:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "problem_must_be_non_empty"})
            return
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "metadata_must_be_object"})
            return
        try:
            result = self.server.agent_factory().solve(problem, metadata)  # type: ignore[attr-defined]
            if not isinstance(result, dict) or not isinstance(result.get("final_response"), str):
                raise TypeError("agent_result_contract")
        except Exception as exc:  # noqa: BLE001 - keep HTTP errors sanitized
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"error": "agent_unavailable", "error_type": type(exc).__name__},
            )
            return
        self._send_json(HTTPStatus.OK, result)

    def log_message(self, _format: str, *_args: Any) -> None:
        """Keep prompts, answers, and credentials out of the Demo's access log."""

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        """Write one UTF-8 JSON response with a stable content type."""

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _page() -> str:
        """Return the self-contained browser page used for the subjective Demo."""

        title = html.escape("数学推理智能体 Demo")
        return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{title}</title>
<style>body{{font:16px system-ui;max-width:900px;margin:40px auto;padding:0 20px}}
textarea{{width:100%;min-height:160px}}button{{margin-top:12px;padding:8px 20px}}
pre{{white-space:pre-wrap;background:#f4f4f4;padding:16px;border-radius:8px}}</style></head>
<body><h1>{title}</h1><p>官方评分骨架的本地展示入口。新增主观功能默认不接入评分链路。</p>
<textarea id="problem" placeholder="输入数学问题"></textarea><br><button id="solve">求解</button>
<pre id="result">等待输入…</pre><script>
const button=document.getElementById('solve'); const result=document.getElementById('result');
button.onclick=async()=>{{button.disabled=true;result.textContent='处理中…';try{{
 const r=await fetch('/solve',{{method:'POST',headers:{{'Content-Type':'application/json'}},
 body:JSON.stringify({{problem:document.getElementById('problem').value}})}});
 result.textContent=JSON.stringify(await r.json(),null,2);
}}catch(e){{result.textContent='请求失败：'+e;}}finally{{button.disabled=false;}}}};
</script></body></html>"""


def create_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    *,
    agent_factory: Callable[[], ReasoningAgent] | None = None,
) -> MathAgentServer:
    """Create a Demo server without starting its event loop."""

    return MathAgentServer((host, port), DemoHandler, agent_factory)


def main() -> None:
    """Parse local binding options and serve until interrupted."""

    parser = argparse.ArgumentParser(description="Local math-agent presentation Demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    with create_server(args.host, args.port) as server:
        print(f"Demo running at http://{args.host}:{args.port}/")
        server.serve_forever()


if __name__ == "__main__":
    main()

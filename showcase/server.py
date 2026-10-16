"""Local Showcase API and browser vertical slice."""

from __future__ import annotations

import argparse
import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from .evidence import EvidencePackExporter
from .run_service import RunNotFoundError, RunService, RunValidationError
from .verification import LightweightVerificationHook

MAX_BODY_BYTES = 1_000_000


class ShowcaseServer(ThreadingHTTPServer):
    """HTTP server carrying explicit product-side dependencies."""

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler], service: RunService):
        super().__init__(address, handler)
        self.run_service = service
        self.verifier = LightweightVerificationHook()
        self.evidence_exporter = EvidencePackExporter()


class ShowcaseHandler(BaseHTTPRequestHandler):
    """Expose health, Run, event, resume, evidence, and browser endpoints."""

    server_version = "MathAgentShowcase/0.1"

    @property
    def application(self) -> ShowcaseServer:
        return self.server  # type: ignore[return-value]

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler protocol
        path = urlsplit(self.path).path.rstrip("/") or "/"
        if path == "/health":
            self._send_json(HTTPStatus.OK, self.application.run_service.health())
            return
        if path == "/":
            body = _page().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        run_id, suffix = _run_route(path)
        if run_id is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            if suffix == "":
                self._send_json(HTTPStatus.OK, self.application.run_service.get_run(run_id))
            elif suffix == "/events":
                self._send_json(HTTPStatus.OK, {"run_id": run_id, "events": self.application.run_service.get_events(run_id)})
            elif suffix == "/evidence":
                snapshot = self.application.run_service.get_run(run_id)
                events = self.application.run_service.get_events(run_id)
                verification = self.application.verifier.verify(snapshot, _tool_results(events))
                pack = self.application.evidence_exporter.export(
                    snapshot,
                    events=events,
                    tool_results=_tool_results(events),
                    verification=verification,
                )
                self._send_json(HTTPStatus.OK, pack)
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
        except RunNotFoundError as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": exc.category})

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler protocol
        path = urlsplit(self.path).path.rstrip("/") or "/"
        payload = self._read_json()
        if payload is None:
            return
        if path == "/api/runs":
            try:
                snapshot = self.application.run_service.create_run(payload)
            except RunValidationError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": exc.category})
                return
            self._send_json(HTTPStatus.CREATED, snapshot)
            return
        run_id, suffix = _run_route(path)
        if run_id is not None and suffix == "/resume":
            try:
                snapshot = self.application.run_service.get_run(run_id)
                if snapshot["status"] not in {"FAILED", "NEEDS_REVIEW"}:
                    self._send_json(HTTPStatus.CONFLICT, {"error": "run_not_reviewable"})
                    return
                self.application.run_service.append_event(
                    run_id,
                    {"type": "resume_requested", "status": "RESUMED", "stage": "solving", "summary": "resume requested"},
                )
                resumed = self.application.run_service.transition(
                    run_id, status="RESUMED", stage="solving", error=None
                )
                self._send_json(HTTPStatus.OK, resumed)
            except RunNotFoundError as exc:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": exc.category})
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def _read_json(self) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY_BYTES:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_body_size"})
            return None
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
            return None
        if not isinstance(payload, dict):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "body_must_be_object"})
            return None
        return payload

    def _send_json(self, status: HTTPStatus, payload: MappingLike) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: Any) -> None:
        """Keep problem text, credentials, and provider output out of access logs."""


class MappingLike(dict[str, Any]):
    """Type alias substitute accepted by json.dumps without importing typing.Mapping."""


def create_server(
    host: str = "127.0.0.1",
    port: int = 8090,
    *,
    service: RunService | None = None,
) -> ShowcaseServer:
    """Create a local Showcase server without starting its event loop."""

    return ShowcaseServer((host, port), ShowcaseHandler, service or RunService())


def serve(host: str = "127.0.0.1", port: int = 8090) -> None:
    """Run the local Showcase server until interrupted."""

    with create_server(host, port) as server:
        print(f"Showcase running at http://{host}:{port}/")
        server.serve_forever()


def _run_route(path: str) -> tuple[str | None, str]:
    prefix = "/api/runs/"
    if not path.startswith(prefix):
        return None, ""
    remainder = path[len(prefix) :]
    if not remainder:
        return None, ""
    parts = remainder.split("/", 1)
    return parts[0], (f"/{parts[1]}" if len(parts) == 2 else "")


def _tool_results(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in events if event.get("type") == "tool_completed"]


def _page() -> str:
    title = html.escape("MathAgent Showcase Workbench")
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{title}</title>
<style>body{{font:16px system-ui;max-width:960px;margin:36px auto;padding:0 20px}}textarea{{width:100%;min-height:120px}}button{{margin:10px 8px 10px 0;padding:8px 18px}}pre{{white-space:pre-wrap;background:#f4f4f4;padding:14px;border-radius:8px}}.badge{{display:inline-block;padding:3px 8px;border-radius:12px;background:#e6f4ea}}</style></head>
<body><h1>{title}</h1><p>showcase_mvp：live / replay / experimental / unavailable 状态会单独标记。</p>
<textarea id="problem" placeholder="输入数学题目"></textarea><br><button id="run">创建 Run</button>
<span id="state" class="badge">等待输入</span><pre id="result">Run ID、阶段、事件和 Evidence Pack 将显示在这里。</pre>
<script>
const problem=document.getElementById('problem'), state=document.getElementById('state'), result=document.getElementById('result');
document.getElementById('run').onclick=async()=>{{state.textContent='live';try{{
 const created=await fetch('/api/runs',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{problem:problem.value}})}}).then(r=>r.json());
 const events=await fetch('/api/runs/'+created.run_id+'/events').then(r=>r.json());
 const evidence=await fetch('/api/runs/'+created.run_id+'/evidence').then(r=>r.json());
 state.textContent=created.status+' / '+created.stage;
 result.textContent=JSON.stringify({{run:created,events,evidence}},null,2);
}}catch(error){{state.textContent='unavailable';result.textContent=String(error)}}}};
</script></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description="Local subjective-evaluation Showcase API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()

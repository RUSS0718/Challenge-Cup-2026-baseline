"""Contract tests for the local Web Demo presentation surface."""

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from demo_server import DemoHandler


class FakeAgent:
    """Return a stable result without calling a model provider."""

    def __init__(self, calls):
        self.calls = calls

    def solve(self, problem, metadata):
        """Record one request and return the public solve shape."""
        self.calls.append((problem, metadata))
        return {"final_response": "2", "trace": [{"step": "fake"}]}


class DemoServerTest(unittest.TestCase):
    """Keep health, browser, validation, and solve contracts deterministic."""

    def setUp(self):
        """Start an isolated server with a model-free agent factory."""
        self.calls = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), DemoHandler)
        self.server.agent_factory = lambda: FakeAgent(self.calls)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)

    def tearDown(self):
        """Stop the isolated server and release its socket."""
        self.connection.close()
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def request(self, method, path, payload=None):
        """Send one JSON or browser request to the test server."""
        body = None
        headers = {}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        self.connection.request(method, path, body=body, headers=headers)
        response = self.connection.getresponse()
        return response.status, response.getheader("Content-Type", ""), response.read()

    def test_health_and_page_are_available_without_agent_call(self):
        """Presentation surfaces are reachable before credentials are configured."""
        status, content_type, body = self.request("GET", "/health")
        self.assertEqual(200, status)
        self.assertIn("application/json", content_type)
        self.assertEqual("ok", json.loads(body)["status"])
        status, content_type, body = self.request("GET", "/")
        self.assertEqual(200, status)
        self.assertIn("text/html", content_type)
        self.assertIn("数学推理智能体 Demo", body.decode("utf-8"))
        self.assertEqual([], self.calls)

    def test_solve_returns_public_result_and_metadata(self):
        """The Demo forwards only validated problem and metadata values."""
        status, content_type, body = self.request(
            "POST", "/solve", {"problem": "计算 1+1", "metadata": {"source": "demo"}}
        )
        self.assertEqual(200, status)
        self.assertIn("application/json", content_type)
        self.assertEqual("2", json.loads(body)["final_response"])
        self.assertEqual([("计算 1+1", {"source": "demo"})], self.calls)

    def test_invalid_payload_is_rejected(self):
        """Empty or malformed user input receives a stable 400 response."""
        status, _, body = self.request("POST", "/solve", {"problem": " "})
        self.assertEqual(400, status)
        self.assertEqual("problem_must_be_non_empty", json.loads(body)["error"])
        self.assertEqual([], self.calls)


if __name__ == "__main__":
    unittest.main()

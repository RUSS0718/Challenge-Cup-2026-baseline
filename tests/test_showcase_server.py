"""HTTP contract tests for the Showcase API and browser slice."""

from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection

from showcase.run_service import RunService
from showcase.server import ShowcaseHandler, ShowcaseServer


class FailingAgent:
    def run(self, _request):
        raise TimeoutError("provider timeout")


class ShowcaseServerTest(unittest.TestCase):
    def setUp(self):
        self.server = ShowcaseServer(("127.0.0.1", 0), ShowcaseHandler, RunService())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)

    def tearDown(self):
        self.connection.close()
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        self.server.run_service.close()

    def request(self, method, path, payload=None):
        body = None
        headers = {}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        self.connection.request(method, path, body=body, headers=headers)
        response = self.connection.getresponse()
        return response.status, response.getheader("Content-Type", ""), json.loads(response.read())

    def test_health_and_page_are_credential_free(self):
        status, content_type, body = self.request("GET", "/health")
        self.assertEqual(200, status)
        self.assertEqual("showcase_mvp", body["profile"])
        self.assertIn("application/json", content_type)
        self.connection.request("GET", "/")
        page = self.connection.getresponse().read().decode("utf-8")
        self.assertIn("live / replay / experimental / unavailable", page)

    def test_create_snapshot_events_and_evidence_share_run_contract(self):
        status, _, created = self.request("POST", "/api/runs", {"problem": "计算 1+1"})
        self.assertEqual(201, status)
        run_id = created["run_id"]
        self.assertEqual("COMPLETED", created["status"])
        status, _, events = self.request("GET", f"/api/runs/{run_id}/events")
        self.assertEqual(200, status)
        self.assertGreaterEqual(len(events["events"]), 3)
        status, _, evidence = self.request("GET", f"/api/runs/{run_id}/evidence")
        self.assertEqual(200, status)
        self.assertEqual(run_id, evidence["run"]["run_id"])
        self.assertIn(evidence["verification"]["status"], {"pass", "unknown", "conflict"})

    def test_invalid_request_is_rejected_before_agent(self):
        status, _, body = self.request("POST", "/api/runs", {"problem": " "})
        self.assertEqual(400, status)
        self.assertEqual("problem_must_be_non_empty", body["error"])


class ShowcaseResumeTest(unittest.TestCase):
    def test_resume_transition_preserves_failure_event(self):
        service = RunService(agent=FailingAgent())
        snapshot = service.create_run({"problem": "求极限"})
        run_id = snapshot["run_id"]
        original_events = service.get_events(run_id)
        resumed = service.transition(run_id, status="RESUMED", stage="solving")
        self.assertEqual("RESUMED", resumed["status"])
        self.assertEqual(original_events, service.get_events(run_id))
        service.close()


if __name__ == "__main__":
    unittest.main()

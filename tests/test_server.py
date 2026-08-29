import json
import threading
import urllib.request

from agent_harness.server import create_dashboard_server
from agent_harness.store import RunStore


def _request(url, token, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload else None
    request = urllib.request.Request(url, data=data, method=method, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=3) as response:
        return json.loads(response.read()) if response.headers.get_content_type() == "application/json" else response.read().decode()


def test_dashboard_api_and_review_decision(tmp_path):
    database = tmp_path / "runs.db"
    store = RunStore(database)
    store.ingest_report({
        "suite_name": "web suite", "finished_at": "2026-01-01T00:00:00+00:00", "summary": {"passed": False},
        "results": [{"case_id": "x", "passed": False, "needs_review": True, "model": "m", "trace": [], "metrics": {}, "capsule": {}}],
    })
    token = "test-token"
    server = create_dashboard_server(str(database), port=0, auth_token=token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert "Agent Harness Console" in urllib.request.urlopen(base, timeout=3).read().decode()
        assert _request(base + "/api/health", token)["ok"]
        assert len(_request(base + "/api/runs", token)) == 1
        review = _request(base + "/api/reviews?status=pending", token)[0]
        decided = _request(base + f"/api/reviews/{review['id']}", token, "POST", {"decision": "pass", "version": review["version"], "reviewer": "alex"})
        assert decided["decision"] == "pass"
    finally:
        server.shutdown()
        server.server_close()

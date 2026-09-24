from unittest.mock import patch, MagicMock

import jira_client


def _report():
    return {
        "experiment": "kill-payment-pod",
        "kind": "PodChaos",
        "service": "payment-service",
        "hypothesis": "test hypothesis",
        "remedy": "scale up replicas",
        "prometheus_evidence": "some_query",
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:01:00Z",
        "verdict": {
            "passed": False,
            "violations": ["P99 too high"],
            "max_error_rate": 0.1,
            "max_p99_latency_seconds": 3.0,
            "circuit_breaker_opened": False,
        },
    }


def test_find_open_blocker_none():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"issues": []}
    with patch.object(jira_client.requests, "get", return_value=resp):
        assert jira_client.find_open_blocker() is None


def test_find_open_blocker_returns_key():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"issues": [{"key": "DD-42"}]}
    with patch.object(jira_client.requests, "get", return_value=resp):
        assert jira_client.find_open_blocker() == "DD-42"


def test_find_open_issue_for_experiment_jql():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"issues": [{"key": "DD-99"}]}
    with patch.object(jira_client.requests, "get", return_value=resp) as g:
        key = jira_client.find_open_issue_for_experiment("kill-payment-pod")
    assert key == "DD-99"
    jql = g.call_args.kwargs.get("params", {}).get("jql", "")
    assert "kill-payment-pod" in jql
    assert "chaosdrill-blocker" in jql


def test_create_incident_ticket_payload_and_labels():
    resp = MagicMock()
    resp.status_code = 201
    resp.json.return_value = {"key": "DD-100"}
    with patch.object(jira_client.requests, "post", return_value=resp) as p:
        key = jira_client.create_incident_ticket(_report())
    assert key == "DD-100"
    payload = p.call_args.kwargs["json"]
    labels = payload["fields"]["labels"]
    assert "chaosdrill-blocker" in labels
    assert "kill-payment-pod" in labels
    assert payload["fields"]["project"]["key"] == "DD"


def test_create_incident_ticket_failure_returns_none():
    resp = MagicMock()
    resp.status_code = 400
    resp.text = "bad request"
    with patch.object(jira_client.requests, "post", return_value=resp):
        assert jira_client.create_incident_ticket(_report()) is None


def test_transition_ticket_posts_correct_id():
    trans = MagicMock()
    trans.status_code = 200
    trans.json.return_value = {"transitions": [{"id": "31", "name": "Done"}]}
    post = MagicMock()
    post.status_code = 204
    with patch.object(jira_client.requests, "get", return_value=trans), \
         patch.object(jira_client.requests, "post", return_value=post) as p:
        assert jira_client.transition_ticket("DD-1", "Done") is True
    assert p.call_args.kwargs["json"]["transition"]["id"] == "31"


def test_transition_ticket_missing_transition_returns_false():
    trans = MagicMock()
    trans.status_code = 200
    trans.json.return_value = {"transitions": [{"id": "11", "name": "In Progress"}]}
    with patch.object(jira_client.requests, "get", return_value=trans):
        assert jira_client.transition_ticket("DD-1", "Done") is False


# ---------- attach_file ----------

def test_attach_file_returns_true_on_success(tmp_path):
    p = tmp_path / "report.json"
    p.write_text('{"ok": true}')
    resp = MagicMock()
    resp.status_code = 200
    with patch.object(jira_client.requests, "post", return_value=resp):
        assert jira_client.attach_file("DD-1", str(p)) is True


def test_attach_file_returns_false_on_http_error(tmp_path):
    p = tmp_path / "report.json"
    p.write_text("{}")
    resp = MagicMock()
    resp.status_code = 500
    resp.text = "server error"
    with patch.object(jira_client.requests, "post", return_value=resp):
        assert jira_client.attach_file("DD-1", str(p)) is False


def test_attach_file_returns_false_on_missing_file():
    assert jira_client.attach_file("DD-1", "/tmp/does-not-exist-xyz.json") is False


# ---------- add_comment ----------

def test_add_comment_posts_payload():
    resp = MagicMock()
    resp.status_code = 201
    with patch.object(jira_client.requests, "post", return_value=resp) as p:
        assert jira_client.add_comment("DD-1", "hello world") is True
    body = p.call_args.kwargs["json"]["body"]
    # Confirm doc structure with our text present
    assert body["type"] == "doc"
    assert "hello world" in str(body)


# ---------- resolve_ticket ----------

def test_resolve_ticket_succeeds_on_first_transition():
    trans = MagicMock()
    trans.status_code = 200
    trans.json.return_value = {"transitions": [{"id": "31", "name": "Done"}]}
    post = MagicMock()
    post.status_code = 204

    with patch.object(jira_client.requests, "get", return_value=trans), \
         patch.object(jira_client.requests, "post", return_value=post):
        assert jira_client.resolve_ticket("DD-1") is True


def test_resolve_ticket_returns_false_when_no_known_transition():
    trans = MagicMock()
    trans.status_code = 200
    trans.json.return_value = {"transitions": [{"id": "11", "name": "Weird"}]}

    with patch.object(jira_client.requests, "get", return_value=trans):
        assert jira_client.resolve_ticket("DD-1") is False

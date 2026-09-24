import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import chaosdrill


# ------- helper to build a minimal set of readings -------

def _fake_readings(p99=0.5, err=0.0, breaker=0.0, n=3):
    return [
        {"timestamp": f"2026-01-01T00:00:0{i}Z",
         "error_rate": err,
         "p99_latency_seconds": p99,
         "circuit_breaker_state": breaker}
        for i in range(n)
    ]


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    """Redirect the state file to a tmp path per test."""
    f = tmp_path / "state.json"
    monkeypatch.setattr(chaosdrill, "STATE_FILE", f)
    return f


# ---------------- FAIL path ----------------

@patch("chaosdrill.time.sleep", return_value=None)
@patch("chaosdrill.subprocess.run")
@patch("chaosdrill.generate_traffic", side_effect=lambda ev: None)
@patch("chaosdrill.PrometheusConnect")
@patch("chaosdrill.poll_metrics")
@patch("chaosdrill.jira")
def test_run_experiment_fail_creates_ticket_and_blocks(
    mock_jira, mock_poll, mock_prom, mock_traffic, mock_sub, mock_sleep,
    isolated_state, tmp_path, monkeypatch, capsys,
):
    # Stay in tmp dir so the report file is written there
    monkeypatch.chdir(tmp_path)

    # Pod-kill experiment: threshold err 5%, p99 2s
    mock_poll.return_value = _fake_readings(p99=10.0)  # forces p99 violation

    mock_jira.find_open_blocker.return_value = None
    mock_jira.find_open_issue_for_experiment.return_value = None
    mock_jira.create_incident_ticket.return_value = "DD-TEST-1"
    mock_jira.attach_file.return_value = True

    mock_sub.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

    with pytest.raises(SystemExit) as e:
        chaosdrill.run_experiment("kill-payment-pod")
    assert e.value.code == 1

    # Ticket created
    assert mock_jira.create_incident_ticket.called
    # Report attached
    assert mock_jira.attach_file.called
    # State file now holds the open ticket
    state = json.loads(isolated_state.read_text())
    assert state["open_ticket"] == "DD-TEST-1"
    assert state["open_experiment"] == "kill-payment-pod"


@patch("chaosdrill.time.sleep", return_value=None)
@patch("chaosdrill.subprocess.run")
@patch("chaosdrill.generate_traffic", side_effect=lambda ev: None)
@patch("chaosdrill.PrometheusConnect")
@patch("chaosdrill.poll_metrics")
@patch("chaosdrill.jira")
def test_run_experiment_fail_reuses_existing_ticket(
    mock_jira, mock_poll, mock_prom, mock_traffic, mock_sub, mock_sleep,
    isolated_state, tmp_path, monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    # Pretend an open ticket already exists for this experiment
    isolated_state.write_text(json.dumps({
        "open_ticket": "DD-EXISTING",
        "open_experiment": "kill-payment-pod",
    }))

    mock_poll.return_value = _fake_readings(p99=10.0)
    mock_jira.find_open_blocker.return_value = "DD-EXISTING"
    mock_jira.find_open_issue_for_experiment.return_value = "DD-EXISTING"
    mock_jira.add_comment.return_value = True
    mock_jira.attach_file.return_value = True

    mock_sub.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

    with pytest.raises(SystemExit) as e:
        chaosdrill.run_experiment("kill-payment-pod")
    assert e.value.code == 1

    # Did NOT create a new ticket
    assert not mock_jira.create_incident_ticket.called
    # Did comment on the existing one
    assert mock_jira.add_comment.called


# ---------------- PASS path ----------------

@patch("chaosdrill.time.sleep", return_value=None)
@patch("chaosdrill.subprocess.run")
@patch("chaosdrill.generate_traffic", side_effect=lambda ev: None)
@patch("chaosdrill.PrometheusConnect")
@patch("chaosdrill.poll_metrics")
@patch("chaosdrill.jira")
def test_run_experiment_pass_no_open_ticket(
    mock_jira, mock_poll, mock_prom, mock_traffic, mock_sub, mock_sleep,
    isolated_state, tmp_path, monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    mock_poll.return_value = _fake_readings(p99=0.5)

    mock_jira.find_open_blocker.return_value = None
    mock_jira.find_open_issue_for_experiment.return_value = None

    mock_sub.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

    report = chaosdrill.run_experiment("kill-payment-pod")
    assert report["verdict"]["passed"] is True
    # Nothing to resolve
    assert not mock_jira.add_comment.called
    # State unchanged / clean
    if isolated_state.exists():
        st = json.loads(isolated_state.read_text())
        assert st.get("open_ticket") is None


@patch("chaosdrill.time.sleep", return_value=None)
@patch("chaosdrill.subprocess.run")
@patch("chaosdrill.generate_traffic", side_effect=lambda ev: None)
@patch("chaosdrill.PrometheusConnect")
@patch("chaosdrill.poll_metrics")
@patch("chaosdrill.jira")
def test_run_experiment_pass_resolves_open_ticket(
    mock_jira, mock_poll, mock_prom, mock_traffic, mock_sub, mock_sleep,
    isolated_state, tmp_path, monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    mock_poll.return_value = _fake_readings(p99=0.5)

    isolated_state.write_text(json.dumps({
        "open_ticket": "DD-OLD",
        "open_experiment": "kill-payment-pod",
    }))

    mock_jira.find_open_blocker.return_value = "DD-OLD"
    mock_jira.find_open_issue_for_experiment.return_value = "DD-OLD"
    mock_jira.add_comment.return_value = True
    mock_jira.attach_file.return_value = True
    mock_jira.resolve_ticket.return_value = True

    mock_sub.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

    report = chaosdrill.run_experiment("kill-payment-pod")
    assert report["verdict"]["passed"] is True
    assert mock_jira.add_comment.called
    assert mock_jira.attach_file.called
    assert mock_jira.resolve_ticket.called
    # State cleared
    st = json.loads(isolated_state.read_text())
    assert st["open_ticket"] is None
    assert st["open_experiment"] is None


@patch("chaosdrill.time.sleep", return_value=None)
@patch("chaosdrill.subprocess.run")
@patch("chaosdrill.generate_traffic", side_effect=lambda ev: None)
@patch("chaosdrill.PrometheusConnect")
@patch("chaosdrill.poll_metrics")
@patch("chaosdrill.jira")
def test_run_experiment_pass_resolve_fails(
    mock_jira, mock_poll, mock_prom, mock_traffic, mock_sub, mock_sleep,
    isolated_state, tmp_path, monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    mock_poll.return_value = _fake_readings(p99=0.5)

    isolated_state.write_text(json.dumps({
        "open_ticket": "DD-OLD",
        "open_experiment": "kill-payment-pod",
    }))

    mock_jira.find_open_blocker.return_value = "DD-OLD"
    mock_jira.find_open_issue_for_experiment.return_value = "DD-OLD"
    mock_jira.add_comment.return_value = True
    mock_jira.attach_file.return_value = True
    mock_jira.resolve_ticket.return_value = False  # transition unavailable

    mock_sub.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

    chaosdrill.run_experiment("kill-payment-pod")
    # State not cleared because resolution failed
    st = json.loads(isolated_state.read_text())
    assert st["open_ticket"] == "DD-OLD"


# ---------------- force flag ----------------

@patch("chaosdrill.time.sleep", return_value=None)
@patch("chaosdrill.subprocess.run")
@patch("chaosdrill.generate_traffic", side_effect=lambda ev: None)
@patch("chaosdrill.PrometheusConnect")
@patch("chaosdrill.poll_metrics")
@patch("chaosdrill.jira")
def test_run_experiment_force_bypasses_blocker(
    mock_jira, mock_poll, mock_prom, mock_traffic, mock_sub, mock_sleep,
    isolated_state, tmp_path, monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    mock_poll.return_value = _fake_readings(p99=0.5)

    # An open blocker exists, but force=True should ignore it
    isolated_state.write_text(json.dumps({
        "open_ticket": "DD-BLOCK",
        "open_experiment": "some-other-exp",
    }))
    mock_jira.find_open_blocker.return_value = "DD-BLOCK"
    mock_jira.find_open_issue_for_experiment.return_value = None

    mock_sub.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

    report = chaosdrill.run_experiment("kill-payment-pod", force=True)
    assert report["verdict"]["passed"] is True

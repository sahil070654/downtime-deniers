import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import chaosdrill


# ---------- state file handling ----------

def test_load_state_returns_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(chaosdrill, "STATE_FILE", tmp_path / "nope.json")
    state = chaosdrill.load_state()
    assert state == {"open_ticket": None, "open_experiment": None}


def test_load_state_reads_existing(tmp_path, monkeypatch):
    f = tmp_path / "state.json"
    f.write_text(json.dumps({"open_ticket": "DD-9", "open_experiment": "x"}))
    monkeypatch.setattr(chaosdrill, "STATE_FILE", f)
    assert chaosdrill.load_state()["open_ticket"] == "DD-9"


def test_load_state_returns_defaults_on_corrupt(tmp_path, monkeypatch):
    f = tmp_path / "state.json"
    f.write_text("not json{{")
    monkeypatch.setattr(chaosdrill, "STATE_FILE", f)
    assert chaosdrill.load_state() == {"open_ticket": None, "open_experiment": None}


def test_save_state_writes_file(tmp_path, monkeypatch):
    f = tmp_path / "state.json"
    monkeypatch.setattr(chaosdrill, "STATE_FILE", f)
    chaosdrill.save_state({"open_ticket": "DD-1", "open_experiment": "e"})
    assert json.loads(f.read_text())["open_ticket"] == "DD-1"


# ---------- resolve_chaos_file ----------

def test_resolve_chaos_file_finds_in_chaos_dir():
    p = chaosdrill.resolve_chaos_file("kill-payment-pod.yaml")
    assert p.endswith("kill-payment-pod.yaml")
    assert Path(p).exists()


def test_resolve_chaos_file_raises_when_missing():
    with pytest.raises(FileNotFoundError):
        chaosdrill.resolve_chaos_file("does-not-exist.yaml")


# ---------- query_metric ----------

def test_query_metric_returns_value():
    prom = MagicMock()
    prom.custom_query.return_value = [{"value": [1700000000, "1.5"]}]
    assert chaosdrill.query_metric(prom, "up") == 1.5


def test_query_metric_returns_zero_on_empty():
    prom = MagicMock()
    prom.custom_query.return_value = []
    assert chaosdrill.query_metric(prom, "up") == 0.0


def test_query_metric_returns_zero_on_exception():
    prom = MagicMock()
    prom.custom_query.side_effect = RuntimeError("boom")
    assert chaosdrill.query_metric(prom, "up") == 0.0


def test_query_metric_handles_nan():
    prom = MagicMock()
    prom.custom_query.return_value = [{"value": [1700000000, "NaN"]}]
    assert chaosdrill.query_metric(prom, "up") == 0.0


# ---------- apply_experiment ----------

@patch("chaosdrill.time.sleep", return_value=None)
@patch("chaosdrill.subprocess.run")
def test_apply_experiment_runs_kubectl(mock_run, mock_sleep):
    ok = MagicMock()
    ok.returncode = 0
    ok.stdout = "created"
    mock_run.return_value = ok

    chaosdrill.apply_experiment("kill-payment-pod.yaml")

    # One delete + one apply = 2 calls
    assert mock_run.call_count == 2
    apply_call = mock_run.call_args_list[1]
    assert apply_call.args[0][:3] == ["kubectl", "apply", "-f"]


@patch("chaosdrill.time.sleep", return_value=None)
@patch("chaosdrill.subprocess.run")
def test_apply_experiment_raises_on_kubectl_failure(mock_run, mock_sleep):
    bad = MagicMock()
    bad.returncode = 1
    bad.stderr = "nope"
    mock_run.return_value = bad

    with pytest.raises(RuntimeError):
        chaosdrill.apply_experiment("kill-payment-pod.yaml")


# ---------- poll_metrics ----------

@patch("chaosdrill.time.sleep", return_value=None)
@patch("chaosdrill.query_metric", return_value=0.5)
def test_poll_metrics_collects_readings(mock_qm, mock_sleep):
    prom = MagicMock()
    readings = chaosdrill.poll_metrics(prom, duration_seconds=10, interval_seconds=5)
    assert len(readings) == 2
    assert all(r["error_rate"] == 0.5 for r in readings)


# ---------- run_experiment gating ----------

def test_run_experiment_unknown_name_raises():
    with pytest.raises(ValueError):
        chaosdrill.run_experiment("not-a-real-experiment")


def test_run_experiment_blocked_by_open_ticket(monkeypatch, tmp_path, capsys):
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({
        "open_ticket": "DD-99",
        "open_experiment": "some-other-experiment",
    }))
    monkeypatch.setattr(chaosdrill, "STATE_FILE", state_file)
    monkeypatch.setattr(chaosdrill.jira, "find_open_blocker", lambda: "DD-99")
    monkeypatch.setattr(
        chaosdrill.jira, "find_open_issue_for_experiment",
        lambda name: "DD-99" if name == "some-other-experiment" else None,
    )

    with pytest.raises(SystemExit) as e:
        chaosdrill.run_experiment("kill-payment-pod")
    assert e.value.code == 2

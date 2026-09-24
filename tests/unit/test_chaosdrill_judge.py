from chaosdrill import judge


def _r(error_rate=0.0, p99=0.1, breaker=0.0):
    return {
        "error_rate": error_rate,
        "p99_latency_seconds": p99,
        "circuit_breaker_state": breaker,
    }


def test_pass_when_within_thresholds():
    readings = [_r(0.0, 0.2, 0.0), _r(0.0, 0.5, 0.0)]
    thresholds = {"error_rate_max": 0.05, "p99_latency_max_seconds": 2.0,
                  "circuit_breaker_must_open": False}
    v = judge(readings, thresholds)
    assert v["passed"] is True
    assert v["violations"] == []


def test_fail_on_error_rate():
    readings = [_r(0.10, 0.2, 0.0)]
    thresholds = {"error_rate_max": 0.05, "p99_latency_max_seconds": 2.0,
                  "circuit_breaker_must_open": False}
    v = judge(readings, thresholds)
    assert v["passed"] is False
    assert any("Error rate" in x for x in v["violations"])


def test_fail_on_p99():
    readings = [_r(0.0, 3.5, 0.0)]
    thresholds = {"error_rate_max": 0.05, "p99_latency_max_seconds": 2.0,
                  "circuit_breaker_must_open": False}
    v = judge(readings, thresholds)
    assert v["passed"] is False
    assert any("P99" in x for x in v["violations"])


def test_fail_when_breaker_did_not_open_but_should():
    readings = [_r(0.0, 0.1, 0.0)]
    thresholds = {"error_rate_max": 0.05, "p99_latency_max_seconds": 2.0,
                  "circuit_breaker_must_open": True}
    v = judge(readings, thresholds)
    assert v["passed"] is False
    assert any("Circuit breaker" in x for x in v["violations"])


def test_breaker_opened_counts_as_pass_when_required():
    readings = [_r(0.0, 0.1, 0.0), _r(0.0, 0.1, 1.0)]
    thresholds = {"error_rate_max": 0.05, "p99_latency_max_seconds": 2.0,
                  "circuit_breaker_must_open": True}
    v = judge(readings, thresholds)
    assert v["passed"] is True


def test_multiple_violations_reported():
    readings = [_r(0.5, 10.0, 0.0)]
    thresholds = {"error_rate_max": 0.05, "p99_latency_max_seconds": 2.0,
                  "circuit_breaker_must_open": True}
    v = judge(readings, thresholds)
    assert len(v["violations"]) == 3

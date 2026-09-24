from hypotheses import HYPOTHESES

REQUIRED_KEYS = {"experiment_file", "experiment_kind",
                 "expected_behavior", "slo_thresholds"}
REQUIRED_SLO_KEYS = {"error_rate_max", "p99_latency_max_seconds",
                     "circuit_breaker_must_open"}


def test_at_least_four_experiments():
    assert len(HYPOTHESES) >= 4


def test_all_have_required_keys():
    for name, h in HYPOTHESES.items():
        missing = REQUIRED_KEYS - h.keys()
        assert not missing, f"{name} missing {missing}"


def test_all_slo_thresholds_complete():
    for name, h in HYPOTHESES.items():
        missing = REQUIRED_SLO_KEYS - h["slo_thresholds"].keys()
        assert not missing, f"{name} slo missing {missing}"


def test_expected_experiments_present():
    for expected in ("kill-payment-pod", "payment-latency",
                     "payment-severe-latency", "payment-cpu-stress"):
        assert expected in HYPOTHESES


def test_thresholds_are_positive():
    for name, h in HYPOTHESES.items():
        assert h["slo_thresholds"]["error_rate_max"] > 0
        assert h["slo_thresholds"]["p99_latency_max_seconds"] > 0

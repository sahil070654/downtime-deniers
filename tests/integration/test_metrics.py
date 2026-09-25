import pytest
import requests


@pytest.mark.integration
@pytest.mark.parametrize("service_key,expected_metric_prefix", [
    ("user",    "user_service_"),
    ("order",   "order_service_"),
    ("payment", "payment_service_"),
])
def test_metrics_endpoint_exposes_prometheus_format(urls, service_key, expected_metric_prefix):
    r = requests.get(urls[service_key] + "/metrics", timeout=5)
    assert r.status_code == 200
    # Prometheus text format includes TYPE comments
    assert "# TYPE" in r.text
    # Should have at least one metric from this service
    assert expected_metric_prefix in r.text


@pytest.mark.integration
def test_order_service_exposes_circuit_breaker_gauge(urls):
    r = requests.get(urls["order"] + "/metrics", timeout=5)
    assert "order_service_circuit_breaker_state" in r.text


@pytest.mark.integration
def test_payment_service_exposes_error_counter(urls):
    r = requests.get(urls["payment"] + "/metrics", timeout=5)
    assert "payment_service_errors_total" in r.text

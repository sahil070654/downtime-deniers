import pytest
import requests


@pytest.mark.integration
def test_user_service_health(urls):
    r = requests.get(urls["user"] + "/health", timeout=5)
    assert r.status_code == 200
    assert r.json()["status"] == "UP"


@pytest.mark.integration
def test_order_service_health(urls):
    r = requests.get(urls["order"] + "/health", timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "UP"
    # Circuit breaker state should be one of closed/open/half-open
    assert body["circuit_breaker_state"] in ("closed", "open", "half-open")


@pytest.mark.integration
def test_payment_service_health(urls):
    r = requests.get(urls["payment"] + "/health", timeout=5)
    assert r.status_code == 200
    assert r.json()["status"] == "UP"

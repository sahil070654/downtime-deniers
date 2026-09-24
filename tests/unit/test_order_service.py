from unittest.mock import patch, MagicMock

import pytest

from tests.helpers import load_service_module

order_app = load_service_module("order-service")


@pytest.fixture(autouse=True)
def reset_breaker():
    order_app.breaker.state = "closed"
    order_app.breaker.failure_count = 0
    order_app.breaker.opened_at = None
    yield
    order_app.breaker.state = "closed"
    order_app.breaker.failure_count = 0
    order_app.breaker.opened_at = None


def test_health_endpoint():
    client = order_app.app.test_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "UP"
    assert body["circuit_breaker_state"] == "closed"


def test_metrics_endpoint():
    client = order_app.app.test_client()
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert b"order_service_" in resp.data


@patch("time.sleep", return_value=None)
@patch("requests.post")
def test_call_payment_success(mock_post, mock_sleep):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"payment_id": "pay_123"}
    mock_post.return_value = mock_resp

    result, error = order_app.call_payment_service("o1", 100)
    assert error is None
    assert result == {"payment_id": "pay_123"}
    assert order_app.breaker.get_state() == "closed"


@patch("time.sleep", return_value=None)
@patch("requests.post")
def test_call_payment_retries_then_succeeds(mock_post, mock_sleep):
    fail = MagicMock()
    fail.status_code = 500
    fail.text = "boom"
    ok = MagicMock()
    ok.status_code = 200
    ok.json.return_value = {"payment_id": "pay_456"}
    mock_post.side_effect = [fail, ok]

    result, error = order_app.call_payment_service("o1", 100, max_retries=3)
    assert error is None
    assert result["payment_id"] == "pay_456"
    assert mock_post.call_count == 2


@patch("time.sleep", return_value=None)
@patch("requests.post")
def test_call_payment_all_retries_fail(mock_post, mock_sleep):
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "boom"
    mock_post.return_value = mock_resp

    result, error = order_app.call_payment_service("o1", 100, max_retries=3)
    assert result is None
    assert error is not None
    assert mock_post.call_count == 3
    assert order_app.breaker.failure_count == 1


@patch("requests.post")
def test_call_payment_blocked_when_open(mock_post):
    for _ in range(3):
        order_app.breaker.record_failure()
    result, error = order_app.call_payment_service("o1", 100)
    assert result is None
    assert error == "circuit_open"
    assert mock_post.call_count == 0

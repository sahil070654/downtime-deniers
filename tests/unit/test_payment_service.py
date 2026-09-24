from unittest.mock import patch, MagicMock

import pytest

from tests.helpers import load_service_module

payment_app = load_service_module("payment-service")


def test_health_endpoint():
    client = payment_app.app.test_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "UP"


def test_metrics_endpoint():
    client = payment_app.app.test_client()
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert b"payment_service_" in resp.data


@patch.object(payment_app, "SessionLocal")
def test_pay_success(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db

    def set_id(p):
        p.id = 101
    mock_db.add.side_effect = set_id

    client = payment_app.app.test_client()
    resp = client.post("/pay", json={"orderId": 5, "amount": 99.5})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["payment_id"] == 101
    assert body["status"] == "SUCCESS"
    mock_db.commit.assert_called_once()
    mock_db.close.assert_called_once()


@patch.object(payment_app, "SessionLocal")
def test_pay_missing_amount_returns_400(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db

    client = payment_app.app.test_client()
    resp = client.post("/pay", json={"orderId": 5})
    assert resp.status_code == 400
    assert "invalid amount" in resp.get_json()["error"]
    mock_db.commit.assert_not_called()


@patch.object(payment_app, "SessionLocal")
def test_pay_zero_amount_returns_400(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db

    client = payment_app.app.test_client()
    resp = client.post("/pay", json={"orderId": 5, "amount": 0})
    assert resp.status_code == 400


@patch.object(payment_app, "SessionLocal")
def test_pay_negative_amount_returns_400(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db

    client = payment_app.app.test_client()
    resp = client.post("/pay", json={"orderId": 5, "amount": -5})
    assert resp.status_code == 400


@patch.object(payment_app, "SessionLocal")
def test_pay_db_error_returns_500(mock_session_local):
    mock_db = MagicMock()
    mock_db.add.side_effect = RuntimeError("db down")
    mock_session_local.return_value = mock_db

    client = payment_app.app.test_client()
    resp = client.post("/pay", json={"orderId": 5, "amount": 10})
    assert resp.status_code == 500
    mock_db.rollback.assert_called_once()
    mock_db.close.assert_called_once()

from unittest.mock import patch, MagicMock
from datetime import datetime

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


def _make_order(id_=1, user_id=1, status="PENDING", payment_id=None):
    o = MagicMock()
    o.id = id_
    o.user_id = user_id
    o.item_name = "Widget"
    o.quantity = 2
    o.amount = 19.99
    o.status = status
    o.payment_id = payment_id
    return o


@patch("requests.post")
@patch.object(order_app, "SessionLocal")
def test_create_order_success(mock_session, mock_post):
    # DB mock
    db = MagicMock()
    mock_session.return_value = db

    def set_id(order):
        order.id = 55
    db.add.side_effect = set_id

    # Payment mock
    pay_resp = MagicMock()
    pay_resp.status_code = 200
    pay_resp.json.return_value = {"payment_id": 999}
    mock_post.return_value = pay_resp

    client = order_app.app.test_client()
    resp = client.post("/api/orders", json={
        "userId": 1, "itemName": "Widget", "quantity": 2, "amount": 19.99,
    })
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["status"] == "COMPLETED"
    assert body["paymentId"] == 999
    assert db.commit.call_count == 2
    assert db.close.called


@patch("requests.post")
@patch.object(order_app, "SessionLocal")
def test_create_order_payment_failure(mock_session, mock_post):
    db = MagicMock()
    mock_session.return_value = db

    def set_id(order):
        order.id = 56
    db.add.side_effect = set_id

    pay_resp = MagicMock()
    pay_resp.status_code = 500
    pay_resp.text = "boom"
    mock_post.return_value = pay_resp

    client = order_app.app.test_client()
    resp = client.post("/api/orders", json={
        "userId": 1, "itemName": "Widget", "quantity": 1, "amount": 9.99,
    })
    assert resp.status_code == 502
    body = resp.get_json()
    assert body["status"] == "FAILED"
    assert "error" in body


@patch.object(order_app, "SessionLocal")
def test_create_order_missing_field_returns_400(mock_session):
    db = MagicMock()
    mock_session.return_value = db

    client = order_app.app.test_client()
    resp = client.post("/api/orders", json={"userId": 1})  # missing fields
    assert resp.status_code == 400
    assert "error" in resp.get_json()
    db.rollback.assert_called_once()


@patch.object(order_app, "SessionLocal")
def test_list_orders_all(mock_session):
    db = MagicMock()
    mock_session.return_value = db

    db.query.return_value.all.return_value = [
        _make_order(1, 1, "COMPLETED", 999),
        _make_order(2, 2, "PENDING"),
    ]

    client = order_app.app.test_client()
    resp = client.get("/api/orders")
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body) == 2
    assert body[0]["status"] == "COMPLETED"


@patch.object(order_app, "SessionLocal")
def test_list_orders_filtered_by_user(mock_session):
    db = MagicMock()
    mock_session.return_value = db

    chain = db.query.return_value
    chain.filter_by.return_value.all.return_value = [_make_order(3, 7, "PENDING")]

    client = order_app.app.test_client()
    resp = client.get("/api/orders?userId=7")
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body) == 1
    chain.filter_by.assert_called_once_with(user_id="7")

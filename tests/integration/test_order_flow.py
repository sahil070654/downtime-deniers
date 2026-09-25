"""End-to-end integration test: register → login → place order → verify.

This is the closest thing to "does the whole system actually work".
"""
import pytest
import requests


@pytest.mark.integration
def test_full_user_lifecycle(urls, unique_user):
    # 1. Register
    r = requests.post(urls["user"] + "/register", json=unique_user, timeout=5)
    assert r.status_code == 201, r.text
    user_id = r.json()["user_id"]
    assert isinstance(user_id, int)

    # 2. Login
    r = requests.post(
        urls["user"] + "/login",
        json={"username": unique_user["username"], "password": unique_user["password"]},
        timeout=5,
    )
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == user_id


@pytest.mark.integration
def test_login_with_wrong_password_fails(urls, unique_user):
    requests.post(urls["user"] + "/register", json=unique_user, timeout=5)
    r = requests.post(
        urls["user"] + "/login",
        json={"username": unique_user["username"], "password": "wrong-password"},
        timeout=5,
    )
    assert r.status_code == 401


@pytest.mark.integration
def test_place_order_end_to_end(urls, unique_user):
    # Ensure user exists
    reg = requests.post(urls["user"] + "/register", json=unique_user, timeout=5)
    user_id = reg.json()["user_id"]

    # Place an order — this triggers Order → Payment → DB
    payload = {
        "userId": user_id,
        "itemName": "IntegrationTestItem",
        "quantity": 1,
        "amount": 12.34,
    }
    r = requests.post(urls["order"] + "/api/orders", json=payload, timeout=15)
    assert r.status_code == 201, f"Order failed: {r.status_code} {r.text}"
    body = r.json()
    assert body["status"] == "COMPLETED"
    assert "paymentId" in body


@pytest.mark.integration
def test_list_orders_filtered_by_user(urls, unique_user):
    reg = requests.post(urls["user"] + "/register", json=unique_user, timeout=5)
    user_id = reg.json()["user_id"]

    # Place 2 orders
    for _ in range(2):
        requests.post(
            urls["order"] + "/api/orders",
            json={"userId": user_id, "itemName": "X", "quantity": 1, "amount": 5.0},
            timeout=15,
        )

    # List them back
    r = requests.get(urls["order"] + "/api/orders", params={"userId": user_id}, timeout=5)
    assert r.status_code == 200
    orders = r.json()
    assert len(orders) >= 2
    assert all(o["status"] == "COMPLETED" for o in orders)


@pytest.mark.integration
def test_invalid_order_payload_returns_400(urls):
    # Missing required fields
    r = requests.post(urls["order"] + "/api/orders", json={"userId": 1}, timeout=5)
    assert r.status_code == 400


@pytest.mark.integration
def test_payment_rejects_invalid_amount(urls):
    r = requests.post(urls["payment"] + "/pay", json={"orderId": 1, "amount": -10}, timeout=5)
    assert r.status_code == 400

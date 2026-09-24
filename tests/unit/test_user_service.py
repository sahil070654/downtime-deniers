from unittest.mock import patch, MagicMock

import pytest

from tests.helpers import load_service_module

user_app = load_service_module("user-service")


def test_health_endpoint():
    client = user_app.app.test_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "UP"


def test_metrics_endpoint():
    client = user_app.app.test_client()
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert b"user_service_" in resp.data


@patch.object(user_app, "SessionLocal")
def test_register_success(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db

    # Fake the autoincrement id returned by the DB
    def set_id(user):
        user.id = 42
    mock_db.add.side_effect = set_id

    client = user_app.app.test_client()
    resp = client.post("/register", json={
        "username": "alice",
        "email": "alice@example.com",
        "password": "hunter2",
    })
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["message"] == "registered"
    assert body["user_id"] == 42
    mock_db.commit.assert_called_once()
    mock_db.close.assert_called_once()


@patch.object(user_app, "SessionLocal")
def test_register_failure_returns_400(mock_session_local):
    mock_db = MagicMock()
    mock_db.add.side_effect = RuntimeError("db blew up")
    mock_session_local.return_value = mock_db

    client = user_app.app.test_client()
    resp = client.post("/register", json={
        "username": "bob",
        "email": "bob@example.com",
        "password": "hunter2",
    })
    assert resp.status_code == 400
    mock_db.rollback.assert_called_once()
    mock_db.close.assert_called_once()


@patch.object(user_app, "SessionLocal")
def test_login_success(mock_session_local):
    from werkzeug.security import generate_password_hash

    mock_user = MagicMock()
    mock_user.id = 7
    mock_user.username = "alice"
    mock_user.password_hash = generate_password_hash("hunter2")

    mock_db = MagicMock()
    mock_db.query.return_value.filter_by.return_value.first.return_value = mock_user
    mock_session_local.return_value = mock_db

    client = user_app.app.test_client()
    resp = client.post("/login", json={"username": "alice", "password": "hunter2"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["message"] == "ok"
    assert body["user_id"] == 7
    assert body["username"] == "alice"


@patch.object(user_app, "SessionLocal")
def test_login_wrong_password_returns_401(mock_session_local):
    from werkzeug.security import generate_password_hash

    mock_user = MagicMock()
    mock_user.password_hash = generate_password_hash("correct")

    mock_db = MagicMock()
    mock_db.query.return_value.filter_by.return_value.first.return_value = mock_user
    mock_session_local.return_value = mock_db

    client = user_app.app.test_client()
    resp = client.post("/login", json={"username": "alice", "password": "wrong"})
    assert resp.status_code == 401


@patch.object(user_app, "SessionLocal")
def test_login_unknown_user_returns_401(mock_session_local):
    mock_db = MagicMock()
    mock_db.query.return_value.filter_by.return_value.first.return_value = None
    mock_session_local.return_value = mock_db

    client = user_app.app.test_client()
    resp = client.post("/login", json={"username": "nobody", "password": "x"})
    assert resp.status_code == 401

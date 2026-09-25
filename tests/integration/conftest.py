"""Fixtures for integration tests.

These tests hit LIVE services — no mocks.

Configure target URLs with env vars (defaults to local docker-compose):

    USER_SERVICE_URL      default http://localhost:5001
    ORDER_SERVICE_URL     default http://localhost:8082
    PAYMENT_SERVICE_URL   default http://localhost:8083
    FRONTEND_URL          default http://localhost:8080

To target the live EC2 deployment:

    export USER_SERVICE_URL=http://13.235.4.151:30001
    export ORDER_SERVICE_URL=http://13.235.4.151:30002
    export PAYMENT_SERVICE_URL=http://13.235.4.151:30003
"""
import os
import time
import uuid

import pytest
import requests


def _env(key, default):
    return os.environ.get(key, default).rstrip("/")


USER_URL    = _env("USER_SERVICE_URL",    "http://localhost:5001")
ORDER_URL   = _env("ORDER_SERVICE_URL",   "http://localhost:8082")
PAYMENT_URL = _env("PAYMENT_SERVICE_URL", "http://localhost:8083")
FRONTEND_URL = _env("FRONTEND_URL",       "http://localhost:8080")


def _wait_healthy(url, path="/health", timeout=5):
    try:
        r = requests.get(url + path, timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
def services_up():
    """Fail fast with a clear message if the target services aren't reachable."""
    problems = []
    for name, url in [("user", USER_URL), ("order", ORDER_URL), ("payment", PAYMENT_URL)]:
        if not _wait_healthy(url):
            problems.append(f"{name}-service at {url}")
    if problems:
        pytest.skip(
            "Integration target(s) not reachable: " + ", ".join(problems) +
            ". Start docker-compose or set *_SERVICE_URL env vars."
        )


@pytest.fixture
def urls():
    return {
        "user": USER_URL,
        "order": ORDER_URL,
        "payment": PAYMENT_URL,
        "frontend": FRONTEND_URL,
    }


@pytest.fixture
def unique_user():
    """A fresh username each test — so re-runs don't collide."""
    suffix = uuid.uuid4().hex[:8]
    return {
        "username": f"itest_{suffix}",
        "email":    f"itest_{suffix}@example.test",
        "password": "itest-password-123",
    }

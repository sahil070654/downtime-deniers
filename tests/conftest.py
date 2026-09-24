"""Shared pytest setup. Env vars set BEFORE any service module import."""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PATHS = [
    REPO_ROOT,
    REPO_ROOT / "chaosdrill",
    REPO_ROOT / "services" / "user-service",
    REPO_ROOT / "services" / "order-service",
    REPO_ROOT / "services" / "payment-service",
]
for p in PATHS:
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

# Fake Jira creds — mocked in unit tests
os.environ.setdefault("JIRA_URL", "https://example.atlassian.net")
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "test-token-not-real")
os.environ.setdefault("JIRA_PROJECT_KEY", "DD")
os.environ.setdefault("CHAOSDRILL_STATE_FILE", "/tmp/dd_chaosdrill_test_state.json")
os.environ.setdefault("PAYMENT_SERVICE_URL", "http://payment-test:9999")

# DB — point at a real MySQL if needed (db.py actually connects on import)
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_USER", "root")
os.environ.setdefault("DB_PASS", "test")
os.environ.setdefault("DB_NAME", "dd_test")

# Flag our code can check to skip DB bootstrap in tests
os.environ.setdefault("UNIT_TEST_MODE", "1")

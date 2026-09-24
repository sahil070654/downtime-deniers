"""Helpers for loading same-named modules from different services."""
import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_SERVICE_MODULES = ("app", "db", "circuit_breaker")


def load_service_module(service, module="app"):
    """
    Load a module from a specific service directory, avoiding
    name collisions across services (all have app.py).
    """
    svc_dir = str(REPO_ROOT / "services" / service)

    # Remove any other service dirs already on sys.path
    for p in list(sys.path):
        if p.endswith("-service") and "services" in p and p != svc_dir:
            sys.path.remove(p)

    # Drop cached modules from any previously loaded service
    for m in _SERVICE_MODULES:
        sys.modules.pop(m, None)

    if svc_dir in sys.path:
        sys.path.remove(svc_dir)
    sys.path.insert(0, svc_dir)

    return importlib.import_module(module)

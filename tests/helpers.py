"""Helpers for loading same-named modules from different services.

Caches loaded modules per (service, module) so prometheus_client's global
metric registry isn't asked to re-register the same Counter/Histogram.
"""
import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_SERVICE_MODULES = ("app", "db", "circuit_breaker")

# module cache: (service, module_name) -> module object
_CACHE = {}


def load_service_module(service, module="app"):
    key = (service, module)
    if key in _CACHE:
        return _CACHE[key]

    svc_dir = str(REPO_ROOT / "services" / service)

    # Remove OTHER service dirs from sys.path
    for p in list(sys.path):
        if p.endswith("-service") and "services" in p and p != svc_dir:
            sys.path.remove(p)

    # Drop cached modules so this service's app/db are the ones imported
    for m in _SERVICE_MODULES:
        sys.modules.pop(m, None)

    if svc_dir in sys.path:
        sys.path.remove(svc_dir)
    sys.path.insert(0, svc_dir)

    mod = importlib.import_module(module)
    _CACHE[key] = mod
    return mod

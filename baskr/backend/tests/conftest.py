"""Pytest fixtures + path setup for the Baskr backend tests.

Ensures ``app`` (and, via ``app.__init__``'s shim, the repo-root ``system_pieces``
package) is importable no matter where pytest is invoked from.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# .../baskr/backend/tests/conftest.py -> backend dir is two parents up.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


@pytest.fixture()
def client() -> TestClient:
    from app.main import app

    return TestClient(app)

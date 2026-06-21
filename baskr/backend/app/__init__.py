"""Baskr backend application package.

Scaffold only — see module docstrings for the contract each file fulfills.

Path shim: the shared ``system_pieces`` package (which provides the multi-source
``DataPipeline``) lives at the repo root, not inside this backend. Put the repo
root on ``sys.path`` so ``from system_pieces.data_pipeline import DataPipeline``
resolves regardless of how the app is launched. Imports of ``DataPipeline`` stay
local to the functions that use it (engine.py / ingest.py) to keep app boot light.
"""

from __future__ import annotations

import sys
from pathlib import Path

# .../baskr/backend/app/__init__.py -> repo root is four parents up.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

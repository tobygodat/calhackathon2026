"""Context Initialization Engine.

Turns a user's research PDFs (prior work, planning/scaffolding, or in-progress
drafts) into a vector-searchable **user context** made of three item kinds:

- **findings**    — conclusions the paper makes as its point.
- **questions**   — unknowns, open problems, or planned future experiments.
- **assumptions** — facts the paper takes as true but does not itself verify.

Incoming data is later vector-searched against these items. See ``engine.py``
for the top-level orchestration and ``api.py`` / ``cli.py`` for entry points.
"""

from .models import ContextItem, ItemKind, ExtractionResult

__all__ = ["ContextItem", "ItemKind", "ExtractionResult"]

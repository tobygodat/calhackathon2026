"""Command-line interface for the Context Engine.

Examples:
    python -m context_engine.cli ingest paper1.pdf paper2.pdf
    python -m context_engine.cli search "does gut microbiota affect mood?"
    python -m context_engine.cli context --kind question
    python -m context_engine.cli clear
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import SETTINGS
from .engine import ContextEngine
from .extractor import using_real_model
from .models import ItemKind


def _engine() -> ContextEngine:
    return ContextEngine(SETTINGS)


def _cmd_ingest(args) -> int:
    eng = _engine()
    mode = "claude" if using_real_model(SETTINGS) else "heuristic"
    emb = "openai" if SETTINGS.openai_api_key else "keyless"
    print(f"[extraction={mode}  embeddings={emb}  store={type(eng.store).__name__}]\n")
    for path in args.paths:
        p = Path(path)
        if not p.exists():
            print(f"  ! {path}: not found", file=sys.stderr)
            continue
        result = eng.ingest_pdf(p.read_bytes(), title=p.name)
        c = result.counts()
        print(f"  {p.name}  ({result.num_chunks} chunks)")
        print(f"    findings={c['finding']}  questions={c['question']}  "
              f"assumptions={c['assumption']}")
    return 0


def _cmd_search(args) -> int:
    eng = _engine()
    kind = ItemKind(args.kind) if args.kind else None
    hits = eng.search(args.query, top_k=args.top_k, kind=kind)
    if not hits:
        print("(no matches — ingest some PDFs first)")
        return 0
    for h in hits:
        print(f"  [{h.score:.3f}] ({h.item.kind.value}) {h.item.text}")
        if h.item.source_title:
            print(f"          — {h.item.source_title}")
    return 0


def _cmd_accept(args) -> int:
    eng = _engine()
    kind = ItemKind(args.kind) if args.kind else ItemKind.FINDING
    p = eng.accept(args.text, kind=kind, auto_apply=not args.preview)
    verb = "WOULD" if args.preview else "DID"
    print(f"  stance={p.stance}  severity={p.severity:.2f}  "
          f"relatedness={p.relatedness:.2f}  ->  mode={p.mode}")
    if p.target:
        print(f"  target belief: {p.target.text}")
    print(f"  rationale: {p.rationale}")
    print(f"  revised text: {p.revised_text}")
    print(f"  {verb} apply: {p.changes or '(preview only)'}")
    return 0


def _cmd_context(args) -> int:
    eng = _engine()
    kind = ItemKind(args.kind) if args.kind else None
    items = eng.context(kind=kind)
    for it in items:
        print(f"  ({it.kind.value}) {it.text}")
    print(f"\n  total: {len(items)} items")
    return 0


def _cmd_clear(args) -> int:
    _engine().clear()
    print("cleared.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="context_engine", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest", help="ingest one or more PDFs")
    p_ing.add_argument("paths", nargs="+")
    p_ing.set_defaults(func=_cmd_ingest)

    p_search = sub.add_parser("search", help="vector-search the user context")
    p_search.add_argument("query")
    p_search.add_argument("--top-k", type=int, default=None)
    p_search.add_argument("--kind", choices=[k.value for k in ItemKind], default=None)
    p_search.set_defaults(func=_cmd_search)

    p_acc = sub.add_parser("accept", help="accept a claim; revise context in proportion")
    p_acc.add_argument("text")
    p_acc.add_argument("--kind", choices=[k.value for k in ItemKind], default=None)
    p_acc.add_argument("--preview", action="store_true", help="assess without mutating")
    p_acc.set_defaults(func=_cmd_accept)

    p_ctx = sub.add_parser("context", help="list stored context items")
    p_ctx.add_argument("--kind", choices=[k.value for k in ItemKind], default=None)
    p_ctx.set_defaults(func=_cmd_context)

    p_clear = sub.add_parser("clear", help="empty the store")
    p_clear.set_defaults(func=_cmd_clear)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

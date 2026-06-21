"""PDF text extraction and chunking.

Pulls plain text out of an uploaded PDF (via pypdf) and splits it into
overlapping character windows so long papers can be reasoned over chunk-by-chunk
without exceeding the extraction model's context window.
"""

from __future__ import annotations

import io
import re

from .config import SETTINGS, Settings

_WS_RE = re.compile(r"[ \t]+")
_NL_RE = re.compile(r"\n{3,}")


def extract_text(data: bytes) -> str:
    """Extract and lightly normalize the full text of a PDF given as bytes.

    Raises ``RuntimeError`` with a clear message if pypdf is missing or the file
    is unreadable, so callers can surface a useful error to the user.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "pypdf is required to read PDFs (pip install pypdf)."
        ) from exc

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 - any parse failure is user-facing
        raise RuntimeError(f"Could not read PDF: {exc}") from exc

    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - skip a single unreadable page
            continue
    text = "\n\n".join(pages)
    return _normalize(text)


def _normalize(text: str) -> str:
    """Collapse runaway whitespace while preserving paragraph breaks."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Join hyphenated line breaks ("micro-\nbiome" -> "microbiome").
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = _WS_RE.sub(" ", text)
    text = _NL_RE.sub("\n\n", text)
    return text.strip()


def chunk_text(text: str, settings: Settings = SETTINGS) -> list[str]:
    """Split text into overlapping windows of ``settings.chunk_chars`` characters.

    Splits on paragraph boundaries where possible to avoid cutting mid-sentence;
    the overlap keeps a claim that straddles a boundary visible in both chunks.
    """
    text = text.strip()
    if not text:
        return []
    size = max(settings.chunk_chars, 1000)
    overlap = min(settings.chunk_overlap, size // 2)
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + size
        if end >= len(text):
            chunks.append(text[start:].strip())
            break
        # Prefer to break at the last paragraph/sentence boundary in the window.
        window = text[start:end]
        split_at = max(window.rfind("\n\n"), window.rfind(". "))
        if split_at < size // 2:  # no good boundary -> hard cut
            split_at = size
        chunks.append(text[start : start + split_at].strip())
        start += max(split_at - overlap, 1)
    return [c for c in chunks if c]

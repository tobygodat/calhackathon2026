"""First-page paper thumbnails for GET /api/thumbnail.

Papers carry no stored image, so we render the first page of the paper's PDF
to a PNG on demand. The PDF URL is derived from the paper's ``source`` +
landing ``url`` (we never store it). Rendered PNGs are cached on disk keyed by
the PDF URL so each paper is rendered at most once.

Sources without a reliably-free PDF (PubMed, unknown) return ``None`` from
``pdf_url_for`` so the route can answer 404 and let the frontend fall back to
its placeholder skeleton.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import requests

# app/ -> backend/ -> baskr/ -> baskr/data/thumbnail_cache
_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "thumbnail_cache"

_HEADERS = {"User-Agent": "Baskr/0.1 (+https://github.com) thumbnail-fetcher"}
_DOWNLOAD_TIMEOUT = 8  # seconds
_MAX_PDF_BYTES = 25 * 1024 * 1024  # 25 MB cap so we never pull huge files
_ZOOM = 2.0  # ~matches the 160x200 card box


def pdf_url_for(source: str, url: str | None) -> str | None:
    """Derive a directly-downloadable PDF URL from a paper's landing page.

    Returns ``None`` when there is no reliably-free PDF (PubMed / unknown /
    missing url), which the caller turns into a 404.
    """
    if not url:
        return None
    source = (source or "").lower()
    url = url.strip()

    if source == "arxiv":
        # https://arxiv.org/abs/2406.12345  ->  https://arxiv.org/pdf/2406.12345
        # tolerate http/https and trailing version suffixes (handled by arXiv).
        if "/abs/" in url:
            return url.replace("/abs/", "/pdf/", 1).replace("http://", "https://", 1)
        return None

    if source == "biorxiv":
        # https://www.biorxiv.org/content/<doi>  ->  <...>.full.pdf
        # the bare content path resolves to the latest version's full text.
        base = url.rstrip("/")
        if base.endswith(".full.pdf"):
            return base
        return f"{base}.full.pdf"

    # pubmed and anything unrecognized: no free PDF we can rely on.
    return None


def _cache_path(pdf_url: str) -> Path:
    digest = hashlib.sha1(pdf_url.encode("utf-8")).hexdigest()
    return _CACHE_DIR / f"{digest}.png"


def _download_pdf(pdf_url: str) -> bytes:
    resp = requests.get(
        pdf_url,
        headers=_HEADERS,
        timeout=_DOWNLOAD_TIMEOUT,
        stream=True,
        allow_redirects=True,
    )
    resp.raise_for_status()

    chunks: list[bytes] = []
    total = 0
    for chunk in resp.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if total > _MAX_PDF_BYTES:
            raise ValueError("PDF exceeds size cap")
        chunks.append(chunk)
    return b"".join(chunks)


def _render_first_page(pdf_bytes: bytes) -> bytes:
    import fitz  # PyMuPDF; imported lazily so the module loads without it.

    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        if doc.page_count == 0:
            raise ValueError("PDF has no pages")
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(_ZOOM, _ZOOM))
        return pix.tobytes("png")


def render_thumbnail(source: str, url: str | None) -> bytes | None:
    """Return PNG bytes of the paper's first page, or ``None`` if unavailable.

    Caches the rendered PNG on disk. Any failure (no PDF url, download error,
    render error) returns ``None`` so the route answers 404 rather than 500.
    """
    pdf_url = pdf_url_for(source, url)
    if not pdf_url:
        return None

    cache_path = _cache_path(pdf_url)
    if cache_path.exists():
        try:
            return cache_path.read_bytes()
        except OSError:
            pass  # fall through and re-render

    try:
        pdf_bytes = _download_pdf(pdf_url)
        png = _render_first_page(pdf_bytes)
    except Exception:
        return None

    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(png)
    except OSError:
        pass  # caching is best-effort

    return png

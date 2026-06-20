"""Pipeline configuration + API key loading.

Keys are optional. The pipeline runs against every source with no keys at all;
keys only raise rate limits (NCBI) or unlock full-text venues (Springer/Nature).

Load order for each key:
  1. real environment variable
  2. a `.env` file sitting next to this module (KEY=value lines)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_ENV_PATH = Path(__file__).resolve().parent / ".env"


def _load_dotenv() -> None:
    """Minimal .env loader (no third-party dependency)."""
    if not _ENV_PATH.exists():
        return
    for line in _ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        # real env always wins over .env
        os.environ.setdefault(key, value)


_load_dotenv()


def _get(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name)
    return val if val else default


@dataclass(frozen=True)
class Config:
    # Contact email — used by NCBI E-utilities and Crossref "polite pool".
    # Identifies your traffic so the services don't throttle you anonymously.
    contact_email: str = _get("PIPELINE_CONTACT_EMAIL", "drewrhawley@gmail.com")
    tool_name: str = _get("PIPELINE_TOOL_NAME", "baskr")

    # --- optional keys (None = run without, at lower limits) ---
    ncbi_api_key: str | None = _get("NCBI_API_KEY")
    springer_api_key: str | None = _get("SPRINGER_API_KEY")

    # --- defaults ---
    default_lookback_days: int = int(_get("PIPELINE_LOOKBACK_DAYS", "7"))
    default_max_per_source: int = int(_get("PIPELINE_MAX_PER_SOURCE", "50"))
    request_timeout: int = int(_get("PIPELINE_HTTP_TIMEOUT", "30"))

    @property
    def ncbi_rate_limit(self) -> float:
        """Requests/sec allowed by NCBI: 10 with a key, 3 without."""
        return 10.0 if self.ncbi_api_key else 3.0

    def status(self) -> dict[str, str]:
        """Human-readable readiness summary for the CLI banner."""
        def mark(v: object) -> str:
            return "configured" if v else "not set (using free/anonymous tier)"
        return {
            "contact_email": self.contact_email,
            "NCBI_API_KEY": mark(self.ncbi_api_key),
            "SPRINGER_API_KEY": mark(self.springer_api_key),
            "ncbi_rate_limit_rps": str(self.ncbi_rate_limit),
        }


CONFIG = Config()

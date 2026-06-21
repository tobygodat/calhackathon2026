"""Paper source adapters, keyed by name for the pipeline registry."""

# ============================================================================
# WARNING: NATURE SOURCE IS DISABLED — DO NOT RE-ENABLE WITHOUT EXPLICIT REQUEST
# The NatureSource import and registry entry below are commented out.
# Do not uncomment unless the user specifically asks to restore the Nature source.
# ============================================================================

from .base import PaperSource
from .pubmed import PubMedSource
from .arxiv import ArxivSource
from .biorxiv import BioRxivSource
# from .nature import NatureSource

SOURCE_REGISTRY: dict[str, type[PaperSource]] = {
    PubMedSource.name: PubMedSource,
    ArxivSource.name: ArxivSource,
    BioRxivSource.name: BioRxivSource,
    # NatureSource.name: NatureSource,
}

__all__ = [
    "PaperSource",
    "PubMedSource",
    "ArxivSource",
    "BioRxivSource",
    # "NatureSource",  # DISABLED — see warning above
    "SOURCE_REGISTRY",
]

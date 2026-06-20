"""Paper source adapters, keyed by name for the pipeline registry."""

from .base import PaperSource
from .pubmed import PubMedSource
from .arxiv import ArxivSource
from .biorxiv import BioRxivSource
from .nature import NatureSource

SOURCE_REGISTRY: dict[str, type[PaperSource]] = {
    PubMedSource.name: PubMedSource,
    ArxivSource.name: ArxivSource,
    BioRxivSource.name: BioRxivSource,
    NatureSource.name: NatureSource,
}

__all__ = [
    "PaperSource",
    "PubMedSource",
    "ArxivSource",
    "BioRxivSource",
    "NatureSource",
    "SOURCE_REGISTRY",
]

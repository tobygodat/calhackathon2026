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
from .openalex import OpenAlexSource
from .chemrxiv import ChemRxivSource
from .medrxiv import MedRxivSource
# from .nature import NatureSource

SOURCE_REGISTRY: dict[str, type[PaperSource]] = {
    PubMedSource.name: PubMedSource,
    ArxivSource.name: ArxivSource,
    BioRxivSource.name: BioRxivSource,
    OpenAlexSource.name: OpenAlexSource,
    ChemRxivSource.name: ChemRxivSource,
    MedRxivSource.name: MedRxivSource,
    # NatureSource.name: NatureSource,
}

__all__ = [
    "PaperSource",
    "PubMedSource",
    "ArxivSource",
    "BioRxivSource",
    "OpenAlexSource",
    "ChemRxivSource",
    "MedRxivSource",
    # "NatureSource",  # DISABLED — see warning above
    "SOURCE_REGISTRY",
]

"""Baskr data pipeline — multi-source ingestion of recent research papers.

Sources: PubMed, arXiv, bioRxiv.

Quick start:
    from implementations.data_pipeline import DataPipeline

    pipe = DataPipeline()                       # all sources
    result = pipe.fetch("gut microbiome immunotherapy", days=7)
    for paper in result.papers:
        print(paper.citation())
"""

from .config import CONFIG, Config
from .models import Paper
from .pipeline import DataPipeline, FetchResult

__all__ = ["DataPipeline", "FetchResult", "Paper", "Config", "CONFIG"]

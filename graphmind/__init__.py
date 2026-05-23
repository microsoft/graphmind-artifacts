"""GraphMind extraction pipeline (CIKM 2026, §3.2)."""
import logging

from .extractor import extract_workflow_graph_from_dict, summarize_workflow_graph
from .pipeline import build_pipeline
from .spreadsheet_extractor import (
    SPREADSHEET_DOMAINS,
    extract_workflow_graph_from_sample,
    load_jsonl,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

__all__ = [
    "extract_workflow_graph_from_dict",
    "summarize_workflow_graph",
    "build_pipeline",
    "extract_workflow_graph_from_sample",
    "load_jsonl",
    "SPREADSHEET_DOMAINS",
]

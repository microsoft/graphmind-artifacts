"""Spreadsheet workflow_graph extractor (generalizability track, single-call).

Companion to ``extractor.extract_workflow_graph_from_dict``: instead of running the
11-node PocketFlow pipeline over an ICM trace, this module takes a solved
SpreadsheetBench record and produces the same ``{domain, workflow_graph, id}`` schema
via a single LLM call.
"""
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from .llm_client import call_llm
from .text_utils import extract_json_from_string, load_prompt

logger = logging.getLogger("graphmind")

SPREADSHEET_DOMAINS = [
    "text_manipulation",
    "lookup_reference",
    "date_time",
    "conditional_logic",
    "aggregation",
    "formatting",
    "data_validation",
    "array_formula",
    "vba_macro",
    "data_transformation",
    "chart_visualization",
    "pivot_table",
    "general",
]

_CONTEXT_CHAR_LIMIT = 2000


def _build_prompt(sample: Dict[str, Any]) -> str:
    template = load_prompt("12_spreadsheet_taxonomy.md")
    return template.format(
        domains=", ".join(SPREADSHEET_DOMAINS),
        instruction=sample.get("instruction", ""),
        context=(sample.get("context", "") or "")[:_CONTEXT_CHAR_LIMIT],
        solution=sample.get("solution", ""),
    )


def extract_workflow_graph_from_sample(sample: Dict[str, Any], max_retries: int = 3) -> Optional[Dict]:
    """Extract a single SpreadsheetBench record into the standard workflow_graph dict."""
    prompt = _build_prompt(sample)
    sample_id = str(sample.get("id", "unknown"))

    for attempt in range(max_retries):
        try:
            raw = call_llm(prompt, temperature=0.1, max_tokens=2000,
                           response_in_json=True, agent_name="spreadsheet_workflow_graph")
            data = extract_json_from_string(raw)
            if not isinstance(data, dict) or "domain" not in data or "taxonomy" not in data:
                raise ValueError("missing 'domain' or 'taxonomy' field")

            if data["domain"] not in SPREADSHEET_DOMAINS:
                data["domain"] = "general"

            paths = [p for p in data.get("taxonomy", []) if isinstance(p, dict)
                     and isinstance(p.get("path"), list) and len(p["path"]) >= 2]
            if not paths:
                raise ValueError("no valid paths extracted")

            data["taxonomy"] = paths
            data["id"] = sample_id
            return data
        except Exception as e:
            logger.warning("spreadsheet extract attempt %d/%d failed for %s: %s",
                           attempt + 1, max_retries, sample_id, e)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    logger.error("spreadsheet extract failed for %s after %d attempts", sample_id, max_retries)
    return None


def load_jsonl(path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Read a SpreadsheetBench-style .jsonl file into a list of dicts."""
    path = Path(path)
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def batch_extract(samples: Iterable[Dict[str, Any]], output_dir: Union[str, Path],
                  max_retries: int = 3, save_interval: int = 10) -> List[Dict]:
    """Extract workflow_graphs for a list of samples, saving each one to disk."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = list(samples)
    workflow_graphs: List[Dict] = []
    failed: List[str] = []

    for i, sample in enumerate(samples):
        sample_id = str(sample.get("id", f"sample_{i}"))
        out_path = output_dir / f"{sample_id}.json"
        if out_path.exists():
            workflow_graphs.append(json.loads(out_path.read_text()))
            continue

        wf = extract_workflow_graph_from_sample(sample, max_retries=max_retries)
        if wf:
            workflow_graphs.append(wf)
            out_path.write_text(json.dumps(wf, indent=2, ensure_ascii=False))
        else:
            failed.append(sample_id)

        if (i + 1) % save_interval == 0:
            logger.info("spreadsheet progress: %d/%d (ok=%d failed=%d)",
                        i + 1, len(samples), len(workflow_graphs), len(failed))

    if failed:
        (output_dir / "_failed_ids.json").write_text(json.dumps(failed))
    logger.info("spreadsheet extraction complete: %d ok, %d failed",
                len(workflow_graphs), len(failed))
    return workflow_graphs

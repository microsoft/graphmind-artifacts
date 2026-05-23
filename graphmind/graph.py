"""Workflow graph paths -> networkx graph.

Handles two schemas:
  * Spreadsheet:  ``{"taxonomy": [{"path": ["action: ...", "observation: ..."]}, ...]}``
  * Incident:     ``{"taxonomy": [[{"problem": ..., "node_label": ...}, {"action_id": ..., "node_label": ...}, ...]]}``

Deduplicates nodes keyed by sanitised label; edges between consecutive path
entries carry co-occurrence weights. Emits a ``networkx.DiGraph`` that
``clustering.cluster_graph`` can collapse in place.
"""

from __future__ import annotations

import re
from collections import defaultdict

import networkx as nx


def _sanitise(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", text.lower())[:100]


def _parse_string_step(step: str) -> tuple[str, str, str | None]:
    """``"Action: VLOOKUP..."`` -> ``("action", "VLOOKUP...", None)``."""
    if ":" in step:
        kind, desc = step.split(":", 1)
        kind = kind.strip().lower()
        desc = desc.strip()
    else:
        kind, desc = "action", step.strip()
    if kind not in ("problem", "action", "observation", "resolution"):
        kind = "action"
    return kind, desc, None


def _parse_dict_step(step: dict) -> tuple[str, str, str | None] | None:
    """Incident-schema step: pick ntype from which key is set, label from ``node_label``.

    Returns ``(kind, label, subtype)`` where ``subtype`` mirrors the prod
    action-extractor enum (kql_query, sql_query, incident_transfer, mitigation,
    dashboard_url, other_action, ...) for action nodes, or None otherwise.
    """
    if "incident_id" in step and "node_label" not in step:
        return None  # root marker
    label = step.get("node_label") or step.get("problem") or step.get("observation") \
        or step.get("cause") or step.get("resolution") or step.get("raw_action_string", "")
    if not label:
        return None
    subtype = None
    if "problem" in step:
        kind = "problem"
    elif "action_id" in step or step.get("type"):
        kind = "action"
        subtype = step.get("type")
        if subtype == "mitigation":
            kind = "resolution"
    elif "observation" in step:
        kind = "observation"
    elif "cause" in step or "resolution" in step:
        kind = "resolution"
    else:
        kind = "action"
    return kind, label.strip(), subtype


def _iter_steps(path_item):
    """Yield (kind, desc, subtype) from either schema."""
    if isinstance(path_item, list):  # incident schema: path_item *is* the path
        steps = path_item
    elif isinstance(path_item, dict):  # spreadsheet schema: {"path": [...]}
        steps = path_item.get("path", [])
    else:
        return
    for step in steps:
        if isinstance(step, str):
            yield _parse_string_step(step)
        elif isinstance(step, dict):
            parsed = _parse_dict_step(step)
            if parsed is not None:
                yield parsed


def build_workflow_graph(workflow_graphs: list[dict]) -> nx.DiGraph:
    """Build a directed graph from a list of workflow_graph documents.

    Node attrs: ``label`` (str), ``ntype`` (problem|action|observation|resolution),
    ``subtype`` (str|None — prod action-extractor enum: kql_query, sql_query,
    incident_transfer, dashboard_url, other_action, ...), ``domain`` (str),
    ``frequency`` (int).
    Edge attrs: ``weight`` (int — co-occurrence count along extracted paths).
    """
    g: nx.DiGraph = nx.DiGraph()
    edge_weights: dict[tuple[str, str], int] = defaultdict(int)

    for workflow_graph in workflow_graphs:
        domain = workflow_graph.get("domain", "general")
        for path_item in workflow_graph.get("taxonomy", []):
            prev = None
            for kind, desc, subtype in _iter_steps(path_item):
                nid = f"{kind}_{_sanitise(desc)}"
                if nid not in g:
                    g.add_node(nid, label=desc, ntype=kind, subtype=subtype,
                               domain=domain, frequency=1)
                else:
                    g.nodes[nid]["frequency"] += 1
                    if subtype and not g.nodes[nid].get("subtype"):
                        g.nodes[nid]["subtype"] = subtype
                if prev is not None:
                    edge_weights[(prev, nid)] += 1
                prev = nid

    for (u, v), w in edge_weights.items():
        g.add_edge(u, v, weight=w)
    return g


__all__ = ["build_workflow_graph"]

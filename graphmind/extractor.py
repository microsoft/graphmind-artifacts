"""High-level entry point for running the GraphMind workflow_graph extraction pipeline."""
import logging

from .pipeline import build_pipeline
from .postprocess import (
    add_mitigation_action_nodes,
    gen_labels_for_workflow_graph,
    resolve_actions_in_workflow_graph,
    resolve_observations_in_workflow_graph,
)
from .text_utils import extract_json_from_string

logger = logging.getLogger("graphmind")


def extract_workflow_graph_from_dict(incident_dict: dict, domain: str, chunk_size: int = 2000) -> dict:
    """Run the full GraphMind workflow_graph extraction pipeline on a single incident."""
    output_format = """{
  "domain": "<domain_name>",
  "taxonomy": [
    { "incident_id": "<incident_number>" },
    { "problem": "<clear description of observed issue>" },
    { "action": "<exact action from provided action list>" },
    { "observation": "<observable result if any>" },
    { "action": "<corresponding action taken>" },
    ...
    { "cause": "<explicitly stated root cause if available>" }
  ]
}"""

    shared = {
        "domain": domain,
        "original_domain": domain,
        "chunk_size": chunk_size,
        "transformed_incident_workflow_graphs": [],
        "output_format": output_format,
        "action_lookup_table": {"actions": []},
        "incident_workflow_graphs": [],
        "action_index": 0,
        "image_index": 0,
        "images": {},
        "icm_number": str(incident_dict.get("incident_id", "single_incident")),
        "chunk_workflow_graphs": [],
        "incident": incident_dict,
        "incident_id": 0,
    }

    try:
        pipeline = build_pipeline()
        pipeline.run(shared)

        if shared["incident_workflow_graphs"]:
            workflow_graph = extract_json_from_string(shared["incident_workflow_graphs"][-1])
            resolved = resolve_actions_in_workflow_graph(workflow_graph, shared["action_lookup_table"])
            resolved = resolve_observations_in_workflow_graph(resolved)
            resolved = add_mitigation_action_nodes(resolved)
            resolved = gen_labels_for_workflow_graph(resolved)
            return resolved
        else:
            logger.warning("No workflow_graph extracted.")
            return None
    except Exception as e:
        logger.error("Pipeline failed: %s", e, exc_info=True)
        return None


def summarize_workflow_graph(workflow_graph: dict, name: str):
    """Print a summary of the extracted workflow_graph."""
    if not workflow_graph:
        print(f"[{name}] No workflow_graph extracted.")
        return
    domain = workflow_graph.get("domain", "Unknown")
    paths = workflow_graph.get("taxonomy", [])
    print(f"\n{'='*60}")
    print(f"Workflow graph: {name}")
    print(f"Domain: {domain}")
    print(f"Paths: {len(paths)}")
    for i, path in enumerate(paths):
        # Spreadsheet track: each entry is {"path": ["Problem: ...", "Action: ...", ...]}
        if isinstance(path, dict) and isinstance(path.get("path"), list):
            steps = path["path"]
            print(f"\n  Path {i+1} ({len(steps)} steps):")
            for step in steps:
                print(f"    {step}")
            continue
        # Incident track: each path is a list of node dicts
        print(f"\n  Path {i+1} ({len(path)} nodes):")
        for node in path:
            label = node.get("node_label", "")
            if "problem" in node:
                print(f"    [PROBLEM]    {label}")
            elif "action_id" in node:
                ntype = node.get("type", "action")
                print(f"    [{ntype.upper():12s}] {label}")
            elif "incident_id" in node:
                print(f"    [INCIDENT]   {node['incident_id']}")
    print(f"{'='*60}")

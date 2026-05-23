"""Workflow graph post-processing: action resolution, observation merging, labeling."""
import json
import logging

from .llm_client import call_llm_with_memory
from .text_utils import extract_json_from_string

logger = logging.getLogger("graphmind")


def resolve_actions_in_workflow_graph(workflow_graph: dict, overall_actions: dict) -> dict:
    """Replace action IDs in the workflow_graph with their full details."""
    action_lookup = {a["id"]: a for a in overall_actions.get("actions", [])}
    incident_id = None
    for path_obj in workflow_graph.get("taxonomy", []):
        path = path_obj.get("path", path_obj) if isinstance(path_obj, dict) and "path" in path_obj else path_obj
        for node in path:
            if "incident_id" in node:
                incident_id = node["incident_id"]
    if not incident_id:
        incident_id = workflow_graph.get("incident_id", "unknown")

    def resolve_path(path):
        resolved = []
        for node in path:
            if "action" in node:
                action = action_lookup.get(node["action"])
                if action:
                    resolved.append({
                        "action_id": f"{action['id']}_{incident_id}",
                        "actor": action.get("actor"),
                        "raw_action_string": action["output"].get("extracted_text"),
                        "description": action["output"].get("description", ""),
                        "type": action.get("type")
                    })
                else:
                    resolved.append(node)
            else:
                resolved.append(node)
        return resolved

    resolved_workflow_graph = {"taxonomy": [], "domain": workflow_graph["domain"]}
    for path_obj in workflow_graph.get("taxonomy", []):
        if isinstance(path_obj, dict) and "path" in path_obj:
            resolved_workflow_graph["taxonomy"].append(resolve_path(path_obj["path"]))
        else:
            resolved_workflow_graph["taxonomy"].append(resolve_path(path_obj))
    return resolved_workflow_graph


def resolve_observations_in_workflow_graph(workflow_graph: dict) -> dict:
    """Move observation values into adjacent action nodes."""
    new_workflow_graph = {"domain": workflow_graph.get("domain"), "taxonomy": []}
    for path in workflow_graph.get("taxonomy", []):
        new_path, i = [], 0
        while i < len(path):
            node = path[i]
            if "observation" in node:
                obs_val = node["observation"]
                if i > 0 and ("action_id" in path[i-1] or "action" in path[i-1]):
                    prev = dict(path[i-1])
                    prev["possible_outcome"] = obs_val
                    new_path[-1] = prev
                if i+1 < len(path) and ("action_id" in path[i+1] or "action" in path[i+1]):
                    next_action = dict(path[i+1])
                    next_action["trigger_observation"] = obs_val
                    path[i+1] = next_action
                i += 1
                continue
            new_path.append(node)
            i += 1
        new_workflow_graph["taxonomy"].append(new_path)
    return new_workflow_graph


def add_mitigation_action_nodes(workflow_graph: dict) -> dict:
    """Combine cause/resolution into synthetic mitigation nodes."""
    new_workflow_graph = {"domain": workflow_graph.get("domain"), "taxonomy": []}
    for path_idx, path in enumerate(workflow_graph.get("taxonomy", [])):
        new_path, cause_val, resolution_val = [], None, None
        incident_id = next((n.get("incident_id") for n in path if "incident_id" in n), "unknown")
        for node in path:
            if "cause" in node:
                cause_val = node["cause"]
            elif "resolution" in node:
                resolution_val = node["resolution"]
            else:
                new_path.append(node)
        if cause_val is not None or resolution_val is not None:
            has_transfer = any("transfer" in str(v).lower() for v in [cause_val, resolution_val] if v)
            if not has_transfer:
                mitigation_node = {"action_id": f"action_mitigation_{path_idx}_{incident_id}", "type": "mitigation"}
                if cause_val:
                    mitigation_node["cause"] = cause_val
                if resolution_val:
                    mitigation_node["resolution"] = resolution_val
                new_path.append(mitigation_node)
        new_workflow_graph["taxonomy"].append(new_path)

    filtered = []
    for idx, path in enumerate(new_workflow_graph["taxonomy"]):
        if idx == 0 or (path and isinstance(path[-1], dict) and path[-1].get("type") in ("mitigation", "incident_transfer")):
            filtered.append(path)
    new_workflow_graph["taxonomy"] = filtered
    return new_workflow_graph


def gen_labels_for_workflow_graph(workflow_graph: dict) -> dict:
    """Generate short labels for each node using LLM."""
    problem_count = 0
    for path in workflow_graph.get("taxonomy", []):
        incident_id = next((n.get("incident_id", "") for n in path if "incident_id" in n), "")
        for node in path:
            if "incident_id" in node:
                node["id"] = f"incident_0_{incident_id}"
            elif "problem" in node:
                node["id"] = f"problem_{problem_count}_{incident_id}"
                problem_count += 1
            elif "action_id" in node:
                node["id"] = node["action_id"]

    for path in workflow_graph.get("taxonomy", []):
        prompt = f"""You are an expert at creating concise, specific titles for technical troubleshooting steps.

Generate SHORT titles (5-10 words max) for EACH node. Do NOT include ticket-specific info (IDs, GUIDs, session numbers).

### NODES TO LABEL:
{json.dumps(path, indent=2)}

### OUTPUT FORMAT:
Return a JSON object mapping node IDs to titles. Skip incident_id nodes."""

        for attempt in range(3):
            try:
                response = call_llm_with_memory(
                    [{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}, agent_name="gen_labels"
                )
                labels_map = extract_json_from_string(response)
                for node in path:
                    if "incident_id" in node:
                        continue
                    node["node_label"] = labels_map.get(node.get("id", ""), node.get("problem", node.get("action_id", ""))[:80])
                break
            except Exception as e:
                logger.warning("Label gen attempt %d failed: %s", attempt + 1, e)
                if attempt == 2:
                    for node in path:
                        if "problem" in node:
                            node["node_label"] = node["problem"][:80]
                        else:
                            node["node_label"] = node.get("description", node.get("action_id", ""))[:80]
    return workflow_graph

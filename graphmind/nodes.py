"""PocketFlow Node classes for the GraphMind extraction pipeline (§3.2)."""
import json
import logging

import dirtyjson
from bs4 import BeautifulSoup
from pocketflow import Node

from .llm_client import (
    call_llm_with_memory,
    call_llm_with_memory_for_image,
)
from .text_utils import (
    are_similar,
    clean_spaces,
    clean_text,
    decode_adx_link,
    estimate_tokens,
    extract_base64_image,
    extract_img_ids,
    extract_json_from_string,
    has_any_img_id_tag,
    load_prompt,
    normalize_command,
    remove_action_tags_for_filtered,
    remove_tables,
    replace_action_tags_with_id,
    replace_img_tags_with_placeholders,
    split_chain,
)

logger = logging.getLogger("graphmind")


class IncidentSummary(Node):
    """Extract the problem summary from an incident."""

    def prep(self, shared):
        self.shared = shared
        return shared["incident"]

    def exec(self, incident):
        raw = incident.get("raw", "")
        summary = dirtyjson.loads(raw).get("summary", "")
        summary, self.shared = replace_img_tags_with_placeholders(summary, self.shared)
        prompt = f"""You are a support assistant. Given the incident summary below, extract only the **problem summary** — a concise description of the issue being reported.

Respond ONLY in this JSON format:
{{
  "problem_summary": "<the extracted problem statement>"
}}

Incident Summary:
{summary}"""
        message_history = [{"role": "user", "content": prompt}]
        response = call_llm_with_memory(
            message_history, response_format={"type": "json_object"}, agent_name="IncidentSummary"
        )
        parsed = extract_json_from_string(response)
        if not parsed or "problem_summary" not in parsed:
            logger.warning("Failed to parse problem summary, using raw summary.")
            problem_summary = summary[:500]
        else:
            problem_summary = parsed["problem_summary"].strip()
        self.shared["summary"] = problem_summary
        logger.info("Problem summary extracted: %s", problem_summary[:120])
        return problem_summary

    def post(self, shared, prep_res, exec_res):
        return "default"


class IncidentMitigation(Node):
    """Extract mitigation information from an incident."""

    def prep(self, shared):
        self.shared = shared
        return shared["incident"]

    def exec(self, incident):
        mitigation_html = incident.get("metadata", {}).get("mitigation", "")
        if mitigation_html:
            soup = BeautifulSoup(mitigation_html, "html.parser")
            mitigation = soup.get_text()
            self.shared["mitigation"] = f"<mitigation>{clean_text(mitigation)}</mitigation>"
            logger.info("Incident mitigation extracted.")
        else:
            mitigation = None
        return mitigation

    def post(self, shared, prep_res, exec_res):
        return "default"


class IncidentPreprocess(Node):
    """Preprocess incident descriptions into variable-size token chunks."""

    def prep(self, shared):
        self.shared = shared
        return shared["incident"]

    def exec(self, incident):
        raw = incident.get("raw", "")
        try:
            description = dirtyjson.loads(raw).get("communications", [])
        except Exception as e:
            logger.error("Failed to parse incident JSON: %s", e)
            return []

        filtered_description = []
        for idx, entry in enumerate(description):
            if entry.get("ChangedBy") != "icmautosvc" or entry.get("Text", "").startswith(
                "This incident is auto-assigned"
            ):
                cleaned_text, self.shared = replace_img_tags_with_placeholders(
                    entry.get("Text", ""), self.shared
                )
                cleaned_text = clean_text(cleaned_text)
                token_count = estimate_tokens(cleaned_text)
                if token_count > 500:
                    try:
                        cleaned_text = remove_tables(cleaned_text, max_token=20000)
                    except Exception as e:
                        logger.warning("remove_tables failed for entry %d, using cleaned text: %s", idx, e)
                filtered_entry = {
                    "Text": cleaned_text,
                    "ChangedBy": entry.get("ChangedBy", "unknown"),
                }
                filtered_description.append(filtered_entry)

        max_tokens = self.shared["chunk_size"]
        chunks, current_chunk, current_token_count = [], [], 0

        for entry in filtered_description:
            text = entry.get("Text", "")
            token_count = estimate_tokens(text)
            if current_token_count + token_count < max_tokens:
                current_chunk.append(entry)
                current_token_count += token_count
            else:
                chunks.append(current_chunk)
                current_chunk = [entry]
                current_token_count = token_count
        if current_chunk:
            chunks.append(current_chunk)

        summary = self.shared.get("summary", "")
        summary_entry = {"Text": summary, "ChangedBy": "summary"}
        if len(chunks) > 0:
            chunks[0].insert(0, summary_entry)
        else:
            chunks.append([summary_entry])
        if "mitigation" in self.shared:
            mitigation = self.shared.get("mitigation", "")
            mitigation_entry = {"Text": mitigation, "ChangedBy": "mitigation"}
            chunks[-1].append(mitigation_entry)

        self.shared["descriptions"] = chunks
        self.shared["annotated_descriptions"] = []
        self.shared["description_index"] = 0
        logger.info("Preprocessing complete. %d chunks created.", len(chunks))
        return chunks

    def post(self, shared, prep_res, exec_res):
        return "default"


class IncidentDescription(Node):
    """Select the current description chunk for processing."""

    def prep(self, shared):
        self.shared = shared
        return shared["descriptions"], shared["description_index"]

    def exec(self, inputs):
        descriptions, description_index = inputs
        description_instance = str(descriptions[description_index])
        self.shared["description_instance"] = description_instance
        self.shared["num_descriptions"] = len(descriptions)
        logger.debug("Passing description %d", description_index)
        return description_instance

    def post(self, shared, prep_res, exec_res):
        return "default"


class ExtractActionsChunk(Node):
    """Extract and annotate actions (queries, commands, URLs) from a description chunk."""

    def prep(self, shared):
        self.shared = shared
        return shared["description_instance"]

    def exec(self, inputs):
        description_instance = inputs
        prompt = load_prompt("06_extract_actions_chunk.md").replace(
            "{description_instance}", description_instance
        )

        message_history = [{"role": "user", "content": prompt}]

        response_json = None
        for attempt in range(3):
            response = call_llm_with_memory(
                message_history, response_format={"type": "json_object"}, agent_name="ExtractActionsChunk"
            )
            response_json = extract_json_from_string(response)
            if response_json and "actions" in response_json and "text" in response_json:
                all_have_required_fields = True
                for action in response_json["actions"]:
                    if not isinstance(action.get("output"), dict) or "extracted_text" not in action.get("output", {}):
                        all_have_required_fields = False
                        break
                    if "dependency" not in action or not isinstance(action.get("dependency"), dict):
                        all_have_required_fields = False
                        break
                if all_have_required_fields:
                    break
                if attempt < 2:
                    message_history.append({"role": "assistant", "content": response})
                    message_history.append({"role": "user", "content": "Some actions are missing required fields. Please ensure every action has: (1) an 'output' object with an 'extracted_text' field, and (2) a 'dependency' object with 'has_dependency', 'depends_on_action_index', 'dependency_type', and 'dependency_description' fields. Return valid JSON."})
            else:
                if attempt < 2:
                    message_history.append({"role": "assistant", "content": response})
                    message_history.append({"role": "user", "content": "The response format was invalid. Please return a valid JSON object with an 'actions' array and 'text' field."})

        index = self.shared.get("action_index", 0)
        filtered_actions = []
        previous_command_normalized = None

        if response_json and "actions" in response_json:
            original_actions = response_json["actions"]
            num_original = len(original_actions)

            for rev_idx, item in enumerate(reversed(original_actions)):
                original_idx = num_original - 1 - rev_idx
                if item.get("type") == "dashboard" and ".windows.net" in item.get("output", {}).get("extracted_text", ""):
                    continue
                if item.get("type") == "kql_query_link":
                    item["type"] = "kql_query"
                    decoded_query = decode_adx_link(item["output"]["extracted_text"])
                    if "unvalid url" in decoded_query.lower() or "invalid url" in decoded_query.lower():
                        continue
                    item["output"]["extracted_text"] = decoded_query

                current_normalized = normalize_command(item.get("output", {}).get("extracted_text", ""))
                if previous_command_normalized and are_similar(current_normalized, previous_command_normalized):
                    continue
                previous_command_normalized = current_normalized
                item["_original_idx"] = original_idx
                filtered_actions.append(item)

            filtered_actions.reverse()

            original_to_filtered_idx = {}
            for filtered_idx, item in enumerate(filtered_actions):
                if "_original_idx" in item:
                    original_to_filtered_idx[item["_original_idx"]] = filtered_idx
                    del item["_original_idx"]

            for item in filtered_actions:
                item["id"] = "action_" + str(self.shared["action_index"])
                self.shared["action_index"] += 1

            self._update_dependency_references(filtered_actions, original_to_filtered_idx)

            response_json["actions"] = filtered_actions
            response_json["text"] = remove_action_tags_for_filtered(response_json["text"])
            response_json["text"] = replace_action_tags_with_id(response_json["text"], index)
            self.shared["description_instance"] = clean_spaces(response_json["text"])
            self.shared["chunk_actions"] = response_json
            if "overall_actions" not in self.shared:
                self.shared["overall_actions"] = response_json
            else:
                self.shared["overall_actions"]["actions"].extend(response_json["actions"])
        else:
            self.shared["chunk_actions"] = {"actions": [], "text": self.shared["description_instance"]}

        logger.info("Chunk %d/%d: %d actions extracted.",
                    self.shared.get('description_index', 0) + 1,
                    self.shared.get('num_descriptions', 0),
                    len(filtered_actions))
        return response_json

    def _update_dependency_references(self, filtered_actions, original_to_filtered_idx):
        for action in filtered_actions:
            dependency = action.get("dependency", {})
            if not dependency or not dependency.get("has_dependency", False):
                continue
            original_dep_idx = dependency.get("depends_on_action_index")
            if original_dep_idx is None:
                continue
            if original_dep_idx in original_to_filtered_idx:
                new_filtered_idx = original_to_filtered_idx[original_dep_idx]
                if 0 <= new_filtered_idx < len(filtered_actions):
                    dep_action_id = filtered_actions[new_filtered_idx].get("id")
                    dep_action_num = int(dep_action_id.split("_")[1]) if "_" in dep_action_id else new_filtered_idx
                    dependency["depends_on_action_id"] = dep_action_id
                    dependency["depends_on_action_index"] = dep_action_num
                else:
                    dependency["has_dependency"] = False
                    dependency["depends_on_action_index"] = None
            else:
                dependency["has_dependency"] = False
                dependency["depends_on_action_index"] = None

    def post(self, shared, prep_res, exec_res):
        if len(self.shared["chunk_actions"]["actions"]) == 0 or exec_res is None:
            logger.info("Chunk %d/%d: 0 actions, skipping results.",
                        self.shared['description_index'] + 1, self.shared['num_descriptions'])
            self.shared["annotated_descriptions"].append(self.shared["description_instance"])
            if self.shared["description_index"] < self.shared["num_descriptions"] - 1:
                self.shared["description_index"] += 1
                return "no_actions_present"
            else:
                if "overall_results" in self.shared:
                    self.shared["chains_of_actions"] = split_chain(self.shared["overall_results"])
                    return "all_chunks_processed"
                else:
                    return "final"
        else:
            return "extract_results_from_images"


class ExtractImageDescription(Node):
    """Extract descriptions from images embedded in incident descriptions."""

    def prep(self, shared):
        self.shared = shared
        return shared["description_instance"], shared["chunk_actions"]["actions"]

    def exec(self, inputs):
        description_instance, chunk_actions = inputs

        def image_analyzer(text_context, action, image_base64):
            prompt = load_prompt("02_image_analyzer.md").replace(
                "{action}", json.dumps(action)
            ).replace("{text_context}", text_context)
            message_history = [{"role": "user", "content": prompt}]
            response = call_llm_with_memory_for_image(
                message_history, image=image_base64,
                response_format={"type": "json_object"}, agent_name="ImageAnalyzer"
            )
            return extract_json_from_string(response)

        for idx in range(len(chunk_actions)):
            action = chunk_actions[idx]
            extracted_text = action.get("output", {}).get("extracted_text", "")
            if has_any_img_id_tag(extracted_text):
                img_ids = extract_img_ids(extracted_text)
                for img_id in img_ids:
                    img_tag = self.shared.get("images", {}).get(img_id)
                    if img_tag:
                        base64_data = extract_base64_image(img_tag)
                        if base64_data:
                            text_context = description_instance[:500]
                            result = image_analyzer(text_context, action, base64_data)
                            if result:
                                desc = result.get("output", {}).get("description", "")
                                description_instance = description_instance.replace(
                                    f"<img>{img_id}</img>",
                                    f"<image_description>{desc}</image_description>"
                                )

        self.shared["description_instance"] = description_instance
        return description_instance

    def post(self, shared, prep_res, exec_res):
        return "default"


class ExtractResultsChunk(Node):
    """Extract result blocks (tables, outputs) following actions in a description chunk."""

    def prep(self, shared):
        self.shared = shared
        return shared["description_instance"], shared["chunk_actions"]["actions"]

    def exec(self, inputs):
        description_instance, chunk_actions = inputs
        prompt = load_prompt("07_extract_results_chunk.md").replace(
            "{description_instance}", description_instance
        ).replace("{chunk_actions}", json.dumps(chunk_actions, indent=2))

        message_history = [{"role": "user", "content": prompt}]
        extracted_blocks = []
        parsed = None

        for attempt in range(3):
            response = call_llm_with_memory(
                message_history, response_format={"type": "json_object"}, agent_name="ExtractResultsChunk"
            )
            parsed = extract_json_from_string(response)
            if parsed and "actions" in parsed:
                extracted_blocks = parsed["actions"]
                if len(extracted_blocks) >= len(chunk_actions):
                    break
                if attempt < 2:
                    message_history.append({"role": "assistant", "content": response})
                    message_history.append({"role": "user", "content": f"You extracted results for {len(extracted_blocks)} actions but there are {len(chunk_actions)} actions. Please extract results for ALL actions."})
            else:
                if attempt < 2:
                    message_history.append({"role": "assistant", "content": response})
                    message_history.append({"role": "user", "content": "Invalid format. Please return valid JSON with an 'actions' array and 'text' field."})

        extracted_map = {}
        for block in extracted_blocks:
            block_id = block.get("id", "")
            clean_id = block_id.replace("result_", "") if block_id.startswith("result_") else block_id
            extracted_map[clean_id] = block

        reordered_blocks = []
        for action in chunk_actions:
            action_id = action["id"]
            if action_id in extracted_map:
                reordered_blocks.append(extracted_map[action_id])
            else:
                reordered_blocks.append({
                    "id": f"result_{action_id}",
                    "type": "other_result",
                    "output": {"description": "No output found.", "extracted_text": "No output found."},
                    "actor": action.get("actor", "unknown")
                })

        extracted_blocks = reordered_blocks
        self.shared["description_instance"] = clean_spaces(
            parsed.get("text", description_instance) if parsed else description_instance
        )
        self.shared["annotated_descriptions"].append(self.shared["description_instance"])

        logger.info("Chunk %d/%d results: %d blocks extracted.",
                    self.shared['description_index'] + 1, self.shared['num_descriptions'], len(extracted_blocks))

        if "overall_results" not in self.shared:
            self.shared["overall_results"] = extracted_blocks
        else:
            self.shared["overall_results"].extend(extracted_blocks)
        return extracted_blocks

    def post(self, shared, prep_res, exec_res):
        if self.shared["description_index"] < self.shared["num_descriptions"] - 1:
            self.shared["description_index"] += 1
            return "next_chunk"
        else:
            if "overall_results" in self.shared:
                self.shared["chains_of_actions"] = split_chain(self.shared["overall_results"])
                return "all_chunks_processed"
            else:
                return "final"


class ExtractWorkflowGraph(Node):
    """Extract a hierarchical workflow_graph from annotated incident descriptions and actions."""

    def filter_dashboard_urls_with_icm_number(self, actions, icm_number):
        return [a for a in actions if not (
            a.get("type") == "dashboard_url" and str(icm_number) in a.get("output", {}).get("extracted_text", "")
        )]

    def prep(self, shared):
        self.shared = shared
        annotated_icm = "\n\n".join(d for d in self.shared["annotated_descriptions"])
        self.shared["annotated_icm"] = annotated_icm
        return annotated_icm

    def extract_action_ids(self, workflow_graph_str):
        try:
            data = json.loads(workflow_graph_str)
        except Exception:
            return set()
        def collect_actions(node):
            ids = set()
            if isinstance(node, dict):
                if "action" in node:
                    ids.add(node["action"])
                for v in node.values():
                    ids |= collect_actions(v)
            elif isinstance(node, list):
                for item in node:
                    ids |= collect_actions(item)
            return ids
        return collect_actions(data)

    def format_missing_actions(self, missing_actions, shared):
        return "\n".join(
            row["id"] for row in shared["overall_actions"]["actions"] if row["id"] in missing_actions
        )

    def exec(self, icm):
        self.shared["paths"] = []
        icm_number = self.shared["icm_number"]

        if "overall_actions" in self.shared:
            self.shared["overall_actions"]["actions"] = self.filter_dashboard_urls_with_icm_number(
                self.shared["overall_actions"]["actions"], icm_number
            )

        filtered_chains = []
        for chain in self.shared.get("chains_of_actions", []):
            filtered_chain = self.filter_dashboard_urls_with_icm_number(chain, icm_number)
            filtered_chains.append(filtered_chain)
        self.shared["chains_of_actions"] = filtered_chains

        result_chunks, action_chunks = [], []
        for chain in self.shared.get("chains_of_actions", []):
            for item in chain:
                item_id = item.get("id", "")
                if item_id.startswith("result_"):
                    result_chunks.append(item)
                else:
                    action_chunks.append(item)

        all_action_ids = {a["id"] for a in action_chunks}

        result_lookup = {r["id"].replace("result_", ""): r for r in result_chunks if r}
        merged_actions = []
        for action in action_chunks:
            merged_actions.append({"action": action, "result": result_lookup.get(action["id"])})

        action_chain = [{"action": a["id"]} for a in action_chunks]

        output_format = self.shared["output_format"]

        prompt = (
            load_prompt("08_extract_taxonomy.md")
            .replace('{self.shared["icm_number"]}', str(icm_number))
            .replace('{self.shared["output_format"]}', str(output_format))
            .replace("{merged_actions}", json.dumps(merged_actions, indent=2))
            .replace("{action_chain}", json.dumps(action_chain, indent=2))
            .replace("{icm}", icm)
        )

        message_history = [{"role": "user", "content": prompt}]
        response = call_llm_with_memory(
            message_history, response_format={"type": "json_object"}, agent_name="ExtractWorkflowGraph"
        )
        message_history.append({"role": "assistant", "content": response})

        final_extracted_ids = self.extract_action_ids(response)
        missing = all_action_ids - final_extracted_ids
        extra = final_extracted_ids - all_action_ids
        no_progress_count = 0

        while (missing or extra) and no_progress_count < 5:
            missing_action_text = self.format_missing_actions(missing, self.shared)
            retry_prompt = f"""The following actions are still **missing** from the workflow_graph:
{missing_action_text}

The following actions are **extra** and should NOT be included:
{', '.join(extra) if extra else 'None'}

Please regenerate the workflow_graph to include all actions. Return only valid JSON."""
            message_history.append({"role": "user", "content": retry_prompt})
            response = call_llm_with_memory(
                message_history, response_format={"type": "json_object"}, agent_name="ExtractWorkflowGraph"
            )
            message_history.append({"role": "assistant", "content": response})
            new_ids = self.extract_action_ids(response)
            if new_ids.issubset(final_extracted_ids):
                no_progress_count += 1
            else:
                no_progress_count = 0
                final_extracted_ids.update(new_ids)
            missing = all_action_ids - final_extracted_ids
            extra = final_extracted_ids - all_action_ids

        response_json = json.loads(response)
        inferred_domain = response_json.get('domain', 'Unknown')
        if inferred_domain.lower() != 'unknown':
            self.shared['domain'] = inferred_domain

        path = response_json['taxonomy']
        response_json['taxonomy'] = [{"path": path}]
        response = json.dumps(response_json)

        self.shared["paths"].append(response)
        self.shared["chunk_workflow_graphs"].append(response)
        logger.info("Workflow graph extracted (total actions: %d).",
                    len(self.shared.get('overall_actions', {}).get('actions', [])))
        return response

    def post(self, shared, prep_res, exec_res):
        return "default"


class PruneWorkflowGraph(Node):
    """Prune workflow_graph paths (currently pass-through)."""

    def prep(self, shared):
        self.shared = shared
        return self.shared["chunk_workflow_graphs"]

    def exec(self, inputs):
        return self.shared.get("chunk_workflow_graphs", [])

    def post(self, shared, prep_res, exec_res):
        return "default"


class AlignWorkflowGraph(Node):
    """Align and merge multiple chunk workflow_graphs into a single workflow_graph."""

    def prep(self, shared):
        self.shared = shared
        return self.shared["chunk_workflow_graphs"]

    def exec(self, inputs):
        parsed_workflow_graphs = [extract_json_from_string(t) for t in inputs]
        domain = self.shared.get("original_domain") or self.shared.get("domain") or (parsed_workflow_graphs[0].get("domain", "unknown") if parsed_workflow_graphs else "unknown")
        workflow_graphs = []
        for parsed in parsed_workflow_graphs:
            for workflow_graph_obj in parsed.get("taxonomy", []):
                if "path" in workflow_graph_obj:
                    workflow_graphs.append(workflow_graph_obj["path"])
        incident_workflow_graph = {"domain": domain, "taxonomy": workflow_graphs}
        self.shared["incident_workflow_graphs"].append(str(incident_workflow_graph))
        logger.info("Taxonomies aligned and merged.")
        return incident_workflow_graph

    def post(self, shared, prep_res, exec_res):
        return "default"


class FinalNode(Node):
    """Final node for cleanup."""

    def prep(self, shared):
        for key in ["incident", "descriptions", "description_instance", "description_index",
                    "num_descriptions", "chunk_workflow_graphs", "chunk_actions", "summary",
                    "mitigation", "annotated_descriptions", "annotated_icm",
                    "chains_of_actions", "images", "image_index"]:
            shared.pop(key, None)

        if "overall_actions" in shared:
            shared["action_lookup_table"]["actions"].extend(shared["overall_actions"]["actions"])
            shared.pop("overall_actions")
        return None

    def exec(self, input):
        return None

    def post(self, shared, prep_res, exec_res):
        logger.info("Pipeline complete.")
        return None

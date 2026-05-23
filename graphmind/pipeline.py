"""PocketFlow pipeline wiring for the GraphMind §3.2 extraction stages."""
from pocketflow import Flow

from .nodes import (
    AlignWorkflowGraph,
    ExtractActionsChunk,
    ExtractImageDescription,
    ExtractResultsChunk,
    ExtractWorkflowGraph,
    FinalNode,
    IncidentDescription,
    IncidentMitigation,
    IncidentPreprocess,
    IncidentSummary,
    PruneWorkflowGraph,
)


def build_pipeline() -> Flow:
    summary_node = IncidentSummary()
    mitigation_node = IncidentMitigation()
    preprocess_node = IncidentPreprocess()
    chunk_node = IncidentDescription()
    extract_actions_node = ExtractActionsChunk()
    extract_image_node = ExtractImageDescription()
    extract_results_node = ExtractResultsChunk()
    extract_workflow_graph_node = ExtractWorkflowGraph()
    prune_node = PruneWorkflowGraph()
    align_node = AlignWorkflowGraph()
    final_node = FinalNode()

    summary_node >> mitigation_node
    mitigation_node >> preprocess_node
    preprocess_node >> chunk_node
    chunk_node >> extract_actions_node
    extract_actions_node - "no_actions_present" >> chunk_node
    extract_actions_node - "extract_results_from_images" >> extract_image_node
    extract_actions_node - "all_chunks_processed" >> extract_workflow_graph_node
    extract_actions_node - "final" >> final_node
    extract_image_node >> extract_results_node
    extract_results_node - "all_chunks_processed" >> extract_workflow_graph_node
    extract_results_node - "final" >> final_node
    extract_results_node - "next_chunk" >> chunk_node
    extract_workflow_graph_node >> prune_node
    prune_node >> align_node
    align_node >> final_node

    return Flow(start=summary_node)

# GraphMind Extraction Prompts

This folder contains all LLM prompts used in the **GraphMind** multi-agent workflow extraction pipeline, as described in the CIKM 2026 submission:

> *GraphMind: From Operational Traces to Self-Evolving Workflow Automation*

## Pipeline Overview

The prompts correspond to the three-stage extraction pipeline (Section 3.2, Figure 3):

### Stage 1: Data Preprocessing
| Prompt | File | Description |
|--------|------|-------------|
| Document Parser | [`01_remove_tables.md`](01_remove_tables.md) | Removes long tabular data from raw text while preserving schema headers |
| Multi-modal Content Synthesizer | [`02_image_analyzer.md`](02_image_analyzer.md) | Extracts descriptions from embedded screenshots via vision-language models |
| KQL URL Decoder | [`03_decode_adx_link.md`](03_decode_adx_link.md) | Decodes KQL queries from compressed ADX/Kusto URLs |
| Text Extractor | [`04_find_text_between_actions.md`](04_find_text_between_actions.md) | Locates text spans between two known actions for image context |

### Stage 2: Workflow Construction
| Prompt | File | Description |
|--------|------|-------------|
| Problem Extractor | [`05_incident_summary.md`](05_incident_summary.md) | Extracts the canonical problem statement from an incident summary |
| Action Extractor | [`06_extract_actions_chunk.md`](06_extract_actions_chunk.md) | Identifies and annotates all actions (queries, commands, URLs) with dependency tracking |
| Resolution Extractor | [`07_extract_results_chunk.md`](07_extract_results_chunk.md) | Extracts result blocks (tables, outputs) following each action |
| Workflow Extractor | [`08_extract_taxonomy.md`](08_extract_taxonomy.md) | Assembles the full workflow taxonomy with problem→action→observation chains |

### Stage 3: Pruning and Alignment
| Prompt | File | Description |
|--------|------|-------------|
| Semantic Similarity | [`09_is_semantically_similar.md`](09_is_semantically_similar.md) | Determines if two resolution strings are semantically equivalent |
| Taxonomy Retry | [`10_taxonomy_retry.md`](10_taxonomy_retry.md) | Iteratively repairs missing or extra actions in extracted taxonomies |
| Label Generator | [`11_gen_labels_for_taxonomy.md`](11_gen_labels_for_taxonomy.md) | Generates concise node titles for visualization and indexing |

## Template Variables

Prompts use Python f-string interpolation. Template variables are denoted as `{variable_name}` and are populated at runtime with incident-specific data. See each file for details on expected inputs.

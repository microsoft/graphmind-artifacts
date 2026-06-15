# GraphMind Artifact (CIKM 2026)

Reproducibility artifact for the CIKM 2026 submission:

> *GraphMind: From Operational Traces to Self-Evolving Workflow Automation*

This repository contains the **redacted implementation of the offline workflow-extraction pipeline** described in Section 3 of the paper — the system that converts raw incident management tickets (ICMs), documentation, and structured logs into pruned, aligned **workflow graphs** that downstream agents can search and execute.

## Pipeline overview

![GraphMind offline extraction pipeline](figure1_pipeline.png)

The pipeline runs in two stages (paper §3.1–3.3):

1. **Data Preprocessing** — heterogeneous inputs (ICMs, docs, JSON) are parsed, multi-modal content (screenshots, embedded tables) is synthesized into text, and the resulting transcript is chunked into LLM-sized windows by an intelligent chunking agent.
2. **Workflow Construction** — three parallel extractors (Problem, Resolution, Action) feed a Workflow Extractor that assembles `problem → action → observation → … → cause/resolution` chains. A Pruning Agent removes duplicate or low-quality paths, and an Alignment Agent merges semantically equivalent branches across incidents.

## Repository layout

```
artifact/
├── README.md                    # this file
├── LICENSE                      # MIT
├── graphmind_pipeline.ipynb     # end-to-end runnable notebook (entry point)
│
├── graphmind/                   # minimal runnable package
│   ├── pipeline.py              # PocketFlow Flow assembly (paper Fig. 3)
│   ├── nodes.py                 # 11 PocketFlow Nodes — one per pipeline stage
│   ├── postprocess.py           # action resolution, mitigation injection, labeling
│   ├── llm_client.py            # Azure OpenAI chat + embeddings wrapper
│   ├── text_utils.py            # tokenization, JSON extraction, image handling
│   ├── extractor.py             # high-level entry point: extract_workflow_graph_from_dict()
│   ├── spreadsheet_extractor.py # single-call extractor for the SpreadsheetBench track
│   ├── graph.py                 # workflow_graph paths → networkx.DiGraph (§3.3)
│   ├── clustering.py            # cosine + agglomerative cluster_graph() (§3.3)
│   ├── cluster_core.py          # numpy/sklearn clustering primitives
│   └── interfaces.py            # Embedder Protocol
│
├── prompts/                     # 12 LLM prompts (one .md file per stage)
│   ├── 01_remove_tables.md             # §3.1 Document Parser
│   ├── 02_image_analyzer.md            # §3.1 Multi-modal Content Synthesizer
│   ├── 03_decode_adx_link.md           # §3.1 Intelligent Chunking Agent (KQL URL helper)
│   ├── 04_find_text_between_actions.md # §3.1 Intelligent Chunking Agent (text span helper)
│   ├── 05_incident_summary.md          # §3.2 Problem Extractor
│   ├── 06_extract_actions_chunk.md     # §3.2 Action Extractor
│   ├── 07_extract_results_chunk.md     # §3.2 Resolution Extractor
│   ├── 08_extract_taxonomy.md          # §3.2 Workflow Extractor
│   ├── 09_is_semantically_similar.md   # §3.3 Alignment Agent (similarity oracle)
│   ├── 10_taxonomy_retry.md            # §3.2 Workflow Extractor (coverage repair)
│   ├── 11_gen_labels_for_taxonomy.md   # §3.3 Pruning Agent (label generation)
│   └── 12_spreadsheet_taxonomy.md      # SpreadsheetBench single-call extractor
│
├── scripts/                     # standalone helpers
│   └── visualize_clusters.py    # multi-panel PNG of pre/post clustering stats
│
├── data/                        # extraction inputs
│   ├── incident_rca/            # two ICM-style traces (synthesized from public
│   │   │                        # stack traces + anonymized internal patterns;
│   │   │                        # all names/IDs/URLs are redacted)
│   │   ├── test_input_A.json    # connectivity-security incident
│   │   └── test_input_B.json    # client-experiences incident
│   └── spreadsheet/             # SpreadsheetBench generalizability track
│       ├── train_sample.jsonl   # 15-record demo subset
│       └── train_124.jsonl      # full set
│
└── outputs/                     # reference workflow_graphs produced by the notebook
    ├── incident_rca/
    │   ├── taxonomy_A.json
    │   └── taxonomy_B.json
    └── spreadsheet/             # one workflow_graph JSON per spreadsheet record
```

Each prompt file in `prompts/` documents its template variables, the calling Node in `graphmind/nodes.py`, and the corresponding paper agent.

## Running the pipeline

The notebook `graphmind_pipeline.ipynb` is the canonical entry point. Pick a track via the `TRACK` toggle at the top of the notebook:

- `"spreadsheet"` (default) — SpreadsheetBench records → single-call extractor in `graphmind/spreadsheet_extractor.py`.
- `"incidents"` — ICM traces → full 11-node PocketFlow pipeline in `graphmind/pipeline.py`.

Both tracks produce the same `{domain, workflow_graph, id}` schema and the final section (build & cluster) is track-agnostic.

```bash
# 1. install
pip install -r requirements.txt    # pocketflow, openai, jupyter, nbformat, networkx, scikit-learn

# 2. configure Azure OpenAI (or set GRAPHMIND_USE_AZURE=0 for openai.com)
export AZURE_OPENAI_ENDPOINT="https://<your-resource>.openai.azure.com/"
export AZURE_OPENAI_API_KEY="..."
export AZURE_OPENAI_DEPLOYMENT="gpt-5.2"
export AZURE_OPENAI_EMBED_DEPLOYMENT="text-embedding-3-large"   # for §3.3 clustering
export AZURE_OPENAI_API_VERSION="2025-04-01-preview"
export GRAPHMIND_USE_AZURE=1

# 3. run
jupyter nbconvert --to notebook --execute graphmind_pipeline.ipynb \
    --output graphmind_pipeline.executed.ipynb

# 4. (optional) standalone clustering visualization
PYTHONPATH=. python scripts/visualize_clusters.py \
    --input-dir outputs/spreadsheet \
    --output outputs/spreadsheet/cluster_plots.png
```

To run programmatically:

```python
from graphmind.extractor import extract_workflow_graph_from_dict
from graphmind.spreadsheet_extractor import extract_workflow_graph_from_sample
import json

# ICM trace
incident = json.load(open("data/incident_rca/test_input_A.json"))
workflow_graph = extract_workflow_graph_from_dict(incident, domain="CloudDw")

# SpreadsheetBench record
record = json.loads(open("data/spreadsheet/train_sample.jsonl").readline())
workflow_graph = extract_workflow_graph_from_sample(record)
```

## Reproducibility notes

- The two incident traces in `data/incident_rca/` are **not real customer tickets**. They were synthesized from publicly-available stack traces and error patterns, then run through the same anonymization map (below) so the artifact's surface looks like the production input format. No internal incident content is included.
- All names, team names, cluster/database identifiers, and internal URLs in `data/`, `outputs/`, `prompts/`, and the notebook have been **anonymized** with a deterministic literal-string map. The reference workflow_graphs were re-extracted post-anonymization with `gpt-5.2`.
- LLM outputs are non-deterministic; node counts and exact phrasings will vary between runs. The pipeline's structural invariants (every action appears in the chain, each action is preceded by a problem or observation, etc.) are enforced by the Workflow Extractor's retry loop (`prompts/10_taxonomy_retry.md`).
- The pipeline is **stateless** at the incident level — there is no shared store across runs, so each incident produces an independent workflow_graph. Cross-incident merging is the Alignment Agent's job (paper §3.3) and is exercised in the notebook's final cells.

## Synthetic Data Disclosure

This repository contains **synthetic data** generated for research and development purposes.

- The data in this repository does **not** correspond to real individuals, organizations, or events.
- Any similarity to real-world entities is purely coincidental.
- The dataset is designed to reflect the structure, patterns, or statistical properties of real data, but it does not contain actual production or user data.

This synthetic data is provided to enable experimentation, benchmarking, and reproducible research while preserving privacy and avoiding the use of sensitive or proprietary information.

## License

Community Data License Agreement — see [`LICENSE`](LICENSE).

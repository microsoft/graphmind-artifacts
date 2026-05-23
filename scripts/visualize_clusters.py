"""Visualize the GraphMind workflow_graph graph before and after clustering.

Reads workflow_graphs from ``outputs/spreadsheet/`` (or any directory passed via
``--input-dir``), builds the directed graph, clusters semantically-similar
nodes, and writes a multi-panel PNG.

Usage:
    python scripts/visualize_clusters.py
    python scripts/visualize_clusters.py --input-dir outputs/spreadsheet \
        --output outputs/spreadsheet/cluster_plots.png --top-n 15
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

from graphmind.clustering import cluster_graph
from graphmind.graph import build_workflow_graph
from graphmind.llm_client import AzureEmbedder


NTYPE_COLORS = {
    "problem": "#d62728",
    "action": "#1f77b4",
    "observation": "#ff7f0e",
    "resolution": "#2ca02c",
}


def load_workflow_graphs(input_dir: Path) -> list[dict]:
    docs = []
    for fp in sorted(input_dir.glob("*.json")):
        if fp.stem.startswith("_"):
            continue
        try:
            obj = json.loads(fp.read_text())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "taxonomy" in obj:
            docs.append(obj)
    return docs


def plot_before_after_counts(ax, before: nx.DiGraph, after: nx.DiGraph) -> None:
    metrics = ("nodes", "edges")
    b = (before.number_of_nodes(), before.number_of_edges())
    a = (after.number_of_nodes(), after.number_of_edges())
    x = np.arange(len(metrics))
    w = 0.35
    ax.bar(x - w / 2, b, w, label="pre-cluster", color="#9ecae1")
    ax.bar(x + w / 2, a, w, label="post-cluster", color="#3182bd")
    for i, (bv, av) in enumerate(zip(b, a)):
        ax.text(i - w / 2, bv, str(bv), ha="center", va="bottom", fontsize=9)
        ax.text(i + w / 2, av, str(av), ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.set_title("Graph size: before vs after clustering")
    ax.legend()


def plot_ntype_distribution(ax, g: nx.DiGraph) -> None:
    counts = Counter(d.get("ntype", "?") for _, d in g.nodes(data=True))
    types = ["problem", "action", "observation", "resolution"]
    vals = [counts.get(t, 0) for t in types]
    colors = [NTYPE_COLORS[t] for t in types]
    ax.bar(types, vals, color=colors)
    for i, v in enumerate(vals):
        ax.text(i, v, str(v), ha="center", va="bottom", fontsize=9)
    ax.set_title("Node-type distribution (post-cluster)")
    ax.set_ylabel("# nodes")


def plot_top_frequent(ax, g: nx.DiGraph, top_n: int) -> None:
    top = sorted(
        g.nodes(data=True),
        key=lambda kv: kv[1].get("frequency", 0),
        reverse=True,
    )[:top_n]
    labels = [
        f"[{d.get('ntype', '?')[:3]}] {d.get('label', '')[:55]}"
        + (f" x{d['cluster_size']}" if d.get("is_clustered") else "")
        for _, d in top
    ]
    freqs = [d.get("frequency", 0) for _, d in top]
    colors = [NTYPE_COLORS.get(d.get("ntype"), "#888") for _, d in top]
    y = np.arange(len(labels))
    ax.barh(y, freqs, color=colors)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("frequency (path occurrences)")
    ax.set_title(f"Top-{top_n} most frequent nodes")


def plot_cluster_sizes(ax, g: nx.DiGraph) -> None:
    sizes = [d.get("cluster_size", 1) for _, d in g.nodes(data=True)]
    clustered = [s for s in sizes if s > 1]
    if not clustered:
        ax.text(0.5, 0.5, "no nodes merged at this threshold",
                ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Cluster sizes")
        return
    bins = range(2, max(clustered) + 2)
    ax.hist(clustered, bins=bins, color="#6baed6", edgecolor="white")
    ax.set_xlabel("cluster size (# nodes merged into one)")
    ax.set_ylabel("# clusters")
    ax.set_title(f"Cluster size distribution ({len(clustered)} merged clusters)")


def plot_graph_layout(ax, g: nx.DiGraph, max_nodes: int = 60) -> None:
    if g.number_of_nodes() == 0:
        ax.set_title("Graph (empty)")
        return
    if g.number_of_nodes() > max_nodes:
        kept = {n for n, _ in sorted(
            g.nodes(data=True),
            key=lambda kv: kv[1].get("frequency", 0),
            reverse=True,
        )[:max_nodes]}
        h = g.subgraph(kept).copy()
        title = f"Top-{max_nodes} subgraph (by frequency)"
    else:
        h = g
        title = "Full clustered graph"

    pos = nx.spring_layout(h, seed=42, k=0.6 / max(1, np.sqrt(h.number_of_nodes())))
    node_colors = [NTYPE_COLORS.get(d.get("ntype"), "#888") for _, d in h.nodes(data=True)]
    node_sizes = [40 + 20 * d.get("frequency", 1) for _, d in h.nodes(data=True)]

    nx.draw_networkx_edges(h, pos, ax=ax, alpha=0.25, arrows=False, width=0.6)
    nx.draw_networkx_nodes(h, pos, ax=ax, node_color=node_colors,
                           node_size=node_sizes, alpha=0.9, linewidths=0)
    ax.set_title(title)
    ax.set_axis_off()
    legend_handles = [plt.Line2D([0], [0], marker="o", color="w",
                                 markerfacecolor=c, markersize=8, label=t)
                      for t, c in NTYPE_COLORS.items()]
    ax.legend(handles=legend_handles, loc="lower right", fontsize=8, frameon=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path,
                        default=Path("outputs/spreadsheet"),
                        help="directory of workflow_graph JSON files")
    parser.add_argument("--output", type=Path,
                        default=Path("outputs/spreadsheet/cluster_plots.png"),
                        help="PNG output path")
    parser.add_argument("--threshold", type=float, default=0.15,
                        help="cosine-distance threshold for clustering (default 0.15)")
    parser.add_argument("--top-n", type=int, default=15,
                        help="how many top-frequency nodes to show")
    parser.add_argument("--max-graph-nodes", type=int, default=60,
                        help="cap on nodes drawn in the layout panel")
    args = parser.parse_args()

    docs = load_workflow_graphs(args.input_dir)
    if not docs:
        raise SystemExit(f"no workflow_graph JSONs found in {args.input_dir}")
    print(f"loaded {len(docs)} workflow_graphs from {args.input_dir}")

    g_pre = build_workflow_graph(docs)
    g_post = deepcopy(g_pre)
    cluster_graph(g_post, AzureEmbedder(), distance_threshold=args.threshold)
    print(f"pre-cluster : {g_pre.number_of_nodes():4d} nodes  {g_pre.number_of_edges():4d} edges")
    print(f"post-cluster: {g_post.number_of_nodes():4d} nodes  {g_post.number_of_edges():4d} edges")

    fig = plt.figure(figsize=(15, 11))
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 1.4], hspace=0.45, wspace=0.3)
    plot_before_after_counts(fig.add_subplot(gs[0, 0]), g_pre, g_post)
    plot_ntype_distribution(fig.add_subplot(gs[0, 1]), g_post)
    plot_cluster_sizes(fig.add_subplot(gs[1, 0]), g_post)
    plot_top_frequent(fig.add_subplot(gs[1, 1]), g_post, args.top_n)
    plot_graph_layout(fig.add_subplot(gs[2, :]), g_post, args.max_graph_nodes)
    fig.suptitle(f"GraphMind clustering — {args.input_dir.name} "
                 f"({len(docs)} workflow_graphs, threshold={args.threshold})",
                 fontsize=13)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=140, bbox_inches="tight")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()

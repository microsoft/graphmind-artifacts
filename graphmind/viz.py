"""Plot helpers for the GraphMind notebook.

All functions take a matplotlib ``ax`` (or create their own figure) and a
small data argument — either a list of ``(name, workflow_graph)`` pairs, a dict of
workflow_graphs, or a ``networkx.DiGraph``. Keeping the plot logic out of the
notebook lets the cells read as one-liners.
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

from graphmind.graph import _iter_steps, _sanitise

NTYPE_COLORS: dict[str, str] = {
    "problem": "#d62728",
    "action": "#1f77b4",
    "observation": "#ff7f0e",
    "resolution": "#2ca02c",
}
NTYPE_ORDER = ("problem", "action", "observation", "resolution")

_SAVE_DIR = None


def set_save_dir(path) -> None:
    """Save every plot as a PNG into ``path`` (alongside ``plt.show()``)."""
    global _SAVE_DIR
    from pathlib import Path
    _SAVE_DIR = Path(path) if path else None
    if _SAVE_DIR is not None:
        _SAVE_DIR.mkdir(parents=True, exist_ok=True)


def _save(name: str) -> None:
    if _SAVE_DIR is not None:
        plt.savefig(_SAVE_DIR / f"{name}.png", dpi=140, bbox_inches="tight")


# ---------- section 8 (per-track summaries) ----------

def plot_domain_distribution(workflow_graphs_by_id: dict) -> None:
    counts = Counter(t["domain"] for t in workflow_graphs_by_id.values())
    domains = sorted(counts)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(domains, [counts[d] for d in domains], color="#3182bd")
    ax.set_xticklabels(domains, rotation=40, ha="right")
    ax.set_ylabel("# workflow_graphs")
    ax.set_title("Domain label distribution")
    plt.tight_layout()
    _save("8_1_domain_distribution")
    plt.show()


def plot_paths_per_workflow_graph(workflow_graphs_by_id: dict) -> None:
    paths = [len(t["taxonomy"]) for t in workflow_graphs_by_id.values()]
    fig, ax = plt.subplots(figsize=(7, 4))
    bins = range(1, max(paths + [2]) + 2)
    ax.hist(paths, bins=bins, color="#3182bd", align="left")
    ax.set_xlabel("paths per workflow_graph")
    ax.set_ylabel("# workflow_graphs")
    ax.set_title("Paths per workflow_graph")
    plt.tight_layout()
    _save("8_2_paths_per_workflow_graph")
    plt.show()
    print(f"mean={sum(paths)/len(paths):.2f}  max={max(paths)}")


def _path_steps(p):
    return p if isinstance(p, list) else p.get("path", [])


def _step_kind(step):
    if not isinstance(step, dict):
        return None
    if "problem" in step:
        return "problem"
    if "action_id" in step or step.get("type"):
        return "action"
    if "observation" in step:
        return "observation"
    if "cause" in step or "resolution" in step:
        return "resolution"
    return None


def plot_steps_per_incident(workflow_graphs: list[tuple[str, dict]]) -> None:
    names = [n for n, _ in workflow_graphs]
    counts = [sum(len(_path_steps(p)) for p in t.get("taxonomy", [])) for _, t in workflow_graphs]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(names, counts, color="#3182bd")
    for i, v in enumerate(counts):
        ax.text(i, v, str(v), ha="center", va="bottom", fontsize=10)
    ax.set_ylabel("# steps")
    ax.set_title("Steps per incident chain")
    plt.tight_layout()
    _save("8_3_steps_per_incident")
    plt.show()


def plot_step_types_per_incident(workflow_graphs: list[tuple[str, dict]]) -> None:
    names = [n for n, _ in workflow_graphs]
    counts = []
    for _, t in workflow_graphs:
        c: Counter[str] = Counter()
        for path in t.get("taxonomy", []):
            for s in _path_steps(path):
                k = _step_kind(s)
                if k:
                    c[k] += 1
        counts.append(c)
    x = np.arange(len(names))
    width = 0.18
    fig, ax = plt.subplots(figsize=(7, 4))
    for i, k in enumerate(NTYPE_ORDER):
        vals = [c.get(k, 0) for c in counts]
        ax.bar(x + (i - 1.5) * width, vals, width, label=k, color=NTYPE_COLORS[k])
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylabel("# steps")
    ax.set_title("Step types per incident")
    ax.legend(fontsize=8)
    plt.tight_layout()
    _save("8_4_step_types_per_incident")
    plt.show()


# ---------- section 9 (graph + clustering) ----------

def plot_size_before_after(g_pre: nx.DiGraph, g_post: nx.DiGraph) -> None:
    metrics = ("nodes", "edges")
    b = (g_pre.number_of_nodes(), g_pre.number_of_edges())
    a = (g_post.number_of_nodes(), g_post.number_of_edges())
    x = np.arange(len(metrics))
    w = 0.35
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(x - w / 2, b, w, label="pre-cluster", color="#9ecae1")
    ax.bar(x + w / 2, a, w, label="post-cluster", color="#3182bd")
    for i, (bv, av) in enumerate(zip(b, a)):
        ax.text(i - w / 2, bv, str(bv), ha="center", va="bottom", fontsize=9)
        ax.text(i + w / 2, av, str(av), ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.set_title("Graph size: before vs after clustering")
    ax.legend()
    plt.tight_layout()
    _save("9_3_size_before_after")
    plt.show()


def plot_ntype_distribution(g: nx.DiGraph) -> None:
    counts = Counter(d.get("ntype", "?") for _, d in g.nodes(data=True))
    vals = [counts.get(t, 0) for t in NTYPE_ORDER]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(NTYPE_ORDER, vals, color=[NTYPE_COLORS[t] for t in NTYPE_ORDER])
    for i, v in enumerate(vals):
        ax.text(i, v, str(v), ha="center", va="bottom", fontsize=9)
    ax.set_title("Node-type distribution (post-cluster)")
    ax.set_ylabel("# nodes")
    plt.tight_layout()
    _save("9_4_ntype_distribution")
    plt.show()


def plot_cluster_sizes(g: nx.DiGraph) -> None:
    sizes = [d.get("cluster_size", 1) for _, d in g.nodes(data=True)]
    clustered = [s for s in sizes if s > 1]
    fig, ax = plt.subplots(figsize=(6, 4))
    if clustered:
        bins = range(2, max(clustered) + 2)
        ax.hist(clustered, bins=bins, color="#6baed6", edgecolor="white")
        ax.set_xlabel("cluster size (# nodes merged)")
        ax.set_ylabel("# clusters")
        ax.set_title(f"Cluster sizes ({len(clustered)} merged clusters)")
    else:
        ax.text(0.5, 0.5, "no nodes merged at this threshold",
                ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Cluster sizes")
    plt.tight_layout()
    _save("9_5_cluster_sizes")
    plt.show()


def _tag(d: dict) -> str:
    """Bracket prefix for a node: ``[SUBTYPE]`` if known, else ``[ntp]``."""
    sub = d.get("subtype")
    return f"[{sub.upper()}]" if sub else f"[{d.get('ntype', '?')[:3]}]"


def plot_top_frequent(g: nx.DiGraph, top_n: int = 15) -> None:
    top = sorted(g.nodes(data=True),
                 key=lambda kv: kv[1].get("frequency", 0), reverse=True)[:top_n]
    labels = [
        f"{_tag(d)} {d.get('label', '')[:55]}"
        + (f" x{d['cluster_size']}" if d.get("is_clustered") else "")
        for _, d in top
    ]
    freqs = [d.get("frequency", 0) for _, d in top]
    colors = [NTYPE_COLORS.get(d.get("ntype"), "#888") for _, d in top]
    fig, ax = plt.subplots(figsize=(9, 6))
    y = np.arange(len(labels))
    ax.barh(y, freqs, color=colors)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("frequency (path occurrences)")
    ax.set_title(f"Top-{top_n} most frequent nodes")
    plt.tight_layout()
    _save("9_6_top_frequent")
    plt.show()


# ---------- layered layout for incidents ----------

def chains_for(workflow_graphs: Iterable[tuple[str, dict]]) -> list[tuple[str, list[str]]]:
    """Per-workflow_graph ordered list of node-ids matching ``build_workflow_graph``."""
    out = []
    for name, wf in workflow_graphs:
        seq = []
        for path_item in wf.get("taxonomy", []):
            for kind, desc, _sub in _iter_steps(path_item):
                seq.append(f"{kind}_{_sanitise(desc)}")
        out.append((name, seq))
    return out


def build_cluster_remap(g_post: nx.DiGraph) -> dict[str, str]:
    """absorbed-id -> rep-id, read from ``cluster_members`` on each rep node."""
    remap = {}
    for rep_id, d in g_post.nodes(data=True):
        for member in d.get("cluster_members", []) or []:
            if member != rep_id:
                remap[member] = rep_id
    return remap


def _depth(graph: nx.DiGraph) -> dict[str, int]:
    """Topological-generation depth, robust to cycles.

    Clustering can merge nodes across chains in ways that create cycles
    (e.g. A: x->y->z, B: y->x  →  merged: x↔y). We strip a DFS-back-edge
    feedback set for layout only — the original graph is unchanged.
    """
    visited, on_stack, back_edges = set(), set(), set()

    def dfs(u):
        stack = [(u, iter(graph.successors(u)))]
        visited.add(u); on_stack.add(u)
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                on_stack.discard(node); stack.pop()
                continue
            if nxt in on_stack:
                back_edges.add((node, nxt))
            elif nxt not in visited:
                visited.add(nxt); on_stack.add(nxt)
                stack.append((nxt, iter(graph.successors(nxt))))

    for n in list(graph.nodes()):
        if n not in visited:
            dfs(n)

    h = graph.copy()
    h.remove_edges_from(back_edges)
    return {n: i for i, gen in enumerate(nx.topological_generations(h)) for n in gen}


def _layered_pos(graph: nx.DiGraph, chains, id_remap: dict[str, str]):
    """Lay out chains as parallel columns; shared nodes sit in the gutter.

    Per-chain y is sequence position (not topological depth), so each chain
    stays linear regardless of cross-chain merges. Shared nodes are placed
    in the gutter at the average sequence position of the chains they appear
    in — producing the X-bridge pattern when chains converge on a shared hub.
    """
    if not chains:
        return nx.spring_layout(graph, seed=42)

    n_chains = len(chains)
    col_x = {i: float(i) * 4.0 for i in range(n_chains)}
    gutter_x = (n_chains - 1) * 4.0 / 2.0

    chain_seqs: list[list[str]] = []
    for _, seq in chains:
        remapped: list[str] = []
        for nid in seq:
            r = id_remap.get(nid, nid)
            if r in graph and r not in remapped:
                remapped.append(r)
        chain_seqs.append(remapped)

    in_chains: dict[str, set[int]] = {}
    for ci, seq in enumerate(chain_seqs):
        for nid in seq:
            in_chains.setdefault(nid, set()).add(ci)

    pos: dict[str, tuple[float, float]] = {}
    for ci, seq in enumerate(chain_seqs):
        for y, nid in enumerate(seq):
            if nid in pos:
                continue
            if len(in_chains[nid]) == 1:
                pos[nid] = (col_x[ci], -float(y))
            else:
                ys = [chain_seqs[c].index(nid) for c in in_chains[nid] if nid in chain_seqs[c]]
                pos[nid] = (gutter_x, -sum(ys) / len(ys))

    for n in graph.nodes():
        if n not in pos:
            pos[n] = (gutter_x, 0.0)
    return pos


def _hier_pos(graph: nx.DiGraph) -> dict[str, tuple[float, float]]:
    """Sugiyama-style layered layout from cycle-broken topological depth.

    Nodes at the same depth spread evenly along x; depth increases downward.
    Handles the post-cluster case where merged chains may have cycles.
    """
    depth = _depth(graph)
    by_depth: dict[int, list[str]] = {}
    for n, d in depth.items():
        by_depth.setdefault(d, []).append(n)
    max_w = max(len(ns) for ns in by_depth.values()) or 1
    pos = {}
    for d, ns in by_depth.items():
        ns_sorted = sorted(ns)
        n = len(ns_sorted)
        for i, nid in enumerate(ns_sorted):
            x = (i - (n - 1) / 2) * (max_w / max(n, 1)) * 0.6
            pos[nid] = (x, -float(d))
    return pos


def _draw(ax, graph: nx.DiGraph, pos, title: str) -> None:
    colors = [NTYPE_COLORS.get(d.get("ntype"), "#888") for _, d in graph.nodes(data=True)]
    sizes = [400 + 60 * d.get("frequency", 1) for _, d in graph.nodes(data=True)]
    nx.draw_networkx_edges(graph, pos, ax=ax, alpha=0.5, arrows=True, arrowsize=12, width=1.0)
    nx.draw_networkx_nodes(graph, pos, ax=ax, node_color=colors, node_size=sizes,
                           alpha=0.9, linewidths=0)
    ax.set_title(f"{title}\n{graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    ax.set_axis_off()


def plot_layout_before_after(
    g_pre: nx.DiGraph,
    g_post: nx.DiGraph,
    workflow_graphs: list[tuple[str, dict]] | None = None,
    *,
    track: str = "incidents",
    max_nodes: int = 60,
) -> None:
    """Two-panel before/after layout. Layered chains for incidents, spring for spreadsheet."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 9))
    if track == "incidents" and workflow_graphs:
        chains = chains_for(workflow_graphs)
        _draw(axes[0], g_pre, _layered_pos(g_pre, chains, {}),
              "pre-cluster (disjoint chains)")
        _draw(axes[1], g_post, _layered_pos(g_post, chains, build_cluster_remap(g_post)),
              "post-cluster (merged nodes shared)")
    else:
        def _sub(graph: nx.DiGraph, k: int) -> nx.DiGraph:
            if graph.number_of_nodes() <= k:
                return graph
            kept = {n for n, _ in sorted(graph.nodes(data=True),
                                         key=lambda kv: kv[1].get("frequency", 0),
                                         reverse=True)[:k]}
            return graph.subgraph(kept).copy()
        h_pre, h_post = _sub(g_pre, max_nodes), _sub(g_post, max_nodes)
        pos_pre = nx.spring_layout(h_pre, seed=42,
                                   k=0.6 / max(1, np.sqrt(h_pre.number_of_nodes())))
        pos_post = nx.spring_layout(h_post, seed=42,
                                    k=0.6 / max(1, np.sqrt(h_post.number_of_nodes())))
        _draw(axes[0], h_pre, pos_pre, f"pre-cluster (top-{max_nodes})")
        _draw(axes[1], h_post, pos_post, f"post-cluster (top-{max_nodes})")

    legend_handles = [plt.Line2D([0], [0], marker="o", color="w",
                                 markerfacecolor=c, markersize=10, label=t)
                      for t, c in NTYPE_COLORS.items()]
    axes[1].legend(handles=legend_handles, loc="lower right", fontsize=8, frameon=False)
    plt.tight_layout()
    _save("9_7_layout_before_after")
    plt.show()


def plot_threshold_sweep(
    wf_docs: list,
    embedder,
    thresholds: Iterable[float] = (0.01, 0.05, 0.10, 0.20, 0.40),
    variants: Iterable[tuple[str, bool]] = (("Ours", True), ("Ours w/o Canonicalization", False)),
    title: str = "Reproduction of paper Figure 3 on the artifact's public dataset",
) -> dict[str, list[tuple[int, float]]]:
    """Sweep clustering threshold τ; plot node count + edge/node ratio per variant.

    Reproduces the shape of paper Figure 3. Returns the raw results dict so
    the caller can print or persist the numbers.
    """
    from graphmind.graph import build_workflow_graph
    from graphmind.clustering import cluster_graph

    thresholds = list(thresholds)
    results: dict[str, list[tuple[int, float]]] = {label: [] for label, _ in variants}
    for tau in thresholds:
        for label, do_canon in variants:
            g = build_workflow_graph(wf_docs)
            cluster_graph(g, embedder, distance_threshold=tau, canonicalize=do_canon)
            n, e = g.number_of_nodes(), g.number_of_edges()
            results[label].append((n, e / n if n else 0.0))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.5))
    for label, pts in results.items():
        ax1.plot(thresholds, [p[0] for p in pts], marker="o", label=label)
        ax2.plot(thresholds, [p[1] for p in pts], marker="o", label=label)
    ax1.set_xlabel("Clustering threshold τ"); ax1.set_ylabel("Number of nodes"); ax1.set_xscale("log")
    ax2.set_xlabel("Clustering threshold τ"); ax2.set_ylabel("Edge / node ratio"); ax2.set_xscale("log")
    ax1.legend(); ax2.legend()
    fig.suptitle(title)
    fig.tight_layout()
    plt.show()
    return results


__all__ = [
    "NTYPE_COLORS", "NTYPE_ORDER",
    "plot_domain_distribution", "plot_paths_per_workflow_graph",
    "plot_steps_per_incident", "plot_step_types_per_incident",
    "plot_size_before_after", "plot_ntype_distribution",
    "plot_cluster_sizes", "plot_top_frequent", "plot_layout_before_after",
    "plot_threshold_sweep",
    "chains_for", "build_cluster_remap",
]

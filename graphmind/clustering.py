"""Embedding-based agglomerative clustering of workflow_graph-graph nodes.

For each clusterable ntype, embed node labels, run cosine-distance
agglomerative clustering, pick the highest-frequency member as the
representative, sum frequencies into it, and remap edges to point at the
representative.

Operates in place on a ``networkx.DiGraph`` and accepts an ``Embedder``
Protocol so callers can plug in any embedding backend.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence

import networkx as nx
import numpy as np

from graphmind.canonicalize import canonicalize as _canonicalize
from graphmind.cluster_core import agglomerative_groups
from graphmind.interfaces import Embedder

DEFAULT_CLUSTERABLE_NTYPES: tuple[str, ...] = ("action", "observation", "resolution")


def cluster_graph(
    g: nx.DiGraph,
    embedder: Embedder,
    distance_threshold: float = 0.15,
    clusterable_ntypes: Sequence[str] = DEFAULT_CLUSTERABLE_NTYPES,
    canonicalize: bool = True,
) -> nx.DiGraph:
    """Cluster ``g`` in place and return the same (mutated) graph.

    When ``canonicalize=True`` (default), node labels are passed through the
    production Phase 1 regex mask (GUIDs, datetimes, IPs, hex hashes, etc.)
    before embedding — matches the paper's "Ours" variant in Figure 3.
    """
    id_remap: dict[str, str] = {}

    for ntype in clusterable_ntypes:
        members = [(nid, d) for nid, d in g.nodes(data=True) if d.get("ntype") == ntype]
        if len(members) < 2:
            continue

        ids = [nid for nid, _ in members]
        labels = [d.get("label", "") for _, d in members]
        freqs = [int(d.get("frequency", 1)) for _, d in members]

        embed_input = [_canonicalize(l) for l in labels] if canonicalize else labels
        X = np.asarray(embedder(embed_input))
        for group in agglomerative_groups(X, distance_threshold):
            if len(group) == 1:
                continue
            rep_local = max(group, key=lambda i: freqs[i])
            rep_id = ids[rep_local]
            g.nodes[rep_id]["frequency"] = sum(freqs[i] for i in group)
            g.nodes[rep_id]["is_clustered"] = True
            g.nodes[rep_id]["cluster_size"] = len(group)
            g.nodes[rep_id]["cluster_members"] = [ids[i] for i in group]
            for i in group:
                if i != rep_local:
                    id_remap[ids[i]] = rep_id

    if not id_remap:
        return g

    new_weights: dict[tuple[str, str], float] = defaultdict(float)
    for u, v, data in g.edges(data=True):
        nu = id_remap.get(u, u)
        nv = id_remap.get(v, v)
        if nu == nv:
            continue
        new_weights[(nu, nv)] += float(data.get("weight", 1.0))

    g.remove_nodes_from(list(id_remap.keys()))
    g.remove_edges_from(list(g.edges()))
    for (u, v), w in new_weights.items():
        if u in g and v in g:
            g.add_edge(u, v, weight=w)

    return g


__all__ = ["cluster_graph", "DEFAULT_CLUSTERABLE_NTYPES"]

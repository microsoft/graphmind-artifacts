"""Shared agglomerative-clustering primitive.

Both ``graphmind.clustering`` (Cloud KV, typed Node objects) and
``examples.spreadsheet.clustering`` (Excel workflow_graphs, ntype-string nodes)
implement the same paper-§3.3 loop:

    embed labels -> AgglomerativeClustering(cosine, average) -> per-group
    {pick representative, mark/remove absorbed, rewire edges}

The bucketing rule, representative-selection heuristic, and edge-rewire
semantics differ by domain, so each call site keeps its own; this module
holds just the algorithm core (the actual sklearn call + group assembly)
so the two implementations cannot drift apart.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np
from sklearn.cluster import AgglomerativeClustering


def agglomerative_groups(
    embeddings: np.ndarray,
    distance_threshold: float,
) -> list[list[int]]:
    """Run cosine + average-linkage clustering and return groups of indices.

    Each group is a list of row indices into ``embeddings`` that landed in
    the same cluster. Singletons are returned as 1-element groups. If fewer
    than 2 rows are supplied, each is returned as its own group (sklearn
    rejects n=1)."""
    n = len(embeddings)
    if n < 2:
        return [[i] for i in range(n)]
    labels = AgglomerativeClustering(
        n_clusters=None,
        metric="cosine",
        linkage="average",
        distance_threshold=distance_threshold,
    ).fit_predict(np.asarray(embeddings))
    by_label: dict[int, list[int]] = defaultdict(list)
    for i, lab in enumerate(labels):
        by_label[int(lab)].append(i)
    return list(by_label.values())


__all__ = ["agglomerative_groups"]

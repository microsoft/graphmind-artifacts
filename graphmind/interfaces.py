"""Pluggable backends for GraphMind."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class Embedder(Protocol):
    """Batch text embedder.

    Returns a 2-D float array of shape (len(texts), d). Output vectors should
    be L2-normalised if the consumer expects cosine similarity via dot product.
    """

    def __call__(self, texts: list[str]) -> np.ndarray: ...

    @property
    def dim(self) -> int: ...

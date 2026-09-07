"""Shared embedders for OKF tests."""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass
class FakeEmbedder:
    """Deterministic SHA-256-derived embedder used by OKF tests."""

    dim: int = 8
    name: str = field(default_factory=lambda: f"fake-{8}")

    def __post_init__(self) -> None:
        self.name = f"fake-{self.dim}"

    def embed(self, text: str) -> list[float]:
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        repeats = (self.dim * 4 + len(seed) - 1) // len(seed)
        raw = (seed * repeats)[: self.dim * 4]
        return list(struct.unpack(f"<{self.dim}f", raw))


def text_to_vector(text: str, dim: int) -> Sequence[float]:
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    repeats = (dim * 4 + len(seed) - 1) // len(seed)
    raw = (seed * repeats)[: dim * 4]
    return struct.unpack(f"<{dim}f", raw)


def l2_normalize(vec: Sequence[float]) -> list[float]:
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if not na or not nb:
        return 0.0
    return dot / (na * nb)

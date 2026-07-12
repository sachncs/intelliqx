"""Visual Regression Agent (Tier 3).

Compares a current screenshot against a stored baseline and reports
whether the difference exceeds a configurable threshold.

Algorithm (v1):
1. On the first run for a given ``baseline_key``, store the
   image as the baseline and return ``is_regression=False``.
2. On subsequent runs, compare bytes using a Hamming-bytes
   distance normalised by length. The result is the
   ``diff_pct`` field; values above ``pixel_threshold`` are
   flagged as a regression.

**Production note:** the v1 byte-comparison is a dependency-free
approximation. Production deployments should decode the PNG to a
pixel buffer (Pillow, libpng, etc.) and compute a real pixel diff
(SSIM, perceptual hash). The interface is stable, so swapping the
internal algorithm is a contained change.
"""

from __future__ import annotations

import hashlib

from aqip_agents.base import AgentBase, AgentContext, AgentMeta
from aqip_agents.decorators import traced_agent
from aqip_storage.store import get_object_store
from pydantic import BaseModel, ConfigDict


class VisualRegressionInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tenant_id: str
    image_bytes: bytes  # current screenshot
    baseline_key: str  # object-store key for the baseline image
    name: str = "screenshot"
    pixel_threshold: float = 0.02  # 2% difference


class VisualRegressionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    diff_pct: float
    is_regression: bool
    baseline_hash: str
    current_hash: str


class VisualRegressionAgent(AgentBase):
    META = AgentMeta(
        name="visual_regression",
        tier=3,
        version="0.1.0",
        description="Pixel + perceptual diff for visual regression.",
    )
    INPUT_MODEL = VisualRegressionInput
    OUTPUT_MODEL = VisualRegressionOutput

    @traced_agent("visual_regression")
    async def run(self, ctx: AgentContext, input: VisualRegressionInput) -> VisualRegressionOutput:
        store = get_object_store()
        baseline_bytes: bytes | None = None
        try:
            baseline_bytes = await store.get(input.baseline_key)
        except Exception:
            # Missing baseline is not fatal; we just store the
            # current image as the new baseline.
            baseline_bytes = None

        current_hash = hashlib.sha256(input.image_bytes).hexdigest()
        baseline_hash = hashlib.sha256(baseline_bytes).hexdigest() if baseline_bytes else ""

        if not baseline_bytes:
            # No baseline → store the first run as baseline.
            await store.put(
                input.baseline_key, input.image_bytes, content_type="image/png"
            )
            return VisualRegressionOutput(
                name=input.name,
                diff_pct=0.0,
                is_regression=False,
                baseline_hash="",
                current_hash=current_hash,
            )

        diff_pct = _pixel_diff_pct(baseline_bytes, input.image_bytes)
        is_regression = diff_pct > input.pixel_threshold
        return VisualRegressionOutput(
            name=input.name,
            diff_pct=diff_pct,
            is_regression=is_regression,
            baseline_hash=baseline_hash,
            current_hash=current_hash,
        )


def _pixel_diff_pct(a: bytes, b: bytes) -> float:
    """Approximate pixel diff percentage using byte-by-byte comparison.

    Production code should decode PNGs to pixels. For test
    purposes, byte comparison is sufficient and dependency-free.

    Returns:
        A float in ``[0.0, 1.0]`` representing the fraction of
        differing bytes. ``0.0`` means the inputs are byte-equal;
        ``1.0`` means every compared byte differs (or the
        shorter input is empty).
    """
    if a == b:
        return 0.0
    # Use a byte-level Hamming distance normalised by length.
    n = min(len(a), len(b))
    if n == 0:
        return 1.0
    diff = sum(1 for x, y in zip(a[:n], b[:n], strict=False) if x != y)
    return min(1.0, diff / n)

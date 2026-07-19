"""Local-backend parity tests for intelliqx-llm.

Asserts the deterministic fallback shapes for the local-only LLM backends
the platform keeps: :class:`FakeLLMClient` and
:class:`MiniMaxLLMClient` (when its API key is missing).
"""

import os

import pytest
from intelliqx_llm.client import CompletionRequest, FakeLLMClient
from intelliqx_llm.minimax import MiniMaxLLMClient


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fake_deterministic():
    c = FakeLLMClient()
    r1 = await c.complete(
        CompletionRequest(model="m", messages=[{"role": "user", "content": "hello"}])
    )
    r2 = await c.complete(
        CompletionRequest(model="m", messages=[{"role": "user", "content": "hello"}])
    )
    assert r1.content == r2.content
    assert r1.content.startswith("[fake:")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_minimax_fallback_deterministic():
    saved = os.environ.pop("MINIMAX_API_KEY", None)
    try:
        client = MiniMaxLLMClient(api_key="")
        r = await client.complete(
            CompletionRequest(model="m", messages=[{"role": "user", "content": "hello"}])
        )
        assert r.content.startswith("[minimax-fallback:")
    finally:
        if saved is not None:
            os.environ["MINIMAX_API_KEY"] = saved


@pytest.mark.unit
@pytest.mark.asyncio
async def test_minimax_embed_dim():
    saved = os.environ.pop("MINIMAX_API_KEY", None)
    try:
        client = MiniMaxLLMClient(api_key="", embed_dim=256)
        vecs = await client.embed(["hello"], model="m")
        assert len(vecs) == 1
        assert len(vecs[0]) == 256
    finally:
        if saved is not None:
            os.environ["MINIMAX_API_KEY"] = saved

"""Tests for aqip-llm."""

import pytest
from intelliqx_llm.client import (
    CompletionRequest,
    FakeLLMClient,
    get_llm_client,
    set_llm_client,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fake_completion_deterministic():
    c = FakeLLMClient()
    set_llm_client(c)
    r1 = await c.complete(CompletionRequest(model="m", messages=[{"role": "user", "content": "hello"}]))
    r2 = await c.complete(CompletionRequest(model="m", messages=[{"role": "user", "content": "hello"}]))
    assert r1.content == r2.content


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fake_registered_marker():
    c = FakeLLMClient()
    c.register_response("hi", "world")
    r = await c.complete(CompletionRequest(model="m", messages=[{"role": "user", "content": "say hi"}]))
    assert r.content == "world"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fake_usage_accounted():
    c = FakeLLMClient()
    r = await c.complete(
        CompletionRequest(
            model="m", messages=[{"role": "user", "content": "hello world"}]
        )
    )
    assert r.usage.prompt_tokens >= 1
    assert r.usage.completion_tokens >= 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fake_embed_dim():
    c = FakeLLMClient(dim=16)
    vecs = await c.embed(["hello"], model="m")
    assert len(vecs) == 1
    assert len(vecs[0]) == 16


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fake_embed_deterministic():
    c = FakeLLMClient(dim=16)
    v1 = await c.embed(["hello"], model="m")
    v2 = await c.embed(["hello"], model="m")
    assert v1 == v2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_call_log():
    c = FakeLLMClient()
    req = CompletionRequest(model="m", messages=[{"role": "user", "content": "x"}])
    await c.complete(req)
    assert len(c.call_log) == 1


@pytest.mark.unit
def test_get_llm_client_default_is_fake():
    c = get_llm_client()
    assert isinstance(c, FakeLLMClient)


@pytest.mark.unit
def test_completion_request_validation():
    req = CompletionRequest(model="m", messages=[])
    assert req.temperature == 0.0
    assert req.max_tokens == 1024
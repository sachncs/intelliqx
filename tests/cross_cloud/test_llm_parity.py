"""Cross-cloud parity tests for intelliqx-llm."""

import pytest
from intelliqx_llm.aws import BedrockLLMClient
from intelliqx_llm.client import CompletionRequest
from intelliqx_llm.gcp import VertexLLMClient
from intelliqx_llm.modal import VLLMModalLLMClient


@pytest.mark.cross_cloud
@pytest.mark.asyncio
async def test_bedrock_fallback_deterministic():
    """Without AWS creds, Bedrock client falls back to deterministic mock."""
    client = BedrockLLMClient(region="us-east-1")
    r1 = await client.complete(
        CompletionRequest(model="m", messages=[{"role": "user", "content": "hello"}])
    )
    r2 = await client.complete(
        CompletionRequest(model="m", messages=[{"role": "user", "content": "hello"}])
    )
    assert r1.content == r2.content
    assert r1.content.startswith("[bedrock-fallback:")


@pytest.mark.cross_cloud
@pytest.mark.asyncio
async def test_vertex_fallback_deterministic():
    client = VertexLLMClient(project_id="intelliqx-test", region="us-central1")
    r1 = await client.complete(
        CompletionRequest(model="m", messages=[{"role": "user", "content": "hello"}])
    )
    r2 = await client.complete(
        CompletionRequest(model="m", messages=[{"role": "user", "content": "hello"}])
    )
    assert r1.content == r2.content
    assert r1.content.startswith("[vertex-fallback:")


@pytest.mark.cross_cloud
@pytest.mark.asyncio
async def test_vllm_fallback_deterministic():
    client = VLLMModalLLMClient(endpoint_url=None)
    r = await client.complete(
        CompletionRequest(model="m", messages=[{"role": "user", "content": "hello"}])
    )
    assert r.content.startswith("[vllm-fallback:")


@pytest.mark.cross_cloud
@pytest.mark.asyncio
async def test_bedrock_embed_dim():
    client = BedrockLLMClient()
    vecs = await client.embed(["hello"], model="m")
    assert len(vecs) == 1
    assert len(vecs[0]) == 1024  # Titan embedding dim


@pytest.mark.cross_cloud
@pytest.mark.asyncio
async def test_vertex_embed_dim():
    client = VertexLLMClient()
    vecs = await client.embed(["hello"], model="m")
    assert len(vecs) == 1
    assert len(vecs[0]) == 768


@pytest.mark.cross_cloud
@pytest.mark.asyncio
async def test_vllm_embed_dim():
    client = VLLMModalLLMClient()
    vecs = await client.embed(["hello"], model="m")
    assert len(vecs) == 1
    assert len(vecs[0]) == 768


@pytest.mark.cross_cloud
def test_cross_cloud_different_fallback_prefixes():
    """Each cloud has a distinct fallback prefix — proves adapter identity."""
    a = BedrockLLMClient()
    g = VertexLLMClient()
    m = VLLMModalLLMClient()
    assert a.DEFAULT_MODEL != g.DEFAULT_MODEL != m.model

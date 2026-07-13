"""Tests for the MiniMax LLM adapter (libs/intelliqx-llm)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from intelliqx_llm.client import CompletionRequest, LLMUsage, deterministic_embedding
from intelliqx_llm.minimax import MiniMaxLLMClient


def _request(content: str = "hello") -> CompletionRequest:
    return CompletionRequest(
        model="minimax/MiniMax-M2.1", messages=[{"role": "user", "content": content}]
    )


@pytest.mark.unit
def test_minimax_init_without_api_key_is_unavailable():
    """Without MINIMAX_API_KEY the adapter must report unavailable."""
    with patch.dict("os.environ", {}, clear=True):
        client = MiniMaxLLMClient(api_key="")
    assert client.api_key == ""
    # No key -> _try_init returns False -> __available is False.
    assert client._MiniMaxLLMClient__available is False  # type: ignore[attr-defined]


@pytest.mark.unit
def test_minimax_init_with_api_key_is_available():
    """A populated API key (real or fake) makes the adapter available."""
    client = MiniMaxLLMClient(api_key="sk-fake-test")
    assert client.api_key == "sk-fake-test"
    assert client._MiniMaxLLMClient__available is True  # type: ignore[attr-defined]


@pytest.mark.unit
def test_minimax_defaults_match_docs():
    """Pin the documented defaults so they can't drift silently."""
    client = MiniMaxLLMClient(api_key="sk-test")
    assert client.model == "minimax/MiniMax-M2.1"
    assert client.embed_model == "minimax/text-embedding-01"
    assert client.embed_dim == 1536
    assert client.api_base == "https://api.minimax.io/v1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_minimax_complete_fallback_when_unavailable():
    """A missing API key must produce a deterministic fallback response."""
    with patch.dict("os.environ", {}, clear=True):
        client = MiniMaxLLMClient(api_key="")
    response = await client.complete(_request("hello world"))
    assert response.content.startswith("[minimax-fallback:")
    assert response.model == "minimax/MiniMax-M2.1"
    assert response.usage.prompt_tokens == len(["hello", "world"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_minimax_complete_calls_litellm_acompletion():
    """When the adapter is available, it must call litellm.acompletion."""

    class _FakeMessage:
        def __init__(self) -> None:
            self.content = "hi from MiniMax"

    class _FakeChoice:
        def __init__(self) -> None:
            self.message = _FakeMessage()

    class _FakeUsage:
        prompt_tokens = 7
        completion_tokens = 3

    class _FakeResponse:
        def __init__(self) -> None:
            self.choices = [_FakeChoice()]
            self.usage = _FakeUsage()

    fake_litellm = AsyncMock()
    fake_litellm.acompletion = AsyncMock(return_value=_FakeResponse())
    fake_litellm.aembedding = AsyncMock()

    client = MiniMaxLLMClient(api_key="sk-test")
    # Bypass _try_init so the test does not depend on the installed
    # litellm version; inject our own client explicitly.
    client._MiniMaxLLMClient__client = fake_litellm  # type: ignore[attr-defined]
    client._MiniMaxLLMClient__available = True  # type: ignore[attr-defined]

    response = await client.complete(_request("hi"))

    fake_litellm.acompletion.assert_awaited_once()
    kwargs = fake_litellm.acompletion.await_args.kwargs
    assert kwargs["model"] == "minimax/MiniMax-M2.1"
    assert kwargs["api_key"] == "sk-test"
    assert kwargs["api_base"] == "https://api.minimax.io/v1"
    assert response.content == "hi from MiniMax"
    assert response.usage == LLMUsage(prompt_tokens=7, completion_tokens=3)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_minimax_complete_falls_back_on_litellm_error():
    """A litellm exception should not propagate — the fallback fires."""

    fake_litellm = AsyncMock()
    fake_litellm.acompletion = AsyncMock(side_effect=RuntimeError("rate limited"))
    fake_litellm.aembedding = AsyncMock()

    client = MiniMaxLLMClient(api_key="sk-test")
    client._MiniMaxLLMClient__client = fake_litellm  # type: ignore[attr-defined]
    client._MiniMaxLLMClient__available = True  # type: ignore[attr-defined]

    response = await client.complete(_request("hello"))
    assert response.content.startswith("[minimax-fallback:")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_minimax_embed_fallback_when_unavailable():
    """A missing API key must produce deterministic embeddings."""
    with patch.dict("os.environ", {}, clear=True):
        client = MiniMaxLLMClient(api_key="", embed_dim=64)
    out = await client.embed(["alpha", "beta"])
    assert len(out) == 2
    assert all(len(v) == 64 for v in out)
    # Deterministic embedding is hash-based, so the same input
    # always produces the same vector.
    assert out == deterministic_embedding(["alpha", "beta"], 64)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_minimax_embed_calls_litellm_aembedding():
    """When available, the adapter must call litellm.aembedding."""

    class _FakeItem:
        def __init__(self) -> None:
            self.embedding = [0.1, 0.2, 0.3]

    class _FakeResponse:
        def __init__(self) -> None:
            self.data = [_FakeItem(), _FakeItem()]

    fake_litellm = AsyncMock()
    fake_litellm.acompletion = AsyncMock()
    fake_litellm.aembedding = AsyncMock(return_value=_FakeResponse())

    client = MiniMaxLLMClient(api_key="sk-test")
    client._MiniMaxLLMClient__client = fake_litellm  # type: ignore[attr-defined]
    client._MiniMaxLLMClient__available = True  # type: ignore[attr-defined]

    out = await client.embed(["x", "y"], model="minimax/text-embedding-01")

    fake_litellm.aembedding.assert_awaited_once()
    kwargs = fake_litellm.aembedding.await_args.kwargs
    assert kwargs["model"] == "minimax/text-embedding-01"
    assert kwargs["input"] == ["x", "y"]
    assert out == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_minimax_embed_falls_back_on_litellm_error():
    """An embed failure must produce deterministic vectors, not raise."""
    fake_litellm = AsyncMock()
    fake_litellm.aembedding = AsyncMock(side_effect=RuntimeError("upstream down"))
    fake_litellm.acompletion = AsyncMock()

    client = MiniMaxLLMClient(api_key="sk-test", embed_dim=8)
    client._MiniMaxLLMClient__client = fake_litellm  # type: ignore[attr-defined]
    client._MiniMaxLLMClient__available = True  # type: ignore[attr-defined]

    out = await client.embed(["foo"])
    assert len(out) == 1
    assert len(out[0]) == 8
    assert out == deterministic_embedding(["foo"], 8)


@pytest.mark.unit
def test_minimax_factory_wires_minimax_backend(monkeypatch: pytest.MonkeyPatch):
    """``get_llm_client`` must return a MiniMaxLLMClient when configured."""
    from intelliqx_llm import client as client_mod

    monkeypatch.setattr(client_mod, "_SINGLETON", None)
    monkeypatch.setenv("INTELLIQX_LLM_BACKEND", "minimax")
    monkeypatch.setenv("MINIMAX_API_KEY", "sk-factory-test")

    backend = client_mod.get_llm_client()
    assert isinstance(backend, MiniMaxLLMClient)
    assert backend.api_key == "sk-factory-test"

    # Reset so the next test starts clean.
    monkeypatch.setattr(client_mod, "_SINGLETON", None)


@pytest.mark.unit
def test_minimax_factory_unknown_backend_raises(monkeypatch: pytest.MonkeyPatch):
    """An unknown backend name must raise a clear RuntimeError."""
    from intelliqx_llm import client as client_mod

    monkeypatch.setattr(client_mod, "_SINGLETON", None)
    monkeypatch.setenv("INTELLIQX_LLM_BACKEND", "not-a-real-backend")

    with pytest.raises(RuntimeError, match="not-a-real-backend"):
        client_mod.get_llm_client()

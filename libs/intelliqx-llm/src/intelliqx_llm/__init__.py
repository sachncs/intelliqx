"""LLM client abstraction for IntelliqX.

The platform talks to LLMs through a small async interface
(:class:`intelliqx_llm.client.LLMClient`) with two operations: ``complete``
for chat and ``embed`` for vectorisation. The reference implementation
(:class:`intelliqx_llm.client.FakeLLMClient`) is deterministic and
dependency-free, so tests can exercise the full agent stack without
network or vendor credentials.

The optional MiniMax adapter is provided by
:class:`intelliqx_llm.minimax.MiniMaxLLMClient` (litellm-routed). Custom
backends can be installed via
:func:`intelliqx_llm.client.register_llm_backend`; the platform looks
up the backend under the ``INTELLIQX_LLM_BACKEND`` env var (``"fake"``
by default).
"""

from intelliqx_llm.client import (
    CompletionRequest,
    CompletionResponse,
    FakeLLMClient,
    LLMClient,
    LLMUsage,
    deterministic_embedding,
    get_llm_client,
)
from intelliqx_llm.minimax import MiniMaxLLMClient

__all__ = [
    "CompletionRequest",
    "CompletionResponse",
    "FakeLLMClient",
    "LLMClient",
    "LLMUsage",
    "MiniMaxLLMClient",
    "deterministic_embedding",
    "get_llm_client",
]

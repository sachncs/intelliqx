"""LLM client abstraction for IntelliqX.

The platform talks to LLMs through a small async interface
(:class:`intelliqx_llm.client.LLMClient`) with two operations: ``complete``
for chat and ``embed`` for vectorisation. The reference implementation
(:class:`intelliqx_llm.client.FakeLLMClient`) is deterministic and
dependency-free, so tests can exercise the full agent stack without
network or vendor credentials.

Cloud adapters live next to this package:

* :class:`intelliqx_llm.aws.BedrockLLMClient` — AWS Bedrock (Claude 3.5
  Sonnet by default).
* :class:`intelliqx_llm.gcp.VertexLLMClient` — Vertex AI (Gemini 2.0 Flash
  by default).
* :class:`intelliqx_llm.modal.VLLMModalLLMClient` — vLLM on Modal
  (Qwen 2.5 default, OpenAI-compatible HTTP).
* :class:`intelliqx_llm.minimax.MiniMaxLLMClient` — MiniMax via
  `litellm <https://docs.litellm.ai/docs/providers/minimax>`__
  (MiniMax-M2.1 default chat, text-embedding-01 default embed).

Selection happens via the ``INTELLIQX_LLM_BACKEND`` env var
(``"fake"`` default; cloud values are recognised but require
credentials at runtime).
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

__all__ = [
    "CompletionRequest",
    "CompletionResponse",
    "FakeLLMClient",
    "LLMClient",
    "LLMUsage",
    "deterministic_embedding",
    "get_llm_client",
]

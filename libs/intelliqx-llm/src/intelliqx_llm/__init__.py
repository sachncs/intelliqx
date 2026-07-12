"""LLM client abstraction for AQIP.

The platform talks to LLMs through a small async interface
(:class:`aqip_llm.client.LLMClient`) with two operations: ``complete``
for chat and ``embed`` for vectorisation. The reference implementation
(:class:`aqip_llm.client.FakeLLMClient`) is deterministic and
dependency-free, so tests can exercise the full agent stack without
network or vendor credentials.

Cloud adapters live next to this package:

* :class:`aqip_llm.aws.BedrockLLMClient` — AWS Bedrock (Claude 3.5
  Sonnet by default).
* :class:`aqip_llm.gcp.VertexLLMClient` — Vertex AI (Gemini 2.0 Flash
  by default).
* :class:`aqip_llm.modal.VLLMModalLLMClient` — vLLM on Modal
  (Qwen 2.5 default, OpenAI-compatible HTTP).

Selection happens via the ``AQIP_LLM_BACKEND`` env var (``"fake"``
default; the cloud values are recognised but require credentials at
runtime).
"""

from intelliqx_llm.client import (
    CompletionRequest,
    CompletionResponse,
    FakeLLMClient,
    LLMClient,
    LLMUsage,
    get_llm_client,
)

__all__ = [
    "CompletionRequest",
    "CompletionResponse",
    "FakeLLMClient",
    "LLMClient",
    "LLMUsage",
    "get_llm_client",
]

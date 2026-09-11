# ADR-0012: Pydantic-AI based LLM abstraction

- **Status**: Accepted
- **Context**: The platform needs a single LLM client surface that
  every agent consumes, while keeping the implementation pluggable.
  The current contract is a single OpenAI-compatible chat path
  exposed through Pydantic AI's `OpenAIChatModel`, with an
  `OpenAIHTTPEmbeddings` adapter for the OKF vector path.
- **Decision**: Standardise on
  [Pydantic AI](https://ai.pydantic.dev/) as the provider-agnostic
  runtime. The `intelliqx_ai.runtime` module (`build_agent` and
  `build_embedder`) is the single construction point. The runtime
  reads `INTELLIQX_MODEL`, `INTELLIQX_OPENAI_BASE_URL`, and
  `INTELLIQX_OPENAI_API_KEY` from the environment to build the
  chat model; the embedding model reads `INTELLIQX_EMBEDDING_MODEL`
  and `INTELLIQX_EMBEDDING_DIM`. Any OpenAI-compatible endpoint
  (OpenAI, Anthropic via proxy, Ollama, vLLM, etc.) works without
  adapter code.
- **Consequences**:
  - Pros: one set of retry / token-count / streaming semantics
    across every provider because Pydantic AI delegates to the
    OpenAI SDK; tests inject a `TestModel` or `FunctionModel` so
    the entire pipeline runs offline.
  - Pros: the chat path and the embed path share one base URL
    and one API key, reducing the env-var surface area.
  - Cons: Pydantic AI is still pre-1.0; minor version bumps may
    rename fields on the underlying SDK models.
  - Cons: providers with non-OpenAI error semantics need a thin
    adapter if strict per-error handling is required.

## Selection

`INTELLIQX_MODEL` selects the chat model (e.g. `openai:gpt-4o-mini`).
`INTELLIQX_EMBEDDING_MODEL` selects the embedding model (e.g.
`text-embedding-3-small`). The chat path defaults to
`https://api.openai.com/v1`; any OpenAI-compatible endpoint can be
configured via `INTELLIQX_OPENAI_BASE_URL`. There is no
`INTELLIQX_LLM_BACKEND` selector — the platform is a single
OpenAI-compatible chat path.

## Smoke CLI

Use the in-process `agents.register_all()` followed by
`intelliqx_compute.runtime.get_compute_runtime().invoke(...)` to
exercise the same code paths as production. The CLI example in
`README.md` (under Quick Start) is the recommended way to verify
credentials before running the rest of the platform.

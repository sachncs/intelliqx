# ADR-0012: litellm-based LLM abstraction

- **Status**: Accepted
- **Context**: The platform needs a single LLM client surface that
  every agent consumes, while keeping the implementation pluggable
  across providers. Four LLM backends are supported today:
  - **AWS Bedrock** — Claude 3.5 Sonnet chat, Titan embeddings.
  - **GCP Vertex AI** — Gemini 2.0 Flash chat, text-embedding-005.
  - **vLLM on Modal** — OpenAI-compatible HTTP at
    `INTELLIQX_VLLM_URL`.
  - **MiniMax** — MiniMax-M2.1 chat, text-embedding-01 via litellm.
- **Decision**: Standardise on
  [`litellm`](https://docs.litellm.ai/) as the provider-agnostic
  client SDK. The package is already a transitive dependency
  (pinned in `libs/intelliqx-llm/pyproject.toml`) so the cloud
  adapters and the MiniMax adapter share the same call surface.
  The `intelliqx_llm.client.LLMClient` interface stays the platform
  contract; the per-cloud adapters wrap `litellm.acompletion` /
  `litellm.aembedding` behind it.
- **Consequences**:
  - Pros: one set of retry / token-count / streaming semantics
    across every provider. The MiniMax adapter became a ~150-line
    module instead of a hand-rolled HTTP client.
  - Pros: every adapter can fall back to the deterministic helpers
    in `intelliqx_llm.client.deterministic_embedding` /
    `_fallback_complete` when the SDK is missing or credentials
    are absent, so the rest of the platform keeps running in
    CI on a laptop with no cloud keys.
  - Cons: litellm is a large dependency (it pulls in tiktoken,
    tokenizers, jinja2, openai, etc.). That cost is amortised
    across the 4 backends; if a future project only needs a
    single provider, litellm would be overkill.
  - Cons: litellm's error taxonomy is heterogeneous across
    providers; the adapter normalises by catching `Exception`
    broadly and falling back. That is permissive but it means
    transient errors look the same as fatal ones. Production
    deployments that need strict per-error handling should
    subclass the adapter and override `complete` / `embed`.

## Selection

`INTELLIQX_LLM_BACKEND` selects the adapter. The default is
`fake` (deterministic, no network). The supported values are
documented in `libs/intelliqx-llm/src/intelliqx_llm/client.py`
(`get_llm_client`).

## Smoke CLI

`intelliqx-llm-smoke` is a console-script entry point installed by
`intelliqx-llm`. It runs a one-shot `complete()` (or `embed()` with
`--embed`) against the configured backend and prints the response
plus latency, with exit code 0 on success and 1 on any failure.
This is the recommended way to verify credentials before running
the rest of the platform.

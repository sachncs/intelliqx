"""Pydantic AI runtime for IntelliqX agents.

Single construction point for the OpenAI-compatible model. Tests
pass :class:`pydantic_ai.models.test.TestModel` or
:class:`pydantic_ai.models.function.FunctionModel` via
:func:`build_agent`; production reads ``INTELLIQX_OPENAI_BASE_URL``,
``INTELLIQX_OPENAI_API_KEY``, and ``INTELLIQX_MODEL`` from the
environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, cast

from pydantic_ai import Agent
from pydantic_ai.embeddings import EmbeddingModel
from pydantic_ai.models import Model

DEFAULT_MODEL = "openai:gpt-4o-mini"
BASE_URL_ENV = "INTELLIQX_OPENAI_BASE_URL"
API_KEY_ENV = "INTELLIQX_OPENAI_API_KEY"
MODEL_ENV = "INTELLIQX_MODEL"
EMBEDDING_DIM_ENV = "INTELLIQX_EMBEDDING_DIM"
DEFAULT_EMBEDDING_DIM = 1536


@dataclass(frozen=True)
class AgentConfig:
    """Configuration for constructing a Pydantic AI :class:`Agent`.

    Attributes:
        model: Either a Pydantic AI ``Model`` instance or a model name
            string. When ``None`` the runtime reads ``INTELLIQX_MODEL``
            (or :data:`DEFAULT_MODEL`) and builds an ``OpenAIChatModel``
            from the ``INTELLIQX_OPENAI_BASE_URL`` /
            ``INTELLIQX_OPENAI_API_KEY`` environment variables. Tests
            pass a ``TestModel``/``FunctionModel`` to bypass the network.
        model_settings: Per-agent overrides for temperature/tokens.
        tools: List of ``@agent.tool``-style callables.
        deps_type: Dependency class for the Pydantic AI run context.
    """

    model: Model | str | None = None
    model_settings: dict[str, Any] | None = None
    tools: list[Any] | None = None
    deps_type: Any = None


def _read_api_key() -> str:
    """Return the configured API key, failing fast if it is missing."""
    key = os.environ.get(API_KEY_ENV)
    if not key:
        raise RuntimeError(
            f"{API_KEY_ENV} is required to build a Pydantic AI agent. "
            "Set the environment variable or pass a TestModel in tests."
        )
    return key


def _openai_chat_model(model_name: str) -> Model:
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    return OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(base_url=os.environ.get(BASE_URL_ENV), api_key=_read_api_key()),
    )


class OpenAIHTTPEmbeddings(EmbeddingModel):
    """OpenAI-compatible HTTP embedding model for the OKF vector path.

    Calls ``POST {base_url}/v1/embeddings`` synchronously via
    ``httpx.Client`` so it works from the OKF's sync ``Embedder.embed``
    contract. The same model name and base URL are used as the chat
    path, so any OpenAI-compatible provider works.

    Attributes:
        model_name: The embedding model name passed in the request.
        base_url: The OpenAI-compatible root (no trailing slash).
    """

    def __init__(self, model_name: str, *, base_url: str | None = None) -> None:
        self._model_name = model_name
        self._base_url = (base_url or os.environ.get(BASE_URL_ENV) or "").rstrip("/")
        self._api_key = _read_api_key()
        # Lazy client so import-time does not require the SDK at test
        # boundaries that override the embedder.
        self._client: Any = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def max_input_tokens(self) -> int:
        return 8192

    @property
    def system(self) -> str:
        return "openai"

    async def embed(
        self,
        inputs: str | list[str],
        *,
        input_type: str = "document",
        settings: Any = None,
    ) -> Any:
        from pydantic_ai.embeddings.result import EmbeddingResult

        texts = [inputs] if isinstance(inputs, str) else list(inputs)
        vectors = self._client_post("embeddings", {"model": self._model_name, "input": texts})
        return EmbeddingResult(
            embeddings=[list(v) for v in vectors],
            model=self._model_name,
            usage={"prompt_tokens": 0, "completion_tokens": 0},
        )

    def count_tokens(self, text: str) -> int:
        return max(1, len(text.split()))

    def prepare_embed(
        self,
        inputs: str | list[str],
        settings: Any = None,
    ) -> tuple[list[str], Any]:
        texts = [inputs] if isinstance(inputs, str) else list(inputs)
        return texts, settings

    def _client_post(self, path: str, body: dict[str, Any]) -> list[Any]:
        if not self._base_url:
            raise RuntimeError(
                f"{BASE_URL_ENV} is required to call the OpenAI embeddings endpoint."
            )
        import httpx

        if self._client is None:
            self._client = httpx.Client(
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=30.0,
            )
        response = self._client.post(f"{self._base_url}/{path}", json=body)
        response.raise_for_status()
        return [item["embedding"] for item in response.json()["data"]]


def build_embedder(
    *, model_name: str | None = None, dim: int | None = None
) -> EmbeddingModel:
    """Build the production Pydaxis-AI embedding model for the OKF vector path.

    Args:
        model_name: Override for the embedding model name. Defaults to
            ``text-embedding-3-small`` which most OpenAI-compatible
            providers support.
        dim: Optional explicit dimension (Pydaxis-AI ``OpenAIHTTPEmbeddings``
            infers it from the response).

    Raises:
        RuntimeError: when ``INTELLIQX_OPENAI_API_KEY`` is not set.
    """
    del dim  # Pydaxis-AI's HTTP-based embedder infers the dimension.
    name = model_name or os.environ.get("INTELLIQX_EMBEDDING_MODEL", "text-embedding-3-small")
    return OpenAIHTTPEmbeddings(name)


def _parse_int(raw: str | None, default: int) -> int:
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"expected integer, got {raw!r}") from exc


def build_agent(
    *, name: str, output_type: Any, instructions: str, agent_config: AgentConfig | None = None
) -> Agent[Any, Any]:
    """Build a Pydantic AI :class:`Agent` for a single role.

    Args:
        name: Agent display name (Pydantic AI uses this for tracing).
        output_type: Pydantic model class or ``str`` for free-form
            text output.
        instructions: System instructions for the model.
        agent_config: Optional runtime configuration. When ``None`` the
            helper reads the OpenAI-compatible model from environment
            variables.
    """
    config = agent_config or AgentConfig()
    model: Model | str = (
        config.model if config.model is not None else os.environ.get(MODEL_ENV, DEFAULT_MODEL)
    )
    if isinstance(model, str):
        model = _openai_chat_model(model)
    return Agent[Any, Any](
        name=name,
        model=model,
        output_type=output_type,
        instructions=instructions,
        deps_type=config.deps_type,
        tools=config.tools or [],
        model_settings=cast(Any, config.model_settings),
    )


__all__ = [
    "API_KEY_ENV",
    "BASE_URL_ENV",
    "DEFAULT_EMBEDDING_DIM",
    "DEFAULT_MODEL",
    "EMBEDDING_DIM_ENV",
    "MODEL_ENV",
    "AgentConfig",
    "EmbeddingModel",
    "build_agent",
    "build_embedder",
]

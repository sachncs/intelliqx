"""Pydantic AI runtime for IntelliqX agents.

Single construction point for the OpenAI-compatible model, the
embedder, and ``usage_limits``. Tests pass ``TestModel`` /
``FunctionModel`` to :func:`build_runtime`; production reads
``INTELLIQX_OPENAI_BASE_URL``, ``INTELLIQX_OPENAI_API_KEY``, and
``INTELLIQX_MODEL`` from the environment.
"""

from __future__ import annotations

import os
from typing import Any, cast

from pydantic_ai import Agent
from pydantic_ai.models import Model

DEFAULT_MODEL = "openai:gpt-4o-mini"
BASE_URL_ENV = "INTELLIQX_OPENAI_BASE_URL"
API_KEY_ENV = "INTELLIQX_OPENAI_API_KEY"
MODEL_ENV = "INTELLIQX_MODEL"


def build_runtime(
    *,
    name: str,
    output_type: Any,
    instructions: str,
    deps_type: Any = None,
    tools: list[Any] | None = None,
    model: Model | str = "",
    model_settings: dict[str, Any] | None = None,
) -> Agent[Any, Any]:
    """Build a Pydantic AI :class:`Agent` with shared runtime defaults.

    Args:
        name: Agent display name (Pydantic AI uses this for tracing).
        output_type: Structured output type or list of types.
        instructions: System instructions for the model.
        deps_type: Dependency class for the run context (Pydantic AI
            injects this on ``run_sync``/``run``).
        tools: List of ``@agent.tool``-style callables.
        model: Explicit Pydantic AI ``Model`` instance; when empty the
            helper builds an ``OpenAIChatModel`` from the env vars.
        model_settings: Per-agent overrides for temperature/tokens.
    """
    resolved: Model | str = model
    if not resolved:
        resolved = OpenAIChatModel(
            os.environ.get(MODEL_ENV, DEFAULT_MODEL),
            provider=OpenAIProvider(
                base_url=os.environ.get(BASE_URL_ENV),
                api_key=os.environ.get(API_KEY_ENV, "sk-not-set"),
            ),
        )
    return Agent[Any, Any](  # type: ignore[call-overload]
        name=name,
        model=cast(Any, resolved),
        output_type=output_type,
        instructions=instructions,
        deps_type=deps_type,
        tools=tools or [],
        model_settings=model_settings or {"temperature": 0.0},
    )


# Local imports deferred so unit tests that monkeypatch
# ``pydantic_ai.models.openai`` see the same symbols.
def OpenAIChatModel(model_name: str, *, provider: Any) -> Model:
    from pydantic_ai.models.openai import OpenAIChatModel as _Model

    return _Model(model_name, provider=provider)


def OpenAIProvider(*, base_url: str | None, api_key: str) -> Any:
    from pydantic_ai.providers.openai import OpenAIProvider as _Provider

    return _Provider(base_url=base_url, api_key=api_key)


__all__ = [
    "API_KEY_ENV",
    "BASE_URL_ENV",
    "DEFAULT_MODEL",
    "MODEL_ENV",
    "OpenAIProvider",
    "build_runtime",
]

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
from pydantic_ai.models import Model

DEFAULT_MODEL = "openai:gpt-4o-mini"
BASE_URL_ENV = "INTELLIQX_OPENAI_BASE_URL"
API_KEY_ENV = "INTELLIQX_OPENAI_API_KEY"
MODEL_ENV = "INTELLIQX_MODEL"


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
    "DEFAULT_MODEL",
    "MODEL_ENV",
    "AgentConfig",
    "build_agent",
]

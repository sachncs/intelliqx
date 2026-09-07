"""Tests for the Pydantic AI agent roles.

Every role is exercised offline through :class:`FunctionModel` so
CI never needs network access. Each test asserts that the configured
agent has the expected output type and a deterministic call returns
a non-null result.
"""

from __future__ import annotations

import asyncio
import inspect
import os
from typing import Any

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.function import AgentInfo, FunctionModel

# Required by the production runtime; tests never exercise the network
# path because every test overrides the model with a ``FunctionModel``.
os.environ.setdefault("INTELLIQX_OPENAI_API_KEY", "test-key")
os.environ.setdefault("INTELLIQX_OPENAI_BASE_URL", "http://localhost")

from agents.ai import roles


def _run(name: str) -> roles.AgentRole:
    return next(role for role in roles.build_roles() if role.name == name)


def _is_text(agent: Agent[Any, Any]) -> bool:
    return agent._output_type is str  # type: ignore[attr-defined]


def _text_response(_messages: list[Any], _info: AgentInfo) -> Any:
    from pydantic_ai.messages import ModelResponse, TextPart

    return ModelResponse(parts=[TextPart("ok")])


def _structured_response(agent: Agent[Any, Any]):
    def _make(_messages: list[Any], _info: AgentInfo) -> Any:
        from pydantic_ai.messages import ModelResponse, TextPart

        schema = agent._output_type  # type: ignore[attr-defined]
        if not inspect.isclass(schema):
            return ModelResponse(parts=[TextPart("ok")])
        try:
            instance = schema.model_validate(
                {
                    name: _default(schema.model_fields[name].annotation, name)
                    for name in schema.model_fields
                }
            )
        except Exception:
            instance = schema.model_validate(
                {name: f"sample_{name}" for name in schema.model_fields}
            )
        return ModelResponse(parts=[TextPart(instance.model_dump_json())])

    return _make


def _default(annotation: Any, name: str) -> Any:
    origin = getattr(annotation, "__origin__", None)
    if origin is list or origin is tuple:
        return []
    if origin in (dict,):
        return {}
    if annotation is int:
        return 1
    if annotation is float:
        return 0.5
    if annotation is bool:
        return True
    return f"sample_{name}"


def _invoke(role_name: str, prompt: str = "ping") -> object:
    role = _run(role_name)
    agent = role.factory()
    if _is_text(agent):
        model: Any = FunctionModel(_text_response)
    else:
        model = FunctionModel(_structured_response(agent))
    with agent.override(model=model):
        result = asyncio.run(agent.run(prompt))
    return result.output


def test_every_role_registers_with_unique_name() -> None:
    names = [r.name for r in roles.build_roles()]
    assert len(names) == len(set(names))
    assert "planner" in names
    assert "release_readiness" in names


@pytest.mark.parametrize("role", [r.name for r in roles.build_roles()])
def test_role_runs_with_test_model(role: str) -> None:
    role = _run(role)
    agent = role.factory()
    model: Any = FunctionModel(_text_response if _is_text(agent) else _structured_response(agent))
    with agent.override(model=model):
        out = asyncio.run(agent.run("ping"))
    assert out is not None


def test_planner_returns_structured_plan() -> None:
    from pydantic_ai.models.test import TestModel

    role = _run("planner")
    test_model = TestModel(custom_output_args={"goal_id": "g1", "steps": ["design", "ship"]})
    agent = role.factory()
    with agent.override(model=test_model):
        plan = asyncio.run(agent.run("plan please")).output
    assert plan.goal_id == "g1"
    assert plan.steps == ["design", "ship"]


def test_release_readiness_decision_shape() -> None:
    from pydantic_ai.models.test import TestModel

    role = _run("release_readiness")
    test_model = TestModel(
        custom_output_args={"recommendation": "go", "confidence": 0.9, "outcome": "passed"}
    )
    agent = role.factory()
    with agent.override(model=test_model):
        decision = asyncio.run(agent.run("ready?")).output
    assert decision.recommendation == "go"
    assert decision.outcome == "passed"


def test_role_has_no_adk_or_agentbase_reference() -> None:
    """Roles are pure Pydantic AI; no legacy framework remains."""
    from agents.ai import roles as module

    source = inspect.getsource(module)
    for forbidden in ("AgentBase", "google.adk", "adk_agents", "META"):
        assert forbidden not in source

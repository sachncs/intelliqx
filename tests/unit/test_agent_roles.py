"""Tests for the Pydantic AI agent roles.

Every role is exercised offline through :class:`TestModel` (string
output) or :func:`FunctionModel` (structured output) so CI never
needs network access. Each test asserts that the configured agent
has the expected output type and a deterministic call returns a
non-null result.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.function import AgentInfo, FunctionModel

from agents.ai import _roles


def _run(name: str) -> _roles.build:
    return next(role for role in _roles.build() if role.name == name)


def _is_text(agent: Agent[Any, Any]) -> bool:
    return agent._output_type is str


def _text_response(_messages: list[Any], _info: AgentInfo) -> Any:
    from pydantic_ai.messages import ModelResponse, TextPart

    return ModelResponse(parts=[TextPart("ok")])


def _structured_response(agent: Agent[Any, Any]):
    def _make(_messages: list[Any], _info: AgentInfo) -> Any:
        import types

        from pydantic_ai.messages import ModelResponse, TextPart

        schema = agent._output_type
        if isinstance(schema, (list, types.GenericAlias)):
            return ModelResponse(parts=[TextPart("[]")])
        fields: dict[str, Any] = {}
        for name, field_info in schema.model_fields.items():
            annotation = field_info.annotation
            if annotation is int:
                fields[name] = 1
            elif annotation is float:
                fields[name] = 0.5
            elif annotation is bool:
                fields[name] = True
            elif getattr(annotation, "__origin__", None) in (list, tuple):
                fields[name] = []
            else:
                fields[name] = f"sample_{name}"
        instance = schema.model_validate(fields)
        return ModelResponse(parts=[TextPart(instance.model_dump_json())])

    return _make


def _invoke(role_name: str, prompt: str = "ping") -> object:
    role = _run(role_name)
    agent = role.builder()
    if _is_text(agent):
        model: Any = FunctionModel(_text_response)
    else:
        model = FunctionModel(_structured_response(agent))
    with agent.override(model=model):
        result = asyncio.run(agent.run(prompt))
    return result.output


def test_every_role_registers_with_unique_name() -> None:
    names = [r.name for r in _roles.build()]
    assert len(names) == len(set(names))
    assert "planner" in names
    assert "release_readiness" in names


@pytest.mark.parametrize("role", [r.name for r in _roles.build()])
def test_role_runs_with_test_model(role: str) -> None:
    out = _invoke(role)
    assert out is not None


def test_planner_returns_structured_plan() -> None:
    role = _run("planner")
    agent = role.builder()
    with agent.override(model=FunctionModel(_structured_response(agent))):
        plan = asyncio.run(agent.run("plan please")).output
    assert plan.goal_id.startswith("sample_goal_id")
    assert isinstance(plan.steps, list)


def test_release_readiness_decision_shape() -> None:
    role = _run("release_readiness")
    agent = role.builder()
    with agent.override(model=FunctionModel(_structured_response(agent))):
        decision = asyncio.run(agent.run("ready?")).output
    assert decision.recommendation.startswith("sample_")
    assert isinstance(decision.confidence, float)


def test_role_has_no_adk_or_agentbase_reference() -> None:
    """Roles are pure Pydantic AI; no legacy framework remains."""
    import inspect

    from agents.ai import _roles as module

    source = inspect.getsource(module)
    for forbidden in ("AgentBase", "google.adk", "adk_agents", "META"):
        assert forbidden not in source

"""Tests for intelliqx-agents."""

import pytest
from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_agents.registry import get_agent_registry, register_agent, reset_agent_registry
from intelliqx_core.models import AgentCategory
from pydantic import BaseModel


class _Input(BaseModel):
    x: int


class _Output(BaseModel):
    y: int


class _DemoAgent(AgentBase[_Input, _Output]):
    META = AgentMeta(name="demo", category=AgentCategory.COORDINATION, description="demos")
    INPUT_MODEL = _Input
    OUTPUT_MODEL = _Output

    @traced_agent("demo")
    async def run(self, ctx: AgentContext, input: _Input) -> _Output:
        return _Output(y=input.x * 2)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_invoke():
    agent = _DemoAgent()
    from intelliqx_compute.runtime import InvocationRequest

    req = InvocationRequest(
        agent_name="demo", input={"x": 5}, tenant_id="t1", metadata={"run_id": "r1"}
    )
    out = await agent.invoke(req)
    assert out == {"y": 10}


@pytest.mark.unit
def test_agent_registry_register_and_create():
    reset_agent_registry()
    register_agent("demo", lambda: _DemoAgent(), meta=_DemoAgent.META)
    reg = get_agent_registry()
    assert "demo" in reg.list()
    inst = reg.create("demo")
    assert isinstance(inst, _DemoAgent)


@pytest.mark.unit
def test_agent_registry_create_missing():
    reset_agent_registry()
    reg = get_agent_registry()
    with pytest.raises(KeyError):
        reg.create("nope")


@pytest.mark.unit
def test_agent_registry_get_meta():
    reset_agent_registry()
    register_agent("demo", lambda: _DemoAgent(), meta=_DemoAgent.META)
    reg = get_agent_registry()
    assert reg.get_meta("demo").name == "demo"


@pytest.mark.unit
def test_agent_capability():
    cap = _DemoAgent.capability()
    assert cap.name == "demo"


@pytest.mark.unit
def test_agent_meta_fields():
    m = AgentMeta(name="a", category=AgentCategory.INTELLIGENCE, description="d")
    assert m.category == AgentCategory.INTELLIGENCE
    assert m.version == "0.1.0"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_requires_input_output_models():
    class _BadAgent(AgentBase):
        META = AgentMeta(name="bad", category=AgentCategory.COORDINATION)

        async def run(self, ctx, input):
            return {}

    bad = _BadAgent()
    from intelliqx_compute.runtime import InvocationRequest

    with pytest.raises(RuntimeError):
        await bad.invoke(InvocationRequest(agent_name="bad", input={}, tenant_id="t1"))

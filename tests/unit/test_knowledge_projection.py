"""Tests for AST→OKF graph projection and transient :class:`RunContext`."""

from __future__ import annotations

from pathlib import Path

from intelliqx_agents.base import RunContext, bind_run, current_run
from intelliqx_compute.runtime import InvocationRequest, get_compute_runtime
from intelliqx_graph.operations import ingest_graph, parse_repository
from intelliqx_okf import Index

from tests.okf._embed import FakeEmbedder

DIM = 8


def test_ingest_graph_writes_one_concept_per_entity(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "a.py").write_text("def foo(): return 1\nclass Bar: pass\n")
    parsed = parse_repository(str(tmp_path))
    assert parsed["errors"] == []
    assert parsed["entities"]

    index = Index(tmp_path / "k.db", embed=FakeEmbedder(DIM))
    written = ingest_graph(parsed["entities"], index=index)
    assert written == len(parsed["entities"])

    hits = index.read("foo", top=5)
    assert any(h.concept.concept_id.endswith("::foo") for h in hits)
    hits = index.read("Bar", top=5)
    assert any(h.concept.concept_id.endswith("::Bar") for h in hits)
    index.close()


def test_run_context_is_bound_per_invocation() -> None:
    runtime = get_compute_runtime()

    async def handler(req: InvocationRequest) -> dict[str, object]:
        rc = current_run()
        assert rc is not None
        return {"run_id": rc.run_id, "plan_id": rc.plan_id, "tenant_id": rc.tenant_id}

    runtime.register("runctx_test", handler)

    async def run() -> None:
        req = InvocationRequest(
            agent_name="runctx_test",
            input={},
            tenant_id="t1",
            metadata={"run_id": "abc", "plan_id": "p", "node_id": "n"},
        )
        out = await runtime.invoke(req)
        assert out.status == "ok"
        assert out.output["run_id"] == "abc"
        assert out.output["plan_id"] == "p"
        assert out.output["tenant_id"] == "t1"

    import asyncio

    asyncio.run(run())


def test_bind_run_is_reeentrant() -> None:
    rc1 = RunContext(run_id="r1", plan_id="p", tenant_id="t1", agent_name="x")
    rc2 = RunContext(run_id="r2", plan_id="p", tenant_id="t1", agent_name="y")
    with bind_run(rc1):
        assert current_run() is rc1
        with bind_run(rc2):
            assert current_run() is rc2
        assert current_run() is rc1
    assert current_run() is None

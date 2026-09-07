"""Loguru-backed structured logging tests.

Captures rendered lines through the public ``configure_logging``
``sink`` callback — no private-helper imports. Covers JSON shape,
bound fields, level filter, idempotent reconfigure, async context
isolation, recursive + text-pattern redaction, dropped
prompt/message/body fields, exception capture without local-variable
leakage, OTel trace-id injection, parent-child span inheritance, and
human (non-JSON) output.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from intelliqx_observability.logging import (
    bind_context,
    configure_logging,
    get_logger,
    reset_logging,
)
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.trace import TracerProvider


def make_capture(level: str = "DEBUG", **kwargs: Any) -> list[str]:
    """Attach a public sink callback and return its line buffer."""
    lines: list[str] = []
    configure_logging(level=level, enqueue=False, sink=lines.append, **kwargs)
    return lines


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_logging()
    yield
    reset_logging()


@pytest.fixture(scope="session")
def _otel_provider() -> TracerProvider:
    provider = TracerProvider()
    otel_trace.set_tracer_provider(provider)
    return provider


@pytest.mark.unit
def test_json_shape_includes_static_fields() -> None:
    lines = make_capture(service="svc", environment="prod", component="compute")
    get_logger("demo").info("hello", k=1)
    rec = json.loads(lines[0])
    assert rec["service"] == "svc" and rec["environment"] == "prod"
    assert rec["component"] == "compute" and rec["level"] == "INFO"
    assert rec["message"] == "hello" and "ts" in rec
    assert rec["extra"]["logger"] == "demo" and rec["extra"]["k"] == 1


@pytest.mark.unit
def test_level_filter() -> None:
    lines = make_capture(level="WARNING")
    log = get_logger("lvl")
    log.info("dropped")
    log.warning("kept")
    assert [json.loads(ln)["message"] for ln in lines] == ["kept"]


@pytest.mark.unit
def test_get_logger_binds_static_extra() -> None:
    lines = make_capture()
    get_logger("bound", component="rag").info("x")
    assert json.loads(lines[0])["extra"]["component"] == "rag"


@pytest.mark.unit
def test_bind_chains_to_loguru_logger() -> None:
    lines = make_capture()
    get_logger("chain").bind(plan_id="p1").info("hi")
    assert json.loads(lines[0])["extra"]["plan_id"] == "p1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_context_isolation() -> None:
    lines = make_capture()
    log = get_logger("ctx")

    async def runner(rid: str) -> None:
        with bind_context(run_id=rid, plan_id="p", node_id="n", agent="a"):
            log.info(f"in-{rid}")
        log.info(f"out-{rid}")

    await asyncio.gather(runner("A"), runner("B"))
    by_msg = {json.loads(ln)["message"]: json.loads(ln) for ln in lines}
    assert sorted(by_msg) == ["in-A", "in-B", "out-A", "out-B"]
    assert by_msg["in-A"]["extra"]["run_id"] == "A"
    assert "run_id" not in by_msg["out-A"]["extra"]
    for msg in ("in-A", "in-B"):
        assert by_msg[msg]["extra"]["agent"] == "a"


@pytest.mark.unit
def test_recursive_redaction_keys() -> None:
    lines = make_capture()
    get_logger("r").info(
        "creds",
        Authorization="Bearer xyz",
        secrets={
            "api_key": "abc",
            "nested": {"password": "hunter2", "database_password": "deeper"},
        },
        tokens=[{"token": "eyJabc"}, {"refresh_token": "r1"}],
    )
    flat = json.dumps(json.loads(lines[0])["extra"])
    assert "hunter2" not in flat and "deeper" not in flat and "eyJabc" not in flat
    assert "[REDACTED]" in flat


@pytest.mark.unit
def test_redaction_drops_prompt_and_body_fields() -> None:
    lines = make_capture()
    get_logger("d").info(
        "sensitive",
        prompt="secret",
        messages=[{"role": "user", "content": "private"}],
        body="raw body text",
        tenant_id="t1",
    )
    extra = json.loads(lines[0])["extra"]
    assert "prompt" not in extra and "messages" not in extra
    assert "body" not in extra and extra["tenant_id"] == "t1"


@pytest.mark.unit
def test_text_pattern_redaction() -> None:
    lines = make_capture()
    log = get_logger("p")
    log.info("Authorization: Bearer ghp_abcdefghijklmnopqrstuv")
    log.info("api_key=abcdef12345abcdef")
    log.info("token=sk-abcdefghijklmnopqrstuv")
    r1, r2, r3 = (json.loads(ln)["message"] for ln in lines)
    assert "ghp_abcdef" not in r1 and "Bearer [REDACTED]" in r1
    assert "abcdef12345" not in r2 and "abcdefghijklmnopqrstuv" not in r3


@pytest.mark.unit
def test_exception_does_not_leak_locals() -> None:
    lines = make_capture()
    log = get_logger("exc")

    class _Boom(RuntimeError):
        pass

    try:
        secret = "hunter2-private"
        raise _Boom(f"local_secret={secret}")
    except _Boom:
        log.exception("caught")

    record = json.loads(lines[0])
    flat = json.dumps(record)
    assert "hunter2-private" not in flat
    assert "_Boom" in flat
    assert "Traceback" in record["exception"]["traceback"]


@pytest.mark.unit
def test_otel_trace_injection(_otel_provider: None) -> None:
    lines = make_capture()
    tracer = otel_trace.get_tracer("test")
    with tracer.start_as_current_span("root") as span:
        want_t = otel_trace.format_trace_id(span.get_span_context().trace_id)
        want_s = otel_trace.format_span_id(span.get_span_context().span_id)
        get_logger("t").info("inside")
    extra = json.loads(lines[0])["extra"]
    assert extra["trace_id"] == want_t and extra["span_id"] == want_s


@pytest.mark.unit
def test_parent_child_spans_share_trace(_otel_provider: None) -> None:
    lines = make_capture()
    log = get_logger("nest")
    tracer = otel_trace.get_tracer("test")
    with tracer.start_as_current_span("parent"):
        log.info("parent.log")
        p_t = json.loads(lines[0])["extra"]["trace_id"]
        p_s = json.loads(lines[0])["extra"]["span_id"]
        with tracer.start_as_current_span("child"):
            log.info("child.log")
            c_t = json.loads(lines[1])["extra"]["trace_id"]
            c_s = json.loads(lines[1])["extra"]["span_id"]
    assert p_t == c_t and p_s != c_s


@pytest.mark.unit
def test_no_duplicate_sinks_after_reconfigure() -> None:
    make_capture()
    make_capture()
    lines = make_capture()
    log = get_logger("dup")
    log.info("once")
    log.info("twice")
    log.info("thrice")
    assert len(lines) == 3


@pytest.mark.unit
def test_human_rendering_skips_json() -> None:
    lines = make_capture(json_logs=False)
    get_logger("pretty").info("human-friendly", x=1)
    out = lines[0]
    assert "human-friendly" in out and "{" not in out.split("\n")[0]


@pytest.mark.unit
def test_idempotent_service_override() -> None:
    configure_logging(level="INFO", json_logs=True, enqueue=False, service="x")
    configure_logging(level="INFO", json_logs=True, enqueue=False, service="y")
    lines: list[str] = []
    configure_logging(level="INFO", enqueue=False, sink=lines.append)
    get_logger("i").info("post")
    rec = json.loads(lines[0])
    assert rec["service"] == "y"

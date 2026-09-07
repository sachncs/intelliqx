"""Loguru-backed structured logging.

Public surface: :func:`configure_logging`, :func:`reset_logging`,
:func:`get_logger`, :func:`bind_context`. JSON outside TTY; recursive
sensitive-key redaction; ``Bearer`` / token-shape / ``key=val``
scrubbing; ``prompt`` / message / body fields dropped; OTel
``trace_id`` / ``span_id`` injected; sync writes by default; sink
callback receives one rendered string per record.
"""

from __future__ import annotations

import json
import os
import re
import sys
import traceback
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from typing import Any

from loguru import logger as _loguru

_REDACTED = "[REDACTED]"

_REDACT_KEYS = frozenset(
    {
        "authorization",
        "bearer",
        "api_key",
        "apikey",
        "api_token",
        "api-token",
        "token",
        "access_token",
        "refresh_token",
        "cookie",
        "cookies",
        "set-cookie",
        "password",
        "passwords",
        "passwd",
        "pwd",
        "secret",
        "credential",
        "credentials",
        "client_secret",
        "private",
    }
)
_DROP_KEYS = frozenset(
    {
        "prompt",
        "system_prompt",
        "messages",
        "model_input",
        "model_output",
        "completion",
        "source_body",
        "raw_body",
        "body",
        "tool_input",
    }
)

_SECRET_PATTERN = re.compile(
    r"(?i)(?P<bearer_auth>authorization\s*:\s*bearer\s+[A-Za-z0-9._\-+/=]+)"
    r"|(?P<auth>authorization\s*:\s*[A-Za-z0-9._\-+/=]+)"
    r"|(?P<bearer>\bbearer\s+[A-Za-z0-9._\-+/=]+)"
    r"|(?P<sk>\bsk-[A-Za-z0-9]{16,})"
    r"|(?P<ghp>\bghp_[A-Za-z0-9]{20,})"
    r"|(?P<slack>\bxox[abpr]-[A-Za-z0-9-]{10,})"
    r"|(?P<pkey>-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+PRIVATE KEY-----)"
    r"|(?P<kv>\b(?:[a-z0-9]+_)*(api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password|credential)"
    r"(?:_[a-z0-9]+)*\s*[=:]\s*[A-Za-z0-9._\-+/=]{1,200})"
)


def _scrub_text(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        g = m.lastgroup
        if g == "bearer_auth":
            return "Authorization: Bearer " + _REDACTED
        if g == "auth":
            return "Authorization: " + _REDACTED
        if g == "bearer":
            return "Bearer " + _REDACTED
        if g == "kv":
            return re.split(r"[=:]", m.group(0), maxsplit=1)[0] + "=" + _REDACTED
        return _REDACTED

    return _SECRET_PATTERN.sub(repl, text)


def _sensitive_key(key: Any) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
    return normalized in _REDACT_KEYS or any(
        normalized.endswith(f"_{candidate}") for candidate in _REDACT_KEYS
    )


def _scrub_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        out: dict[Any, Any] = {}
        for k, v in value.items():
            low = str(k).lower()
            if low in _DROP_KEYS:
                continue
            out[k] = _REDACTED if _sensitive_key(k) else _scrub_value(v)
        return out
    if isinstance(value, (list, tuple)):
        items = [_scrub_value(v) for v in value]
        return type(value)(items) if isinstance(value, tuple) else items
    if isinstance(value, str):
        return _scrub_text(value)
    return value


SERVICE: str = "intelliqx"
ENVIRONMENT: str = "development"
COMPONENT: str = "core"
_CONFIGURED = False


def _inject_otel(record: dict[str, Any]) -> None:
    if "trace_id" in record["extra"]:
        return
    try:
        from opentelemetry import trace as _otel
    except Exception:
        return
    ctx = _otel.get_current_span().get_span_context()
    if not getattr(ctx, "is_valid", False):
        return
    record["extra"]["trace_id"] = _otel.format_trace_id(ctx.trace_id)
    record["extra"]["span_id"] = _otel.format_span_id(ctx.span_id)


def _process(record: dict[str, Any]) -> None:
    extra = record.get("extra") or {}
    record["extra"] = _scrub_value(extra) if isinstance(extra, dict) else {}
    msg = record.get("message")
    if isinstance(msg, str):
        record["message"] = _scrub_text(msg)
    _inject_otel(record)


def _render_json(record: dict[str, Any]) -> str:
    payload: dict[str, Any] = {
        "ts": record["time"].isoformat(),
        "level": record["level"].name,
        "message": record["message"],
        "service": SERVICE,
        "environment": ENVIRONMENT,
        "component": COMPONENT,
        "logger": record.get("name"),
        "extra": record.get("extra") or {},
    }
    if (ex := record.get("exception")) and getattr(ex, "type", None):
        rendered = "".join(traceback.format_exception(ex.type, ex.value, ex.traceback))
        payload["exception"] = {"type": ex.type.__name__, "traceback": _scrub_text(rendered)}
    return json.dumps(payload, default=str, separators=(",", ":"))


def _render_pretty(record: dict[str, Any]) -> str:
    head = (
        f"{record['time'].isoformat()} | {record['level'].name:<8} | "
        f"{record.get('name') or SERVICE}: {record['message']}"
    )
    if extra := record.get("extra") or {}:
        head += " " + " ".join(f"{k}={v!r}" for k, v in extra.items())
    if (ex := record.get("exception")) and getattr(ex, "type", None):
        rendered = "".join(traceback.format_exception(ex.type, ex.value, ex.traceback))
        head += f"\n{_scrub_text(rendered).rstrip()}"
    return head


def _resolve_json(json_logs: bool | None) -> bool:
    if json_logs is not None:
        return json_logs
    env = os.environ.get("INTELLIQX_LOGS_JSON", "")
    if env == "1":
        return True
    if env == "0":
        return False
    return not sys.stderr.isatty()


def configure_logging(
    level: str = "INFO",
    json_logs: bool | None = None,
    *,
    service: str | None = None,
    environment: str | None = None,
    component: str | None = None,
    enqueue: bool = False,
    sink: Callable[[str], None] | None = None,
) -> None:
    """Install one sink on Loguru (idempotent)."""
    global SERVICE, ENVIRONMENT, COMPONENT, _CONFIGURED
    if service is not None:
        SERVICE = service
    if environment is not None:
        ENVIRONMENT = environment
    elif "INTELLIQX_ENV" in os.environ:
        ENVIRONMENT = os.environ["INTELLIQX_ENV"]
    if component is not None:
        COMPONENT = component
    _loguru.remove()
    use_json = _resolve_json(json_logs)

    def _emit(message: Any) -> None:
        record = dict(message.record)
        _process(record)
        line = _render_json(record) if use_json else _render_pretty(record)
        if sink is not None:
            sink(line)
        else:
            sys.stderr.write(line + "\n")
            sys.stderr.flush()

    _loguru.add(
        _emit,
        level=level.upper(),
        format="{message}",
        enqueue=enqueue,
        backtrace=False,
        diagnose=False,
    )
    _CONFIGURED = True


def reset_logging() -> None:
    """Remove every Loguru sink (test helper)."""
    global _CONFIGURED
    _loguru.remove()
    _CONFIGURED = False


def get_logger(name: str | None = None, **extra: Any):
    """Return a Loguru bound logger."""
    if not _CONFIGURED:
        configure_logging()
    return _loguru.bind(logger=name, **extra)


@contextmanager
def bind_context(**fields: Any):
    """Async-safe context binding using Loguru's contextualize."""
    with _loguru.contextualize(**fields):
        yield


__all__ = ["bind_context", "configure_logging", "get_logger", "reset_logging"]

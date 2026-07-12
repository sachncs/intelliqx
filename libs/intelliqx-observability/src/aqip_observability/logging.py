"""Structured logging for AQIP.

The platform uses ``structlog`` because it gives us JSON output in
production and pretty console output in development from the same code
path, with per-request fields (``tenant_id``, ``run_id``) injected via
``structlog.contextvars``.

Configuration is opt-in: import ``get_logger`` and the underlying
``structlog`` library is initialised on first use. Production
deployments should call :func:`configure_logging` once at startup to
pin the log level and JSON mode.
"""

from __future__ import annotations

import logging
import os
import sys

import structlog


def configure_logging(level: str = "INFO", json_logs: bool | None = None) -> None:
    """Configure structlog and the stdlib logging bridge.

    Args:
        level: Log level for both structlog and the stdlib bridge.
            One of ``"DEBUG"``, ``"INFO"``, ``"WARNING"``, ``"ERROR"``,
            ``"CRITICAL"`` (case-insensitive). Unknown values fall
            back to ``INFO``.
        json_logs: If ``True``, emit JSON log lines (production).
            If ``False``, emit pretty colored output (dev). If
            ``None`` (default), read the ``AQIP_LOGS_JSON`` env var:
            ``"1"`` enables JSON, anything else uses pretty output.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    if json_logs is None:
        json_logs = os.environ.get("AQIP_LOGS_JSON", "0") == "1"
    # Processor order matters: each entry is a transformation that
    # receives the event dict produced by earlier processors.
    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if json_logs:
        # JSON output for log aggregators (CloudWatch, Stackdriver, etc.).
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Pretty console output for human-readable development logs.
        processors.append(structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    # Mirror the level on the stdlib logger so libraries that log via
    # the stdlib ``logging`` module respect the same threshold.
    logging.basicConfig(level=log_level)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog bound logger.

    Args:
        name: Optional logger name (typically ``__name__`` of the
            calling module). Used to namespace log records.

    Returns:
        A structlog logger that can be used as
        ``log.info("msg", key=value)``.
    """
    return structlog.get_logger(name)

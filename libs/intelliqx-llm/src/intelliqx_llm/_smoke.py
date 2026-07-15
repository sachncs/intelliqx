"""Smoke test CLI for the LLM client.

Quick way to verify that the configured LLM backend is reachable
and that the platform's request/response contract is honoured.

Examples:

    # Fake backend (default — no network required)
    intelliqx-llm-smoke
    intelliqx-llm-smoke --prompt "Explain pytest fixtures in one sentence."

    # MiniMax via litellm (requires MINIMAX_API_KEY)
    INTELLIQX_LLM_BACKEND=minimax MINIMAX_API_KEY=sk-... \\
        intelliqx-llm-smoke --prompt "Hello from MiniMax!"

    # AWS Bedrock
    INTELLIQX_LLM_BACKEND=bedrock intelliqx-llm-smoke

The CLI prints the raw response content plus a one-line
per-call latency report. A non-zero exit code is returned when
the configured backend raises an exception that the adapter
cannot catch.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from typing import Any

from intelliqx_llm.client import CompletionRequest, get_llm_client


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="intelliqx-llm-smoke",
        description=(
            "Smoke test the configured INTELLIQX_LLM_BACKEND. " "Exits 0 on success, 1 on failure."
        ),
    )
    parser.add_argument(
        "--prompt",
        default="In one sentence, what does this LLM backend do well?",
        help="The prompt to send. Defaults to a generic capability question.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override the chat model name (e.g. minimax/MiniMax-M2-lightning).",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=256, help="Maximum tokens to request. Default 256."
    )
    parser.add_argument(
        "--embed",
        action="store_true",
        help="Run an embed() smoke test instead of a complete() smoke test.",
    )
    parser.add_argument(
        "--show-env",
        action="store_true",
        help="Print the active INTELLIQX_LLM_BACKEND, model, and dim before running.",
    )
    return parser.parse_args(argv)


def print_env(client: Any, args: argparse.Namespace) -> None:
    backend = os.environ.get("INTELLIQX_LLM_BACKEND", "fake")
    model = args.model or getattr(client, "model", None) or getattr(client, "DEFAULT_MODEL", "?")
    embed_model = getattr(client, "embed_model", None) or "?"
    dim = getattr(client, "embed_dim", getattr(client, "dim", "?"))
    available = getattr(client, "available", None)
    if available is None:
        available = "<not-applicable>"
    print(
        f"backend={backend}  model={model}  embed_model={embed_model}  "
        f"embed_dim={dim}  available={available}",
        flush=True,
    )


async def build_client(args: argparse.Namespace) -> tuple[Any, int]:
    """Resolve the configured LLM client.

    Returns ``(client, exit_code)`` so callers can forward the
    factory's RuntimeError as a normal CLI failure instead of a
    traceback.
    """
    try:
        return get_llm_client(), 0
    except Exception as exc:
        print(f"failed to build LLM client: {type(exc).__name__}: {exc}", file=sys.stderr)
        return None, 1


async def run_complete(args: argparse.Namespace) -> int:
    client, rc = await build_client(args)
    if rc != 0:
        return rc
    if args.show_env:
        print_env(client, args)
    request = CompletionRequest(
        model=args.model or "auto",
        messages=[{"role": "user", "content": args.prompt}],
        max_tokens=args.max_tokens,
    )
    start = time.monotonic()
    try:
        response = await client.complete(request)
    except Exception as exc:
        print(f"complete() raised {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    duration_ms = int((time.monotonic() - start) * 1000)
    print("--- response ---", flush=True)
    print(response.content, flush=True)
    print("--- meta ---", flush=True)
    print(
        f"model={response.model}  finish_reason={response.finish_reason}  "
        f"prompt_tokens={response.usage.prompt_tokens}  "
        f"completion_tokens={response.usage.completion_tokens}  "
        f"duration_ms={duration_ms}",
        flush=True,
    )
    return 0


async def run_embed(args: argparse.Namespace) -> int:
    client, rc = await build_client(args)
    if rc != 0:
        return rc
    if args.show_env:
        print_env(client, args)
    start = time.monotonic()
    try:
        vectors = await client.embed([args.prompt], model=args.model or "auto")
    except Exception as exc:
        print(f"embed() raised {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    duration_ms = int((time.monotonic() - start) * 1000)
    print("--- embed ---", flush=True)
    print(
        f"count={len(vectors)}  dim={len(vectors[0]) if vectors else 0}  duration_ms={duration_ms}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    runner = run_embed if args.embed else run_complete
    return asyncio.run(runner(args))


if __name__ == "__main__":
    sys.exit(main())

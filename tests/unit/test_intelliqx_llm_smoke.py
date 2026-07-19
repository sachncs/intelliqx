"""Tests for the intelliqx-llm-smoke CLI entry point."""

from __future__ import annotations

import subprocess
import sys

import pytest
from intelliqx_llm._smoke import main, parse_args
from intelliqx_llm.client import FakeLLMClient, reset_llm_client, set_llm_client


@pytest.fixture(autouse=True)
def reset_singleton_fixture():
    """Each test starts with no cached client so the backend env var wins."""
    reset_llm_client()
    yield
    reset_llm_client()


def testparse_args_defaults():
    args = parse_args([])
    assert args.prompt.startswith("In one sentence")
    assert args.max_tokens == 256
    assert args.embed is False
    assert args.show_env is False
    assert args.model is None


def testparse_args_embed():
    args = parse_args(["--embed", "--max-tokens", "64"])
    assert args.embed is True
    assert args.max_tokens == 64


def testparse_args_prompt_override():
    args = parse_args(["--prompt", "Hi", "--model", "minimax/MiniMax-M2-lightning"])
    assert args.prompt == "Hi"
    assert args.model == "minimax/MiniMax-M2-lightning"


def test_main_complete_smoke(monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setenv("INTELLIQX_LLM_BACKEND", "fake")

    # The fake client returns a hash-derived placeholder, not the
    # input echo, so we register a marker on the global fake so the
    # smoke CLI emits a deterministic, assertable response.
    fake = FakeLLMClient()
    fake.register_response("smoke-test", "smoke-ok")
    set_llm_client(fake)

    rc = main(["--prompt", "smoke-test"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "smoke-ok" in err
    assert "--- response ---" in err
    assert "--- meta ---" in err
    assert "duration_ms=" in err


def test_main_embed_smoke(monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setenv("INTELLIQX_LLM_BACKEND", "fake")
    set_llm_client(FakeLLMClient(dim=8))
    rc = main(["--embed", "--prompt", "embed-me"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "--- embed ---" in err
    assert "count=1" in err
    assert "dim=8" in err


def test_main_unknown_backend_raises(monkeypatch: pytest.MonkeyPatch, capsys):
    """An unknown backend name is reported on stderr with a non-zero exit."""
    monkeypatch.setenv("INTELLIQX_LLM_BACKEND", "definitely-not-a-backend")
    rc = main([])
    assert rc == 1
    err = capsys.readouterr().err
    assert "definitely-not-a-backend" in err


def test_main_exception_in_complete_is_caught(monkeypatch: pytest.MonkeyPatch, capsys):
    """If complete() raises, the CLI must exit 1 with a useful message."""
    monkeypatch.setenv("INTELLIQX_LLM_BACKEND", "fake")

    class _BoomClient(FakeLLMClient):
        async def complete(self, request):
            raise RuntimeError("kaboom")

    set_llm_client(_BoomClient())
    rc = main(["--prompt", "Hi"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "kaboom" in err


def test_main_show_env(monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setenv("INTELLIQX_LLM_BACKEND", "fake")
    set_llm_client(FakeLLMClient(dim=128))
    rc = main(["--show-env", "--prompt", "env-test"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "backend=fake" in err
    assert "dim=128" in err


@pytest.mark.unit
def test_python_m_intelliqx_llm_runs_smoke_cli(monkeypatch: pytest.MonkeyPatch):
    """``python -m intelliqx_llm`` should run the same smoke CLI."""
    monkeypatch.setenv("INTELLIQX_LLM_BACKEND", "fake")
    result = subprocess.run(
        [sys.executable, "-m", "intelliqx_llm"],
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "INTELLIQX_LLM_BACKEND": "fake"},
        check=False,
    )
    assert result.returncode == 0
    assert "--- response ---" in result.stderr
    assert "--- meta ---" in result.stderr

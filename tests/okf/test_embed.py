"""Tests for the OKF :class:`Embedder` contract."""

from __future__ import annotations

from intelliqx_okf.embed import Embedder, EmbeddingMismatchError

from ._embed import FakeEmbedder


def test_fake_embedder_is_deterministic_and_dimension_matches() -> None:
    e = FakeEmbedder(dim=12)
    v1 = e.embed("hello world")
    v2 = e.embed("hello world")
    assert v1 == v2
    assert len(v1) == 12
    assert e.name == "fake-12"


def test_embedding_mismatch_error_carries_context() -> None:
    err = EmbeddingMismatchError(
        existing_name="fake-8", existing_dim=8, requested_name="fake-16", requested_dim=16
    )
    assert "fake-8" in str(err)
    assert "fake-16" in str(err)
    assert err.existing_dim == 8 and err.requested_dim == 16


def test_fake_embedder_satisfies_protocol() -> None:
    assert isinstance(FakeEmbedder(dim=4), Embedder)

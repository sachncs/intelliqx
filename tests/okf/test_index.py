"""Tests for :mod:`intelliqx_okf.index`."""

from __future__ import annotations

from pathlib import Path

import pytest
from intelliqx_okf.concept import OKFConcept
from intelliqx_okf.embed import EmbeddingMismatchError
from intelliqx_okf.frontmatter import OKFFrontmatter
from intelliqx_okf.index import Index

from ._embed import FakeEmbedder

DIM = 8


def _concept(cid: str, body: str, type_: str = "doc", tags: list[str] | None = None) -> OKFConcept:
    return OKFConcept(
        concept_id=cid,
        frontmatter=OKFFrontmatter(type=type_, title=cid.title(), tags=tags or []),
        body=body,
    )


def test_write_then_read_returns_concept(tmp_path: Path) -> None:
    idx = Index(tmp_path / "k.db", embed=FakeEmbedder(DIM))
    idx.write(_concept("hello", "hello world"))
    hits = idx.read("hello")
    assert [h.concept.concept_id for h in hits] == ["hello"]


def test_write_is_idempotent(tmp_path: Path) -> None:
    idx = Index(tmp_path / "k.db", embed=FakeEmbedder(DIM))
    idx.write(_concept("a", "first"))
    idx.write(_concept("a", "second"))
    assert len(idx.read("first")) == 0
    hits = idx.read("second", top=10)
    assert len(hits) == 1
    assert hits[0].concept.body == "second"


def test_empty_text_concept_round_trips(tmp_path: Path) -> None:
    idx = Index(tmp_path / "k.db", embed=FakeEmbedder(DIM))
    idx.write(_concept("blank", ""))
    hits = idx.read("Blank", top=10)
    assert len(hits) == 1
    assert hits[0].concept.concept_id == "blank"


def test_type_and_tag_filters(tmp_path: Path) -> None:
    idx = Index(tmp_path / "k.db", embed=FakeEmbedder(DIM))
    idx.write(_concept("a", "alpha bravo", type_="api", tags=["x"]))
    idx.write(_concept("b", "alpha charlie", type_="guide", tags=["y"]))
    assert [h.concept.concept_id for h in idx.read("alpha", type="api")] == ["a"]
    assert [h.concept.concept_id for h in idx.read("alpha", tag="y")] == ["b"]


def test_dimension_mismatch_on_reopen(tmp_path: Path) -> None:
    Index(tmp_path / "k.db", embed=FakeEmbedder(DIM)).close()
    with pytest.raises(EmbeddingMismatchError):
        Index(tmp_path / "k.db", embed=FakeEmbedder(DIM + 4))


def test_embedding_dim_mismatch_raises(tmp_path: Path) -> None:
    idx = Index(tmp_path / "k.db", embed=FakeEmbedder(DIM))
    idx.write(_concept("a", "alpha"))
    with pytest.raises(ValueError, match="Embedding dim mismatch"):
        idx.read("alpha", query_embedding=[0.0] * (DIM + 1))


def test_concept_with_empty_text_skips_vector(tmp_path: Path) -> None:
    idx = Index(tmp_path / "k.db", embed=FakeEmbedder(DIM))
    idx.write(_concept("blank", ""))
    hits = idx.read("Blank", top=10)
    assert len(hits) == 1
    assert hits[0].concept.concept_id == "blank"


def test_close_is_idempotent(tmp_path: Path) -> None:
    idx = Index(tmp_path / "k.db", embed=FakeEmbedder(DIM))
    idx.close()
    idx.close()


def test_hybrid_ranking_prefers_keyword_match(tmp_path: Path) -> None:
    idx = Index(tmp_path / "k.db", embed=FakeEmbedder(DIM))
    idx.write(_concept("on", "authentication flow"))
    idx.write(_concept("off", "unrelated body"))
    top = idx.read("authentication", top=2)
    assert top[0].concept.concept_id == "on"


def test_in_memory_index(tmp_path: Path) -> None:
    idx = Index(":memory:", embed=FakeEmbedder(DIM))
    idx.write(_concept("a", "memory"))
    assert [h.concept.concept_id for h in idx.read("memory")] == ["a"]

# ADR-0011: OKF Catalog with Hybrid FTS5 + sqlite-vec Retrieval

## Status

Accepted

## Context

The platform needs a structured knowledge source that combines
typed metadata (concept type, tags, timestamps) with full-text
search and vector similarity. The OKF (Open Knowledge Format)
bundle format provides the metadata schema; the catalog provides
the retrieval engine.

Three retrieval strategies are available:

1. **FTS5** — SQLite's built-in full-text search. Fast, zero-
   dependency, but no semantic understanding. Handles keyword
   matching and proximity queries well.
2. **sqlite-vec** — SQLite extension for approximate nearest-
   neighbour search using quantised embeddings. Provides semantic
   similarity but requires an embedding model.
3. **Dual-candidate RRF** — Combines both ranked lists via
   reciprocal-rank fusion (RRF, k=60). Each source contributes
   an independently ranked candidate list; RRF merges them into
   a single ranking that is robust to incompatible score scales.

We chose dual-candidate RRF over raw-score blending because FTS5
scores (BM25) and vector cosine similarities live on different
scales and cannot be meaningfully combined additively. RRF is
rank-based: it only cares about the position of each document in
each list, not the raw scores.

## Decision

1. **Tenant-scoped catalog.** The `concepts` table has a composite
   primary key `(concept_id, tenant_id)`. Multiple tenants share
   a single SQLite file without cross-contamination. Each tenant's
   data is independently rebuildable via `build_catalog(tenant_id=)`.

2. **FTS5 tokenization.** Natural-language queries are pre-
   processed by `_tokenize_fts5()` which extracts alphanumeric
   tokens and quotes them, preventing FTS5 syntax errors from
   hyphens, question marks, apostrophes, and other punctuation.

3. **Structured filter aliasing.** The `_structured_where()`
   method accepts a `table_alias` parameter so JOINed queries
   (e.g. `concepts c JOIN concepts_ai a ON ...`) don't produce
   ambiguous column references.

4. **Cosine similarity in Python.** The sqlite-vec extension
   only supports L2 distance natively. Cosine similarity is
   computed in Python after fetching L2 candidates, ensuring
   scores are in `[-1, 1]` as the contract requires.

5. **Pre-filtering via eligible rowids.** When both structured
   filters and vector search are active, the catalog first
   computes the eligible rowid set from the structured filter,
   then restricts the vector search to those rowids. This avoids
   computing embeddings for documents that would be filtered out.

## Consequences

* **Single SQLite file per tenant group.** Simple deployment; no
  separate vector database needed for small-to-medium bundles.
* **RRF is rank-based.** Changing the FTS5 scoring formula or
  the vector distance metric doesn't break the fusion layer.
* **Embedding dimension must be consistent.** The `_meta` table
  stores the dimension and validates it on construction.
* **Graceful degradation.** If `sqlite-vec` is not installed, the
  catalog falls back to FTS5-only mode. Vector fields are ignored.

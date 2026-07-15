"""OKF retrieval bootstrap.

Loads tenant-scoped OKF bundles, builds the catalog, batch-embeds
concepts, and installs singletons so the RAG agent can immediately
search both the global vector index and the OKF catalog.

Usage::

    from pathlib import Path
    from intelliqx_okf.retrieval import bootstrap_okf_retrieval

    await bootstrap_okf_retrieval({
        "tenant_alpha": Path("/data/okf/alpha"),
        "tenant_beta": Path("/data/okf/beta"),
    })
"""

from __future__ import annotations

import logging
from pathlib import Path

from intelliqx_llm.client import get_llm_client
from intelliqx_vector.index import VectorDoc, get_vector_index

from intelliqx_okf.bundle import load_bundle
from intelliqx_okf.catalog import OKFCatalog, get_catalog, set_catalog

logger = logging.getLogger(__name__)

CONCEPT_EMBED_BATCH = 32  # Embed this many concepts per LLM call.


async def bootstrap_okf_retrieval(
    tenant_bundles: dict[str, Path],
    *,
    catalog: OKFCatalog | None = None,
    db_path: str | None = None,
    dim: int | None = None,
) -> int:
    """Bootstrap OKF retrieval for one or more tenants.

    For each tenant:

    1. Load the bundle from ``tenant_bundles[tenant_id]``.
    2. Build the catalog rows (FTS5 + relational) for that tenant.
    3. Batch-embed each non-reserved concept's title + description +
       body text.
    4. Store the embedding in both the OKF catalog (``concepts_ai``)
       and the global vector index under the key
       ``okf::<tenant_id>::<concept_id>``.

    Args:
        tenant_bundles: Mapping of tenant ID to bundle root path.
        catalog: Optional pre-built catalog instance. If ``None``,
            the global singleton is used (created via ``db_path``
            and ``dim``).
        db_path: Passed to ``OKFCatalog`` when creating a new
            singleton.
        dim: Vector dimension for sqlite-vec in the catalog.

    Returns:
        Total number of concepts embedded across all tenants.
    """
    llm = get_llm_client()
    vec_index = get_vector_index()

    cat = catalog or get_catalog()
    if catalog is None and (db_path or dim):
        cat = OKFCatalog(db_path=db_path, dim=dim)
        set_catalog(cat)

    total_embedded = 0

    for tenant_id, bundle_path in tenant_bundles.items():
        logger.info("Loading OKF bundle for tenant %s from %s", tenant_id, bundle_path)
        bundle = load_bundle(bundle_path)

        if bundle.errors:
            for path, error in bundle.errors:
                logger.warning("Bundle parse error for %s: %s", path, error)

        count = cat.build_catalog(bundle, tenant_id=tenant_id)
        logger.info("Built catalog for tenant %s: %d concepts", tenant_id, count)

        concepts_to_embed = [c for cid, c in bundle.concepts.items() if cid not in bundle.reserved]

        for i in range(0, len(concepts_to_embed), CONCEPT_EMBED_BATCH):
            batch = concepts_to_embed[i : i + CONCEPT_EMBED_BATCH]
            texts = [
                " ".join(
                    filter(
                        None,
                        [
                            c.frontmatter.title or "",
                            c.frontmatter.description or "",
                            c.body[:500] if c.body else "",
                        ],
                    )
                )
                for c in batch
            ]
            if not texts:
                continue
            embeddings = await llm.embed(texts, model="auto")
            for concept, embedding in zip(batch, embeddings, strict=False):
                cat.store_embedding(concept.concept_id, embedding, tenant_id=tenant_id)
                vec_id = f"okf::{tenant_id}::{concept.concept_id}"
                await vec_index.upsert(
                    [
                        VectorDoc(
                            id=vec_id,
                            tenant_id=tenant_id,
                            text=concept.body[:500] if concept.body else "",
                            vector=embedding,
                            metadata={
                                "source": "okf",
                                "concept_id": concept.concept_id,
                                "type": concept.frontmatter.type,
                            },
                        )
                    ]
                )
                total_embedded += 1

    logger.info("OKF bootstrap complete: %d concepts embedded", total_embedded)
    return total_embedded

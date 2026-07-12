"""Vector index abstraction for AQIP.

A small async surface that hides whether the underlying engine is the
in-memory numpy implementation (tests / small datasets) or the
on-disk zvec index (production). The same interface is implemented
twice:

* :class:`InMemoryVectorIndex` — pure numpy, dependency-free, used
  for tests and for low-cardinality datasets.
* :class:`ZvecIndex` — Alibaba's zvec embedded vector DB, persisted
  to the AQIP object store. Reference: https://github.com/alibaba/zvec

Both implementations:

* Accept :class:`VectorDoc` records keyed by id.
* Use cosine similarity (vectors are L2-normalised at search time).
* Scope results by ``tenant_id`` so cross-tenant reads return nothing.

The default production model is zvec; :func:`get_vector_index` returns
the in-memory index for tests and the zvec index for prod. The
``AQIP_VECTOR_DIM`` env var configures the in-memory dim.
"""

from intelliqx_vector.index import (
    InMemoryVectorIndex,
    SearchResult,
    VectorDoc,
    VectorIndex,
    get_vector_index,
)
from intelliqx_vector.zvec_index import ZvecIndex

__all__ = [
    "InMemoryVectorIndex",
    "SearchResult",
    "VectorDoc",
    "VectorIndex",
    "ZvecIndex",
    "get_vector_index",
]

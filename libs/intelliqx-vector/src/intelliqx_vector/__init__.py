"""Vector index abstraction for IntelliqX.

A small async surface that hides whether the underlying engine is the
in-memory numpy implementation (tests / small datasets), the on-disk
zvec index, or the on-disk sqlite-vec index (default for production).
The same interface is implemented by all three:

* :class:`InMemoryVectorIndex` — pure numpy, dependency-free, used
  for tests and for low-cardinality datasets.
* :class:`ZvecIndex` — Alibaba's zvec embedded vector DB, persisted
  to the IntelliqX object store. Reference:
  https://github.com/alibaba/zvec
* :class:`SqliteVecIndex` — Alex Garcia's sqlite-vec extension, a
  pure-SQLite ANN engine. Reference:
  https://github.com/asg017/sqlite-vec

All three implementations:

* Accept :class:`VectorDoc` records keyed by id.
* Use cosine similarity (vectors are L2-normalised at search time).
* Scope results by ``tenant_id`` so cross-tenant reads return nothing.

The default production index is sqlite-vec (zero-config,
single-file, dependency-light); :func:`get_vector_index` returns
the in-memory index for tests. The ``INTELLIQX_VECTOR_DIM`` env
var configures the in-memory dim.
"""

from intelliqx_vector.index import (
    InMemoryVectorIndex,
    SearchResult,
    VectorDoc,
    VectorIndex,
    get_vector_index,
    reset_vector_index,
    set_vector_index,
)
from intelliqx_vector.sqlite_vec_index import SqliteVecIndex
from intelliqx_vector.zvec_index import ZvecIndex

__all__ = [
    "InMemoryVectorIndex",
    "SearchResult",
    "SqliteVecIndex",
    "VectorDoc",
    "VectorIndex",
    "ZvecIndex",
    "get_vector_index",
    "reset_vector_index",
    "set_vector_index",
]

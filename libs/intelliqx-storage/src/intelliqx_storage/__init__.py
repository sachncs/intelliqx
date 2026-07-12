"""Object storage abstraction for IntelliqX.

A thin async wrapper over the three cloud object stores (S3, GCS,
Modal Volume) plus a filesystem-backed implementation for local dev.
All implementations share the same minimal interface:

* ``put(key, data, *, content_type=None)`` — write bytes
* ``get(key)`` → ``bytes`` (raises :class:`NotFoundError` if missing)
* ``exists(key)`` → ``bool``
* ``delete(key)`` — idempotent
* ``list(prefix)`` → async iterator of keys
* ``size(key)`` → ``int`` (default implementation: ``len(get(key))``)

**Namespace conventions** are the caller's responsibility: every key
written by IntelliqX is prefixed with the tenant id (``{tenant_id}/...``).
Tenants are *not* enforced by the store itself; the
:class:`intelliqx_tenant.IsolationEnforcer` provides runtime checks.
"""

from intelliqx_storage.store import (
    InMemoryObjectStore,
    LocalFileSystemObjectStore,
    ObjectStore,
    get_object_store,
)

__all__ = [
    "InMemoryObjectStore",
    "LocalFileSystemObjectStore",
    "ObjectStore",
    "get_object_store",
]

"""IntelliqX OKF (Open Knowledge Format) library.

Implements the [OKF v0.1 spec](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md):

* :class:`OKFFrontmatter` — Pydantic model of the YAML metadata block
  (``type`` required, ``title`` / ``description`` / ``resource`` /
  ``tags`` / ``timestamp`` recommended, plus arbitrary extension keys).
* :class:`OKFConcept` — frontmatter + parsed body (sections, links,
  citations).
* :func:`load_concept` — parse a single ``.md`` file.
* :func:`save_concept` — write a concept back to disk.
* :func:`load_bundle` — walk a directory tree, returning every
  non-reserved ``.md`` file as an :class:`OKFConcept` and recording
  ``index.md`` / ``log.md`` as such.
* :class:`OKFLinkResolver` — turn the bundle's relative markdown
  links into a (source, target) edge list, tolerant of broken links.
* :class:`OKFCatalog` (in :mod:`intelliqx_okf.catalog`) — a SQLite-
  backed FTS5 + sqlite-vec index over a bundle. Provides structured
  filter + full-text + vector retrieval for the RAG agent.

The library is intentionally dependency-light (Pydantic + PyYAML).
The optional catalog adds :class:`sqlite3` (stdlib) and
``sqlite-vec`` (a single-binary extension; gracefully degrades to
FTS5-only if missing).
"""

from intelliqx_okf.bundle import (
    OKFBundle,
    OKFEdge,
    OKFLinkResolver,
    load_bundle,
)
from intelliqx_okf.concept import (
    Citation,
    OKFConcept,
    OKFLink,
    OKFSection,
    load_concept,
    save_concept,
)
from intelliqx_okf.frontmatter import OKFFrontmatter
from intelliqx_okf.validator import (
    OKFValidationError,
    ValidationIssue,
    ValidationResult,
    validate_bundle,
    validate_concept,
)

__all__ = [
    "Citation",
    "OKFBundle",
    "OKFConcept",
    "OKFEdge",
    "OKFFrontmatter",
    "OKFLink",
    "OKFLinkResolver",
    "OKFSection",
    "OKFValidationError",
    "ValidationIssue",
    "ValidationResult",
    "load_bundle",
    "load_concept",
    "save_concept",
    "validate_bundle",
    "validate_concept",
]


def __getattr__(name):  # pragma: no cover - lazy import shim
    """Lazy-import :mod:`intelliqx_okf.catalog` to avoid forcing the
    sqlite-vec native extension to be importable when the catalog
    itself isn't used."""
    if name in {
        "OKFCatalog",
        "CatalogHit",
        "get_catalog",
        "set_catalog",
        "reset_catalog",
        "load_okf_catalog_from_bundle",
    }:
        from intelliqx_okf import catalog as _catalog

        return getattr(_catalog, name)
    raise AttributeError(f"module 'intelliqx_okf' has no attribute {name!r}")

"""IntelliqX OKF (Open Knowledge Format) library.

The OKF format is the platform's directional guide for retrieval: one
:class:`OKFConcept` per knowledge file, indexed through one SQLite
:class:`Index` (FTS5 + sqlite-vec) on a single ``Embedder``.

Public surface:

* :mod:`intelliqx_okf.concept` — :class:`OKFConcept`, :func:`load_concept`,
  :func:`save_concept`.
* :mod:`intelliqx_okf.frontmatter` — :class:`OKFFrontmatter`.
* :mod:`intelliqx_okf.bundle` — :func:`load_bundle`, :class:`OKFBundle`,
  :class:`OKFLinkResolver`.
* :mod:`intelliqx_okf.index` — :class:`Index`, :class:`Hit`.
* :mod:`intelliqx_okf.embed` — :class:`Embedder` Protocol,
  :class:`EmbeddingMismatchError`.
* :mod:`intelliqx_okf.validator` — OKF spec validation helpers.

The library stays dependency-light (Pydantic + PyYAML). The index adds
:class:`sqlite3` (stdlib) and ``sqlite-vec`` (a single-binary extension).
"""

from intelliqx_okf.bundle import OKFBundle, OKFEdge, OKFLinkResolver, load_bundle
from intelliqx_okf.concept import (
    Citation,
    OKFConcept,
    OKFLink,
    OKFSection,
    load_concept,
    save_concept,
)
from intelliqx_okf.embed import Embedder, EmbeddingMismatchError
from intelliqx_okf.frontmatter import OKFFrontmatter
from intelliqx_okf.index import Hit, Index
from intelliqx_okf.validator import (
    OKFValidationError,
    ValidationIssue,
    ValidationResult,
    validate_bundle,
    validate_concept,
)

__all__ = [
    "Citation",
    "Embedder",
    "EmbeddingMismatchError",
    "Hit",
    "Index",
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

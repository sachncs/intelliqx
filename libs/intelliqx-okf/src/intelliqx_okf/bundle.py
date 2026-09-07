"""OKF bundle loader and link resolver.

A bundle is a directory tree of ``.md`` files. :func:`load_bundle`
walks the tree and returns:

* Every non-reserved ``.md`` file as an :class:`OKFConcept` (in a
  :class:`OKFBundle`).
* ``index.md`` and ``log.md`` entries (reserved by §3.1) as
  :class:`OKFConcept` instances too — the parser doesn't enforce
  "no frontmatter" on them, so the bundle-root ``index.md`` can
  carry ``okf_version`` per §11.
* A list of malformed files (skipped, but reported).

:class:`OKFLinkResolver` turns the bundle's internal markdown
links into a list of :class:`OKFEdge` records, resolving
``/tables/users.md``-style absolute links against the bundle root.
Per §5.3, broken links are tolerated (the resolver skips them and
returns a count of unresolved links).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from intelliqx_okf.concept import OKFConcept, load_concept

# Reserved filenames per §3.1. These files are still parsed as
# concepts when present (so the bundle-root ``index.md`` can carry
# ``okf_version`` per §11), but consumers must not treat them as
# regular concept documents.
RESERVED_FILENAMES = frozenset({"index.md", "log.md"})


@dataclass
class OKFBundle:
    """A loaded OKF bundle."""

    root: Path
    concepts: dict[str, OKFConcept]  # concept_id -> concept
    errors: list[tuple[Path, str]] = field(default_factory=list)
    # Reserved-file concepts (index.md / log.md) are also stored
    # under ``concepts`` for convenience; this map records which
    # ones are reserved so the catalog can index them differently
    # if desired.
    reserved: set[str] = field(default_factory=set)

    def __len__(self) -> int:
        return len(self.concepts)

    def __iter__(self) -> Iterator[OKFConcept]:
        return iter(self.concepts.values())


def load_bundle(root: Path | str, *, follow_symlinks: bool = False) -> OKFBundle:
    """Walk a directory tree and return every ``.md`` file as an OKF concept.

    The root directory itself is the bundle root. ``index.md`` and
    ``log.md`` are loaded too; consumers that don't want to index
    them can filter on :attr:`OKFBundle.reserved`.

    Args:
        root: Path to the bundle directory.
        follow_symlinks: If ``True``, follow symlinks during the
            walk. Defaults to ``False`` to avoid loops.

    Returns:
        An :class:`OKFBundle` with every successfully-parsed
        concept, plus a list of ``(path, error)`` tuples for any
        file that failed to parse.
    """
    root_path = Path(root).resolve()
    concepts: dict[str, OKFConcept] = {}
    errors: list[tuple[Path, str]] = []
    reserved: set[str] = set()

    for path in walk_md(root_path, follow_symlinks):
        if not path.is_file():
            continue
        # Compute the concept id relative to the bundle root, with
        # the ``.md`` suffix stripped. Using the relative path as
        # the concept id (rather than the absolute path that
        # :func:`load_concept` would set) makes the catalog
        # portable: the same bundle indexed at different absolute
        # locations still has the same concept ids.
        rel = path.relative_to(root_path).as_posix()
        concept_id = rel[: -len(".md")] if rel.endswith(".md") else rel
        try:
            concept = load_concept(path)
        except (ValueError, OSError) as e:
            errors.append((path, str(e)))
            continue
        # Override the absolute-path concept id set by
        # :func:`load_concept` with the bundle-relative id so the
        # catalog and link resolver use stable keys.
        concept = concept.model_copy(update={"concept_id": concept_id})
        # If the file has the same concept id as one already loaded
        # (e.g. symlinks pointing to the same file), the second one
        # overwrites the first. Callers that care can inspect
        # ``bundle.errors`` for any ``OSError`` raised during walk.
        concepts[concept_id] = concept
        if path.name in RESERVED_FILENAMES:
            reserved.add(concept_id)

    return OKFBundle(root=root_path, concepts=concepts, errors=errors, reserved=reserved)


def walk_md(root: Path, follow_symlinks: bool) -> Iterator[Path]:
    """Recursive ``.md`` walker.

    ``Path.rglob`` doesn't accept a pattern in some 3.12+ configs;
    this helper makes the walk explicit and testable.
    """
    for path in root.rglob("*.md"):
        if not follow_symlinks and path.is_symlink():
            continue
        yield path


@dataclass(frozen=True)
class OKFEdge:
    """A resolved cross-link between two concepts.

    ``source`` is the concept id of the linking document;
    ``target`` is the concept id of the link destination. Edges
    are untyped (per §5.3); the surrounding prose is what gives
    the relationship meaning.
    """

    source: str
    target: str
    text: str


class OKFLinkResolver:
    """Resolve a bundle's internal markdown links into edges.

    Per §5, two link forms are supported:

    * **Absolute (bundle-relative)**: ``/tables/users.md`` →
      ``tables/users``.
    * **Relative**: ``./other.md`` or ``other.md`` → resolved
      against the linking concept's directory.

    External (http(s)://) and absolute-path (file://) links are
    skipped. Broken links (target doesn't exist) are skipped and
    counted in :attr:`unresolved_count`.
    """

    def __init__(self, bundle: OKFBundle) -> None:
        self.bundle = bundle
        self.unresolved_count = 0

    def edges(self) -> list[OKFEdge]:
        out: list[OKFEdge] = []
        for concept in self.bundle.concepts.values():
            source_id = concept.concept_id
            source_dir = Path(source_id).parent
            for link in concept.links:
                target = link.target
                if not target:
                    continue
                if target.startswith(("http://", "https://", "file://", "mailto:")):
                    continue
                if target.startswith("/"):
                    # Absolute bundle-relative: strip leading ``/``
                    # and ``.md`` if present.
                    target_id = target.lstrip("/")
                else:
                    # Relative: resolve against source dir.
                    abs_target = (source_dir / target).as_posix()
                    target_id = abs_target
                if target_id.endswith(".md"):
                    target_id = target_id[: -len(".md")]
                # Normalise away any ``./`` prefix segments.
                target_id = normalise_path(target_id)
                if target_id not in self.bundle.concepts:
                    self.unresolved_count += 1
                    continue
                out.append(OKFEdge(source=source_id, target=target_id, text=link.text))
        return out


PATH_NORMALISE_RE = re.compile(r"(^|/)\./")


def normalise_path(path: str) -> str:
    """Collapse ``./`` segments in a POSIX path."""
    # Iterative replacement to handle chains like ``a/./b/./c``.
    prev = None
    while prev != path:
        prev = path
        path = PATH_NORMALISE_RE.sub(r"\1", path)
    return path

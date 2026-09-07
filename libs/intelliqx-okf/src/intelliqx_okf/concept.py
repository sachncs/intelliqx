"""OKF concept document: frontmatter + parsed body.

Implements §4 of the OKF spec. A :class:`OKFConcept` is the
in-memory representation of one ``.md`` file in a bundle: a parsed
:class:`OKFFrontmatter`, the markdown body as plain text, the
``# Citations`` list, and the body broken into ``# Schema`` /
``# Examples`` / etc. sections.

The body parser is intentionally light — it splits on top-level
markdown headings (``# ...``) and extracts markdown links and the
``# Citations`` block. Anything fancier (GFM tables, code blocks,
nested lists) is preserved verbatim in :attr:`OKFConcept.body`
so consumers that need a full markdown render can pass the string
to a library of their choice.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field

from intelliqx_okf.frontmatter import OKFFrontmatter


class OKFLink(BaseModel):
    """A markdown link extracted from a concept body."""

    model_config = ConfigDict(extra="forbid")

    text: str
    target: str  # may be relative ("tables/users.md") or absolute


class OKFSection(BaseModel):
    """A single ``# Heading`` section of a concept body.

    The text inside a section is preserved verbatim (with the
    leading heading stripped) so consumers can re-render it.
    """

    model_config = ConfigDict(extra="forbid")

    heading: str
    body: str


class Citation(BaseModel):
    """A single entry under the concept's ``# Citations`` block.

    ``target`` is the link's destination (a URL, bundle-relative
    path, or external reference). ``label`` is the visible text.
    """

    model_config = ConfigDict(extra="forbid")

    label: str
    target: str


class OKFConcept(BaseModel):
    """An OKF concept document.

    Attributes:
        concept_id: The path of the concept's file within the
            bundle, with the ``.md`` suffix removed. For example,
            ``"tables/users.md"`` becomes ``"tables/users"``.
        source_path: Absolute path on disk when the concept was
            loaded from a bundle; ``None`` for in-memory concepts.
        frontmatter: The parsed YAML metadata.
        body: Raw markdown body (frontmatter stripped).
        sections: Body broken into ``# Heading`` sections.
        links: Every markdown link in the body.
        citations: Entries from the ``# Citations`` section (if any).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    concept_id: str
    source_path: Path | None = None
    frontmatter: OKFFrontmatter
    body: str
    sections: list[OKFSection] = Field(default_factory=list)
    links: list[OKFLink] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


# --- Parsing --------------------------------------------------------------

# Matches the YAML frontmatter delimiter line: a line that is exactly
# "---" (with optional trailing whitespace). The block must be at
# the very top of the file.
FRONTMATTER_RE = re.compile(r"^---\s*$", re.MULTILINE)

# Matches markdown links of the form `[text](target)`. The
# target is captured lazily up to the first unescaped ')'. This
# intentionally doesn't try to handle complex URLs (parentheses in
# URLs are uncommon in OKF).
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# Top-level markdown heading: ``# Heading`` (but not ``## `` or
# ``### `` — those are sub-headings and stay inside the parent
# section). The OKF spec doesn't distinguish heading levels in any
# semantic way, so we treat the first ``# ...`` as the section
# boundary and everything below until the next ``# ...`` is the
# section's body.
SECTION_RE = re.compile(r"^# (.+)$", re.MULTILINE)


def parse_frontmatter_and_body(text: str) -> tuple[dict[str, Any], str]:
    """Split a markdown file into ``(frontmatter_dict, body)``.

    The file MUST start with a ``---`` line; if it doesn't, the
    whole text is treated as body and the frontmatter is empty.
    """
    text = text.lstrip("\ufeff")  # tolerate BOM
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return {}, text
    # Find the closing ``---`` after the opening one.
    matches = list(FRONTMATTER_RE.finditer(text))
    if len(matches) < 2:
        return {}, text
    close_start = matches[1].start()
    fm_text = text[matches[0].end() : close_start]
    body_start = matches[1].end()
    # Skip the single newline that follows the closing ``---`` if
    # present, to keep the body aligned with the original.
    body = text[body_start:]
    if body.startswith("\n"):
        body = body[1:]
    try:
        parsed = yaml.safe_load(fm_text) or {}
        if not isinstance(parsed, dict):
            parsed = {}
    except yaml.YAMLError:
        parsed = {}
    return parsed, body


def split_sections(body: str) -> list[OKFSection]:
    """Split ``body`` into ``# Heading`` sections.

    The body before the first ``# ...`` heading is returned as a
    section with ``heading=""`` (an "intro" section).
    """
    matches = list(SECTION_RE.finditer(body))
    if not matches:
        return [OKFSection(heading="", body=body)]
    sections: list[OKFSection] = []
    intro_end = matches[0].start()
    if intro_end:
        sections.append(OKFSection(heading="", body=body[:intro_end].rstrip("\n")))
    for i, m in enumerate(matches):
        next_start = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        section_body = body[m.end() : next_start].strip("\n")
        sections.append(OKFSection(heading=m.group(1).strip(), body=section_body))
    return sections


def extract_links(body: str) -> list[OKFLink]:
    """Pull every markdown link out of ``body``.

    Duplicate (text, target) pairs are collapsed so callers don't
    have to dedupe themselves.
    """
    seen: set[tuple[str, str]] = set()
    out: list[OKFLink] = []
    for m in LINK_RE.finditer(body):
        text = m.group(1).strip()
        target = m.group(2).strip()
        key = (text, target)
        if key in seen:
            continue
        seen.add(key)
        out.append(OKFLink(text=text, target=target))
    return out


def extract_citations(sections: list[OKFSection]) -> list[Citation]:
    """Find the ``# Citations`` section and parse its numbered list."""
    for s in sections:
        if s.heading.lower() == "citations":
            out: list[Citation] = []
            for m in LINK_RE.finditer(s.body):
                label = m.group(1).strip()
                # Strip a leading numeric prefix like "1. " or "[1] "
                # so the citation number doesn't end up in the label.
                label = re.sub(r"^\[\d+\]\s*", "", label)
                label = re.sub(r"^\d+\.\s*", "", label)
                out.append(Citation(label=label, target=m.group(2).strip()))
            return out
    return []


def split_frontmatter_from_extras(parsed: dict) -> tuple[OKFFrontmatter, dict]:
    """Separate known fields from arbitrary extras.

    The OKF spec (§4.1) calls out the six known fields; everything
    else lands in :attr:`extra_fields`. ``okf_version`` is kept as
    a top-level field because the spec uses it for version
    negotiation.
    """
    known = {"type", "title", "description", "resource", "tags", "timestamp", "okf_version"}
    fm_data: dict[str, Any] = {}
    extras: dict[str, Any] = {}
    for k, v in parsed.items():
        if k in known:
            fm_data[k] = v
        else:
            extras[k] = v
    return OKFFrontmatter(**fm_data, extra_fields=extras), extras


# --- I/O --------------------------------------------------------------------


def load_concept(path: Path | str) -> OKFConcept:
    """Load a single ``.md`` file as an :class:`OKFConcept`.

    The file must be UTF-8. If parsing fails (bad YAML, missing
    ``type``), a :class:`ValueError` is raised.
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    parsed, body = parse_frontmatter_and_body(text)
    if "type" not in parsed or not parsed.get("type"):
        raise ValueError(f"OKF concept {p} has no 'type' frontmatter field (required by spec §4.1)")
    frontmatter, _extras = split_frontmatter_from_extras(parsed)
    sections = split_sections(body)
    links = extract_links(body)
    citations = extract_citations(sections)
    concept_id = str(p).removesuffix(".md")
    return OKFConcept(
        concept_id=concept_id,
        source_path=p,
        frontmatter=frontmatter,
        body=body,
        sections=sections,
        links=links,
        citations=citations,
    )


def save_concept(concept: OKFConcept, path: Path | str) -> None:
    """Serialise ``concept`` back to ``.md`` (YAML frontmatter + body).

    Extra frontmatter fields are preserved. ``okf_version`` is
    kept on the top level. ``index.md`` and ``log.md`` are
    reserved filenames (§3.1); callers are responsible for
    ensuring the output path is appropriate.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = concept.frontmatter.model_dump_okf()
    # ``sort_keys=False`` preserves author intent; ``allow_unicode``
    # is on by default in modern PyYAML.
    yaml_text = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip("\n")
    body = concept.body or ""
    # Always emit a trailing newline at EOF (POSIX text file
    # convention) but only one.
    if not body.endswith("\n"):
        body = body + "\n"
    p.write_text(f"---\n{yaml_text}\n---\n\n{body}", encoding="utf-8")

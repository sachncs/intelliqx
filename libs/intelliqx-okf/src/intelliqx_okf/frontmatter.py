"""OKF frontmatter (YAML metadata) model.

Implements §4.1 of the OKF spec. ``type`` is the only required
field. Every other field is recommended but optional; producers
MAY attach arbitrary additional keys (``extra_fields``), and
consumers MUST preserve unknown keys on round-trip per §9 of the
spec.

The :class:`OKFFrontmatter` model is configured with
``extra="allow"`` so arbitrary producer fields round-trip cleanly
through Pydantic — anything in the YAML block that isn't a known
field is captured in :attr:`OKFFrontmatter.extra_fields` instead
of being rejected.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OKFFrontmatter(BaseModel):
    """The YAML frontmatter block of an OKF concept document.

    Attributes:
        type: Required. A short string identifying the kind of
            concept (e.g. ``"BigQuery Table"``, ``"API Endpoint"``,
            ``"Playbook"``). Unknown values are accepted (the spec
            requires consumers to be tolerant).
        title: Human-readable display name. Falls back to the
            concept's filename when missing.
        description: One-sentence summary.
        resource: Canonical URI for the underlying asset the
            concept describes. Optional; absent for abstract
            concepts.
        tags: Cross-cutting categorisation tags.
        timestamp: ISO 8601 datetime of the last meaningful change.
        extra_fields: Arbitrary additional fields that consumers
            should preserve on round-trip. Stored as a plain dict
            so JSON serialisation is lossless.
        okf_version: The OKF version this concept targets. Per
            §11, the only place this is permitted is the bundle's
            root ``index.md``; :class:`OKFConcept` allows it on
            every concept for permissive consumption.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: str = Field(min_length=1)
    title: str | None = None
    description: str | None = None
    resource: str | None = None
    tags: list[str] = Field(default_factory=list)
    timestamp: datetime | None = None
    okf_version: str | None = Field(default=None, alias="okf_version")
    extra_fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def _strip_type(cls, v: str) -> str:
        """Strip surrounding whitespace from ``type``.

        YAML frontmatter often has accidental trailing spaces;
        a concept type of ``"BigQuery Table "`` should still be
        treated as ``"BigQuery Table"``.
        """
        return v.strip()

    def model_dump_okf(self) -> dict[str, Any]:
        """Serialise to a YAML-friendly dict that preserves extras.

        Unlike :meth:`BaseModel.model_dump`, this method:

        * Does not include ``extra_fields`` as a key (its keys
          are merged into the top-level dict).
        * Drops ``None`` values (YAML frontmatter convention).
        * Keeps ``okf_version`` under the ``okf_version`` key
          even though Pydantic would alias it.
        """
        out: dict[str, Any] = {"type": self.type}
        if self.title is not None:
            out["title"] = self.title
        if self.description is not None:
            out["description"] = self.description
        if self.resource is not None:
            out["resource"] = self.resource
        if self.tags:
            out["tags"] = list(self.tags)
        if self.timestamp is not None:
            out["timestamp"] = self.timestamp.isoformat()
        if self.okf_version is not None:
            out["okf_version"] = self.okf_version
        # Merge extra fields last so they can override (though the
        # spec discourages this).
        for k, v in self.extra_fields.items():
            out.setdefault(k, v)
        return out

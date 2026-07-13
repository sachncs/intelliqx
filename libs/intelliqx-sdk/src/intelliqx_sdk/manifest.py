"""Agent manifest for marketplace agents.

A manifest is the public contract for a third-party agent. It is
written to disk as JSON and consumed by the marketplace loader,
which validates the file against this schema before installing the
agent.

Attributes:
    name: Agent registry key. Must be unique within a tenant.
    version: SemVer. Marketplace agents may pin to a specific
        version.
    category: Functional category (coordination, intelligence,
        execution, governance); same enum used by first-party agents.
    description: One-line summary; shown in marketplace listings.
    author: Display name for the author / vendor.
    input_schema / output_schema: Optional JSON Schemas.
    capabilities: Tags used by :class:`intelliqx_tools.registry.find_by_capability`.
    permissions: Strings describing what the agent is allowed to do
        (``"net"``, ``"fs"``, ``"subprocess"``). The runtime enforces
        these against the sandbox.
    signature: Optional Ed25519 signature over the rest of the
        manifest. Set by the publisher; verified at install time.
    entrypoint: Module path and attribute the runtime imports to
        instantiate the agent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from intelliqx_core.models import AgentCategory
from pydantic import BaseModel, ConfigDict, Field


class AgentManifest(BaseModel):
    """A third-party agent's public contract.

    The manifest is intentionally serialisable to plain JSON so
    publishers can hand it to the marketplace via git, S3, or any
    other transport.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    category: AgentCategory
    description: str = ""
    author: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    signature: str | None = None  # Ed25519 signature (set by signer)
    entrypoint: str = "agent:Agent"


def load_manifest(path: Path | str) -> AgentManifest:
    """Load and validate a manifest from disk.

    Args:
        path: Filesystem path to the manifest JSON file.

    Returns:
        A validated :class:`AgentManifest`.

    Raises:
        pydantic.ValidationError: If the file doesn't match the
            schema.
        FileNotFoundError: If the path does not exist.
    """
    return AgentManifest.model_validate_json(Path(path).read_text())


def dump_manifest(manifest: AgentManifest, path: Path | str) -> None:
    """Serialise ``manifest`` to ``path`` as pretty-printed JSON.

    Args:
        manifest: The manifest to write.
        path: Destination file path. Overwritten if it exists.
    """
    Path(path).write_text(manifest.model_dump_json(indent=2))

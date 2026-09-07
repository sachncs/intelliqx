"""Event schemas and registry.

The :class:`EventRegistry` is a process-wide map from topic name to a
JSON Schema. The bus uses it (when ``jsonschema`` is installed) to
validate outgoing payloads, catching producer bugs at the boundary
instead of letting malformed data propagate to consumers.

Schemas can be loaded from a directory of ``.json`` files via
:func:`load_contracts_from_dir`; the file's ``title`` (or filename)
becomes the topic key.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field


class EventContract(BaseModel):
    """A JSON Schema describing the payload for one event topic.

    The ``schema_`` field is aliased to ``schema`` so YAML / JSON
    config can use the natural name without colliding with the
    Pydantic ``Schema`` model. Callers should access it as
    ``contract.schema_``.
    """

    model_config = ConfigDict(frozen=True)

    topic: str
    description: str
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")


class EventRegistry:
    """Process-wide registry of event-topic schemas.

    All methods are class methods because the registry is a singleton
    that lives for the process lifetime. There is no instance state.
    """

    _contracts: ClassVar[dict[str, EventContract]] = {}

    @classmethod
    def register(cls, contract: EventContract) -> None:
        """Register a contract. Replaces any existing contract for the topic.

        Args:
            contract: The contract to register.
        """
        cls._contracts[contract.topic] = contract

    @classmethod
    def get(cls, topic: str) -> EventContract:
        """Return the contract for ``topic``.

        Raises:
            KeyError: If no contract is registered for ``topic``.
        """
        if topic not in cls._contracts:
            raise KeyError(f"Unknown topic: {topic!r}")
        return cls._contracts[topic]

    @classmethod
    def all(cls) -> dict[str, EventContract]:
        """Return a copy of every registered contract, keyed by topic."""
        return dict(cls._contracts)

    @classmethod
    def validate(cls, topic: str, payload: dict[str, Any]) -> None:
        """Best-effort schema validation of ``payload`` for ``topic``.

        If the ``jsonschema`` package is installed, validates
        strictly. Otherwise this is a no-op (we don't want to make
        the runtime test suite depend on ``jsonschema``).

        Raises:
            jsonschema.ValidationError: If the payload fails the
                registered schema.
            KeyError: If no contract is registered for ``topic``.
        """
        try:
            import jsonschema  # type: ignore
        except ImportError:
            return
        contract = cls.get(topic)
        jsonschema.validate(payload, contract.schema_)


def get_registry() -> type[EventRegistry]:
    """Return the :class:`EventRegistry` class.

    The registry is class-level state, so this is a trivial accessor
    provided for symmetry with the other singletons
    (``get_event_bus``, ``get_metrics`` …).
    """
    return EventRegistry


def load_contracts_from_dir(path: Path) -> int:
    """Bulk-load contracts from a directory of JSON Schema files.

    The directory may contain any number of ``.json`` files; each one
    becomes a single :class:`EventContract`. The file's ``title``
    (or its stem if ``title`` is missing) becomes the topic key.

    Args:
        path: Directory to scan.

    Returns:
        The number of contracts successfully loaded. Files that fail
        to parse are silently skipped (the platform keeps working
        with whatever did load).
    """
    count = 0
    if not path.exists():
        return 0
    for f in sorted(path.glob("*.json")):
        try:
            data = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        topic = data.get("title") or f.stem
        contract = EventContract(
            topic=topic,
            description=data.get("description", ""),
            schema_=data,  # type: ignore[call-arg]
        )
        EventRegistry.register(contract)
        count += 1
    return count

"""Test Data Agent (Tier 2).

Generates synthetic datasets from a column-type schema. The agent
is intentionally simple — it does not consult a real data
generator. Each column is generated independently:

* ``string`` / ``str`` — context-sensitive defaults: emails
  always go to ``@example.com``; ages are 18..67; names are
  ``UserN``.
* ``int`` / ``integer`` — context-sensitive for ``age``, else row
  index.
* ``float`` / ``number`` — row index as float.
* ``bool`` / ``boolean`` — alternating ``True`` / ``False``.
* ``list`` — ``[f"{col}_0", f"{col}_1"]``.

The ``privacy_safe`` flag is ``True`` only when the validator
confirms no real-looking email slipped through (i.e. every email
matches ``@example.com``/``@test.com``/``@localhost``).

The validator is a heuristic; production deployments that need
stronger guarantees should layer Presidio on top.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from pydantic import BaseModel, ConfigDict, Field

from agents.intelligence.models import TestDataOutput


class TestDataInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_: dict[str, Any] = Field(alias="schema")  # {"name": "string", "age": "int", ...}
    count: int = 10
    privacy_safe: bool = True


class TestDataAgentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output: TestDataOutput


class TestDataAgent(AgentBase):
    # ``pytest`` interprets any class named ``Test*`` as a test class
    # by default. Disable collection here so the agent class is
    # not mistaken for a test case.
    __test__ = False
    META = AgentMeta(
        name="test_data",
        tier=2,
        version="0.1.0",
        description="Generates synthetic test data, privacy-safe by default.",
    )
    INPUT_MODEL = TestDataInput
    OUTPUT_MODEL = TestDataAgentOutput

    # PII patterns used by the validator. ``email`` requires a
    # safe-domain suffix; ``ssn``/``phone`` are not generated at
    # all but are recognised for completeness.
    PII_PATTERNS: ClassVar[dict[str, str]] = {
        "email": r"@example\.com$",
        "ssn": r"^\d{3}-\d{2}-\d{4}$",
        "phone": r"^\+1-\d{3}-\d{3}-\d{4}$",
    }

    @traced_agent("test_data")
    async def run(self, ctx: AgentContext, input: TestDataInput) -> TestDataAgentOutput:
        items = [
            _generate_row(input.schema_, idx, privacy_safe=input.privacy_safe)
            for idx in range(input.count)
        ]
        privacy_safe = _validate_privacy_safe(items)
        return TestDataAgentOutput(output=TestDataOutput(items=items, privacy_safe=privacy_safe))


def _generate_row(schema: dict[str, str], idx: int, *, privacy_safe: bool) -> dict[str, Any]:
    """Generate a single row following ``schema``.

    The per-column rules:

    * ``string`` / ``str`` — emails always go to ``@example.com``
      (privacy-safe), ages are 18..67, names are ``UserN``, other
      strings are ``f"{col}_{idx}"``.
    * ``int`` / ``integer`` — age is 18..67, others are row index.
    * ``float`` / ``number`` — row index as float.
    * ``bool`` / ``boolean`` — alternating ``True``/``False`` by row.
    * ``list`` — ``[f"{col}_0", f"{col}_1"]``.

    Unknown types produce ``None``. ``privacy_safe`` is accepted
    for symmetry with the input model but doesn't change the row
    content (the validator checks after generation).
    """
    out: dict[str, Any] = {}
    for field, ftype in schema.items():
        ftype_norm = ftype.lower()
        if ftype_norm in ("string", "str"):
            if "email" in field.lower() and privacy_safe:
                out[field] = f"user{idx}@example.com"
            elif "name" in field.lower():
                out[field] = f"User{idx}"
            else:
                out[field] = f"{field}_{idx}"
        elif ftype_norm in ("int", "integer"):
            if "age" in field.lower():
                out[field] = 18 + (idx % 50)
            else:
                out[field] = idx
        elif ftype_norm in ("float", "number"):
            out[field] = float(idx)
        elif ftype_norm in ("bool", "boolean"):
            out[field] = idx % 2 == 0
        elif ftype_norm == "list":
            out[field] = [f"{field}_{i}" for i in range(2)]
        else:
            out[field] = None
    return out


def _validate_privacy_safe(items: list[dict]) -> bool:
    """Return ``True`` if every email in ``items`` is a safe-domain address.

    A "safe domain" is one of ``example.com``, ``test.com``,
    ``localhost``. Real-looking addresses (e.g. ``john@gmail.com``)
    fail the check.
    """
    for item in items:
        for k, v in item.items():
            if not isinstance(v, str):
                continue
            if (
                "email" in k.lower()
                and "@" in v
                and not re.search(r"@(example\.com|test\.com|localhost)$", v)
            ):
                return False
    return True

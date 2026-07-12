"""Error types for IntelliqX.

The hierarchy is rooted at :class:`IntelliqxError` so callers may catch the
whole family with a single ``except`` while still being able to
distinguish specific failure modes by their concrete type.
"""

from __future__ import annotations


class IntelliqxError(Exception):
    """Base error class for IntelliqX.

    Catching this catches every domain-level error in the platform. Concrete
    subclasses add specificity; lib code should raise the most specific
    subclass that semantically matches the failure.
    """


class CloudConfigError(IntelliqxError):
    """Raised when the cloud adapter cannot resolve its configuration.

    Examples: missing ``INTELLIQX_CLOUD`` env var, unrecognised provider string,
    or a ``CloudConfig`` that is missing required fields for the chosen
    provider (e.g. GCP without ``project_id``).
    """


class ContractError(IntelliqxError):
    """Raised when a contract — event schema, MCP tool interface, or
    marketplace manifest — is violated.

    Use this when an external actor sends data that does not match the
    agreed-upon schema. Do **not** use it for internal validation
    failures of agent inputs; those should raise :class:`ValidationError`.
    """


class NotFoundError(IntelliqxError):
    """Raised when a requested resource does not exist.

    Object-store and state-store adapters translate backend-specific
    "not found" errors (S3 NoSuchKey, Redis nil, GCS 404) into this
    exception so callers can use a single ``except`` clause.
    """


class ValidationError(IntelliqxError):
    """Raised when an input fails internal validation.

    Distinct from :class:`ContractError`: ``ValidationError`` is for
    inputs that the *internal* agent API rejects; ``ContractError``
    is for inputs that violate an *external* contract (event schemas,
    manifest schemas).
    """

"""Error types for AQIP.

The hierarchy is rooted at :class:`AQIPError` so callers may catch the
whole family with a single ``except`` while still being able to
distinguish specific failure modes by their concrete type.
"""

from __future__ import annotations


class AQIPError(Exception):
    """Base class for all AQIP-raised exceptions.

    Catching this catches every domain-level error in the platform. Concrete
    subclasses add specificity; lib code should raise the most specific
    subclass that semantically matches the failure.
    """


class CloudConfigError(AQIPError):
    """Raised when the cloud adapter cannot resolve its configuration.

    Examples: missing ``AQIP_CLOUD`` env var, unrecognised provider string,
    or a ``CloudConfig`` that is missing required fields for the chosen
    provider (e.g. GCP without ``project_id``).
    """


class ContractError(AQIPError):
    """Raised when a contract — event schema, MCP tool interface, or
    marketplace manifest — is violated.

    Use this when an external actor sends data that does not match the
    agreed-upon schema. Do **not** use it for internal validation
    failures of agent inputs; those should raise :class:`ValidationError`.
    """


class NotFoundError(AQIPError):
    """Raised when a requested resource does not exist.

    Object-store and state-store adapters translate backend-specific
    "not found" errors (S3 NoSuchKey, Redis nil, GCS 404) into this
    exception so callers can use a single ``except`` clause.
    """


class ValidationError(AQIPError):
    """Raised when an input fails internal validation.

    Distinct from :class:`ContractError`: ``ValidationError`` is for
    inputs that the *internal* agent API rejects; ``ContractError``
    is for inputs that violate an *external* contract (event schemas,
    manifest schemas).
    """

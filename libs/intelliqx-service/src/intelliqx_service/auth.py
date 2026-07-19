"""Bearer-token authentication helper.

Single bearer auth, constant-time compare, no surprises.
"""

from __future__ import annotations

API_TOKEN_ENV = "INTELLIQX_API_TOKEN"


def bearer_token_from_header(header: str | None) -> str | None:
    """Return the token from an ``Authorization: Bearer ...`` header."""
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


__all__ = ["API_TOKEN_ENV", "bearer_token_from_header"]

"""Bearer-token authentication helper.

Single bearer auth scheme; the token is supplied via
``Authorization: Bearer <token>``. Any other scheme, missing
header, or empty token is treated as "no token".
"""

from __future__ import annotations

API_TOKEN_ENV = "INTELLIQX_API_TOKEN"

BEARER_SCHEME = "bearer"
HEADER_SEPARATOR = " "


def bearer_token_from_header(header: str | None) -> str | None:
    """Return the bearer token from an ``Authorization`` header.

    Args:
        header: Raw ``Authorization`` header value, or ``None``.

    Returns:
        The token string if the header is well-formed
        (``"Bearer <token>"``); otherwise ``None``.
    """
    if not header:
        return None
    parts = header.split(HEADER_SEPARATOR, 1)
    if len(parts) != 2:
        return None
    scheme, token = parts
    if scheme.lower() != BEARER_SCHEME:
        return None
    token = token.strip()
    return token or None


__all__ = ["API_TOKEN_ENV", "BEARER_SCHEME", "bearer_token_from_header"]

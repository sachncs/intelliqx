"""ID generation and parsing.

Identifiers throughout IntelliqX are 26-character Crockford-base32 ULIDs
(``01HXXXXXXXXXXXXXXXXXXXXXXXX``). They are:

* Lexicographically sortable by creation time (high bits are the UNIX
  millisecond timestamp, low bits are random).
* URL-safe and case-insensitive.
* Compact (fits comfortably in any header, log line, or JSON key).

We use ULIDs instead of UUIDs because (a) their sortable property removes
the need for an extra ``created_at`` field on every entity, and (b) the
high timestamp resolution simplifies log correlation and stream
ordering.
"""

from __future__ import annotations

import re

import ulid

# ULIDs are 26 characters of Crockford base32. The character class is
# intentionally restrictive so the regex can be used as a validator
# without having to spin up the full ulid parser.
ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def new_id() -> str:
    """Return a new ULID as a string.

    Returns:
        A 26-character ULID, freshly minted for the current time.

    Example:
        >>> new_id()[0:10]
        '01HXYZ1234'
    """
    return str(ulid.new())


def parse_id(value: str) -> ulid.ULID:
    """Parse a ULID string into the underlying ``ulid.ULID`` object.

    Args:
        value: A 26-character Crockford-base32 string.

    Returns:
        The parsed :class:`ulid.ULID` instance.

    Raises:
        ValueError: If ``value`` is not a valid ULID. The check is strict:
            the regex rejects any input that is not exactly 26 characters
            drawn from the Crockford alphabet.
    """
    if not ULID_RE.match(value):
        raise ValueError(f"Invalid ULID: {value!r}")
    return ulid.parse(value)


def is_valid_id(value: str) -> bool:
    """Return ``True`` if ``value`` is a syntactically valid ULID.

    This is a non-raising predicate version of :func:`parse_id`, useful
    when validating user-supplied identifiers (path components, query
    parameters) where raising an exception is undesirable.

    Args:
        value: The candidate string.

    Returns:
        ``True`` if ``value`` matches the ULID grammar, ``False`` otherwise.
    """
    return bool(ULID_RE.match(value))

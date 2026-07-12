"""Tenant context management.

The tenant context is stored in a :class:`contextvars.ContextVar` so it
propagates naturally through async tasks and thread-pool workers within
the same logical request scope. We deliberately avoid
:data:`threading.local` because:

* IntelliqX agents are async; ``contextvars`` are the standard way to pass
  per-task state.
* Thread pools used by ``asyncio.to_thread`` need to see the same
  context as the parent task — ``threading.local`` does not support
  that without extra plumbing.
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager

from intelliqx_core.models import TenantContext

# Single, package-wide ContextVar. The default of ``None`` is intentional:
# code that needs a tenant must either receive one or set one explicitly.
_CTX: contextvars.ContextVar[TenantContext | None] = contextvars.ContextVar(
    "intelliqx_tenant_ctx", default=None
)


def current_tenant() -> TenantContext | None:
    """Return the active :class:`TenantContext`, or ``None`` if unset.

    Returns:
        The current tenant context for the running task, or ``None`` if
        no context has been bound.
    """
    return _CTX.get()


@contextmanager
def with_tenant(tenant: TenantContext) -> Iterator[TenantContext]:
    """Bind a tenant context for the duration of the block.

    Use this in CLI tools, background workers, and any code that doesn't
    receive a tenant through an agent invocation.

    Args:
        tenant: The context to bind.

    Yields:
        The bound context (for convenience).

    Example:
        >>> with with_tenant(TenantContext(tenant_id="t1")):
        ...     assert current_tenant().tenant_id == "t1"
    """
    token = _CTX.set(tenant)
    try:
        yield tenant
    finally:
        _CTX.reset(token)


class TenantResolver:
    """Build a :class:`TenantContext` from a request's authentication data.

    Two common transports are supported:

    * A signed JWT whose claims include ``tid`` (tenant id, required),
      ``sub`` (user id, optional), ``roles`` (list or comma-separated
      string, optional), and ``trace_id`` (optional).
    * Plain HTTP headers (``X-IntelliqX-Tenant``, ``X-IntelliqX-User``,
      ``X-Trace-Id``). Used by service-to-service callers and the local
      dev API.
    """

    @staticmethod
    def from_jwt_claims(claims: dict) -> TenantContext:
        """Build a context from verified JWT claims.

        Args:
            claims: The decoded JWT claim set.

        Returns:
            A new :class:`TenantContext`.

        Raises:
            ValueError: If the ``tid`` (or ``tenant_id``) claim is missing.
        """
        tid = claims.get("tid") or claims.get("tenant_id")
        if not tid:
            raise ValueError("JWT missing tenant claim 'tid'")
        roles = claims.get("roles") or ()
        if isinstance(roles, str):
            roles = tuple(r.strip() for r in roles.split(",") if r.strip())
        return TenantContext(
            tenant_id=str(tid),
            user_id=claims.get("sub"),
            roles=tuple(roles),
            trace_id=claims.get("trace_id"),
        )

    @staticmethod
    def from_headers(headers: dict[str, str]) -> TenantContext:
        """Build a context from HTTP headers.

        Lookup is case-insensitive on the header names.

        Args:
            headers: A mapping of header name to value (typically
                ``request.headers`` from FastAPI/Starlette).

        Returns:
            A new :class:`TenantContext`.

        Raises:
            ValueError: If ``X-IntelliqX-Tenant`` is missing.
        """
        # Normalise once for case-insensitive lookups.
        lower = {k.lower(): v for k, v in headers.items()}
        tid = lower.get("x-intelliqx-tenant")
        if not tid:
            raise ValueError("Missing X-IntelliqX-Tenant header")
        return TenantContext(
            tenant_id=tid,
            user_id=lower.get("x-intelliqx-user"),
            trace_id=lower.get("x-trace-id"),
        )

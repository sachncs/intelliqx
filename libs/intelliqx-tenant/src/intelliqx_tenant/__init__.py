"""Tenant context and isolation.

Two primitives:

* :class:`TenantContext` — frozen value object carrying the active
  tenant's identity. Every agent invocation receives one and threads
  it through the call stack.
* :class:`IsolationEnforcer` — runtime guard that raises
  :class:`TenantViolation` if a code path tries to read or mutate a
  resource owned by a different tenant.

The package also exposes :func:`current_tenant` / :func:`with_tenant`
helpers for code that wants to bind a tenant to a logical scope without
threading it explicitly. These are typically used in CLI tools and
background workers.
"""

from aqip_tenant.context import TenantResolver, current_tenant, with_tenant
from aqip_tenant.isolation import IsolationEnforcer, TenantViolation

__all__ = [
    "IsolationEnforcer",
    "TenantResolver",
    "TenantViolation",
    "current_tenant",
    "with_tenant",
]

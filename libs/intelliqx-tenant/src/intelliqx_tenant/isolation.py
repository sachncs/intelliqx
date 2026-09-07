"""Tenant isolation enforcement.

The :class:`IsolationEnforcer` is a lightweight runtime guard. It is
*not* an authorisation system; it is the last line of defence that
catches bugs (and a few malicious paths) where a piece of code
mistakenly touches a resource owned by another tenant.

Use it as a per-request object in API handlers:

    enforcer = IsolationEnforcer(current_tenant())
    enforcer.check_object(resource)

The enforcer raises :class:`TenantViolation` on any mismatch.

Security / isolation guarantees:

* The enforcer is a **defense-in-depth** layer, not the primary
  access-control mechanism. It catches accidental cross-tenant
  leaks (bugs), not intentional privilege escalation. The primary
  access control should be enforced at the API gateway / auth
  middleware layer before the request reaches agent code.
* ``check(resource_tenant_id)`` raises ``TenantViolation`` when a
  non-``None`` tenant id differs from the current tenant. A
  ``None`` value is treated as "not tenant-scoped" and is
  allowed — this is intentional for global resources (e.g. the
  OKF catalog's ``_global`` tenant).
* ``namespace(key)`` prefixes a key with the current tenant id,
  producing ``"{tenant_id}/{key}"``. Use this for stores that do
  not natively enforce tenant isolation (object store, state store,
  KG ids). The namespace prevents key collisions between tenants
  but does **not** prevent a tenant from constructing a key that
  includes another tenant's prefix — that is the job of the
  authorization layer.
* The enforcer is **stateless** except for the bound tenant; one
  instance per request avoids stale-tenant bugs across request
  boundaries.
"""

from __future__ import annotations

from typing import Any

from intelliqx_core.models import TenantContext


class TenantViolation(Exception):
    """Raised when code touches a resource owned by another tenant.

    Catching this lets callers turn a tenant leak into a recoverable
    error (e.g. 404) rather than a 500.
    """


class IsolationEnforcer:
    """Validate that resources accessed belong to the current tenant.

    The enforcer is stateless except for the bound tenant; one instance
    should be created per request.

    Args:
        tenant: The active :class:`TenantContext`. The enforcer
            compares every checked resource against ``tenant.tenant_id``.
    """

    def __init__(self, tenant: TenantContext) -> None:
        self.tenant = tenant

    def check(self, resource_tenant_id: str | None) -> None:
        """Verify a tenant id matches the current tenant.

        Args:
            resource_tenant_id: The tenant id of the resource being
                accessed. A value of ``None`` is treated as "not
                tenant-scoped" and is allowed.

        Raises:
            TenantViolation: If ``resource_tenant_id`` is non-``None``
                and differs from ``self.tenant.tenant_id``.
        """
        if resource_tenant_id is None:
            return
        if resource_tenant_id != self.tenant.tenant_id:
            raise TenantViolation(
                f"Tenant {self.tenant.tenant_id!r} attempted to access resource "
                f"owned by {resource_tenant_id!r}"
            )

    def check_object(self, obj: Any, *, tenant_attr: str = "tenant_id") -> None:
        """Verify an object's ``tenant_attr`` matches the current tenant.

        Args:
            obj: Any object exposing a tenant identifier attribute.
            tenant_attr: The attribute name to read (default
                ``"tenant_id"``).

        Raises:
            TenantViolation: If the attribute exists and its value
                differs from the current tenant.
        """
        rid = getattr(obj, tenant_attr, None)
        self.check(rid)

    def namespace(self, key: str) -> str:
        """Prefix a key with the current tenant id.

        Use this for object-store keys, state-store keys, KG ids, and
        any other resource where the underlying store does not already
        enforce tenant isolation.

        Args:
            key: The un-namespaced key.

        Returns:
            ``"{tenant_id}/{key}"``.
        """
        return f"{self.tenant.tenant_id}/{key}"

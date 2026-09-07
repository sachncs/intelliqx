"""Tests for intelliqx-tenant."""

import pytest
from intelliqx_core.models import TenantContext
from intelliqx_tenant.context import TenantResolver, current_tenant, with_tenant
from intelliqx_tenant.isolation import IsolationEnforcer, TenantViolation


@pytest.mark.unit
def test_resolver_from_jwt():
    t = TenantResolver.from_jwt_claims({"tid": "t1", "sub": "u1", "roles": "admin,user"})
    assert t.tenant_id == "t1"
    assert t.user_id == "u1"
    assert "admin" in t.roles


@pytest.mark.unit
def test_resolver_from_jwt_missing():
    with pytest.raises(ValueError):
        TenantResolver.from_jwt_claims({})


@pytest.mark.unit
def test_resolver_from_headers():
    t = TenantResolver.from_headers({"X-IntelliqX-Tenant": "t1", "X-IntelliqX-User": "u1"})
    assert t.tenant_id == "t1"
    assert t.user_id == "u1"


@pytest.mark.unit
def test_resolver_from_headers_missing():
    with pytest.raises(ValueError):
        TenantResolver.from_headers({})


@pytest.mark.unit
def test_isolation_enforcer_check():
    e = IsolationEnforcer(TenantContext(tenant_id="t1"))
    e.check("t1")
    e.check(None)
    with pytest.raises(TenantViolation):
        e.check("t2")


@pytest.mark.unit
def test_isolation_enforcer_namespace():
    e = IsolationEnforcer(TenantContext(tenant_id="t1"))
    assert e.namespace("k") == "t1/k"


@pytest.mark.unit
def test_isolation_enforcer_check_object():
    e = IsolationEnforcer(TenantContext(tenant_id="t1"))

    class _R:
        tenant_id = "t1"

    e.check_object(_R())
    with pytest.raises(TenantViolation):

        class _Bad:
            tenant_id = "t2"

        e.check_object(_Bad())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_with_tenant_context_manager():
    t = TenantContext(tenant_id="t1")
    assert current_tenant() is None
    with with_tenant(t):
        assert current_tenant() is t
    assert current_tenant() is None

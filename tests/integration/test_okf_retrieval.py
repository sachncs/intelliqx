"""Integration test for OKF retrieval pipeline.

Tests the full round-trip: bundle → catalog → bootstrap → vector index → search.
"""

from pathlib import Path

import pytest
from intelliqx_llm.client import FakeLLMClient, set_llm_client
from intelliqx_okf.bundle import load_bundle
from intelliqx_okf.catalog import OKFCatalog, get_catalog, reset_catalog, set_catalog
from intelliqx_okf.retrieval import bootstrap_okf_retrieval
from intelliqx_vector.index import set_vector_index
from intelliqx_vector.sqlite_vec_index import SqliteVecIndex


def write_concept(path: Path, fm: dict, body: str = "Body text.\n") -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    fm_text = yaml.safe_dump(fm, sort_keys=False).rstrip("\n")
    path.write_text(f"---\n{fm_text}\n---\n\n{body}", encoding="utf-8")


@pytest.fixture(autouse=True)
def setup_singletons(tmp_path):
    """Set up LLM, vector index, and OKF catalog singletons."""
    llm = FakeLLMClient(dim=128)
    set_llm_client(llm)

    vec_idx = SqliteVecIndex(db_path=str(tmp_path / "vec.db"), dim=128)
    set_vector_index(vec_idx)

    catalog = OKFCatalog(db_path=str(tmp_path / "okf.db"), dim=128)
    reset_catalog()
    set_catalog(catalog)

    yield

    reset_catalog()


@pytest.mark.integration
def test_bootstrap_single_tenant(tmp_path):
    """Bootstrap a single tenant's bundle and search for concepts."""
    bundle_dir = tmp_path / "alpha"
    write_concept(
        bundle_dir / "auth" / "login.md",
        {
            "type": "API Endpoint",
            "title": "Login API",
            "description": "Authenticate a user with email and password.",
            "tags": ["auth", "login"],
        },
        body="The login endpoint accepts a POST request with email and password fields.\n",
    )
    write_concept(
        bundle_dir / "auth" / "logout.md",
        {
            "type": "API Endpoint",
            "title": "Logout API",
            "description": "Terminate the current session.",
            "tags": ["auth", "session"],
        },
        body="The logout endpoint invalidates the session token.\n",
    )

    bundle = load_bundle(bundle_dir)
    catalog = get_catalog()

    count = catalog.build_catalog(bundle, tenant_id="alpha")
    assert count == 2

    results = catalog.search("login", tenant_id="alpha", top_k=5)
    assert len(results) > 0
    assert results[0].concept_id == "auth/login"

    results_beta = catalog.search("login", tenant_id="beta", top_k=5)
    assert len(results_beta) == 0


@pytest.mark.integration
def test_bootstrap_multi_tenant(tmp_path):
    """Bootstrap two tenants and verify isolation."""
    for tenant, concept_name in [("alpha", "alpha-concept"), ("beta", "beta-concept")]:
        bundle_dir = tmp_path / tenant
        write_concept(
            bundle_dir / f"{concept_name}.md",
            {
                "type": "Data Model",
                "title": f"{tenant.title()} Concept",
                "description": f"A concept belonging to {tenant}.",
                "tags": [tenant],
            },
            body=f"This is the {tenant} concept body.\n",
        )

    alpha_bundle = load_bundle(tmp_path / "alpha")
    beta_bundle = load_bundle(tmp_path / "beta")

    catalog = get_catalog()
    catalog.build_catalog(alpha_bundle, tenant_id="alpha")
    catalog.build_catalog(beta_bundle, tenant_id="beta")

    alpha_results = catalog.search("concept", tenant_id="alpha", top_k=5)
    assert len(alpha_results) == 1
    assert alpha_results[0].concept_id == "alpha-concept"

    beta_results = catalog.search("concept", tenant_id="beta", top_k=5)
    assert len(beta_results) == 1
    assert beta_results[0].concept_id == "beta-concept"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bootstrap_and_search(tmp_path):
    """Full bootstrap + search round-trip."""
    bundle_dir = tmp_path / "tenant1"
    write_concept(
        bundle_dir / "config" / "timeout.md",
        {
            "type": "Config Key",
            "title": "Timeout Configuration",
            "description": "Maximum wait time in seconds.",
            "tags": ["config", "performance"],
        },
        body="The timeout value controls how long the client waits before retrying.\n",
    )

    count = await bootstrap_okf_retrieval(
        {"tenant1": bundle_dir}, db_path=str(tmp_path / "catalog.db"), dim=128
    )
    assert count == 1

    catalog = get_catalog()
    results = catalog.search("timeout", tenant_id="tenant1", top_k=5)
    assert len(results) == 1
    assert results[0].concept_id == "config/timeout"


@pytest.mark.integration
def test_type_filter_integration(tmp_path):
    """Search with type filter."""
    bundle_dir = tmp_path / "mixed"
    write_concept(
        bundle_dir / "endpoint.md",
        {
            "type": "API Endpoint",
            "title": "Create Order",
            "description": "Create a new order.",
            "tags": ["orders"],
        },
    )
    write_concept(
        bundle_dir / "model.md",
        {
            "type": "Data Model",
            "title": "Order Model",
            "description": "Represents a customer order.",
            "tags": ["orders"],
        },
    )

    bundle = load_bundle(bundle_dir)
    catalog = get_catalog()
    catalog.build_catalog(bundle, tenant_id="mixed")

    all_results = catalog.search("order", tenant_id="mixed", top_k=10)
    assert len(all_results) == 2

    endpoint_results = catalog.search(
        "order", tenant_id="mixed", type_filter=["API Endpoint"], top_k=10
    )
    assert len(endpoint_results) == 1
    assert endpoint_results[0].concept_id == "endpoint"


@pytest.mark.integration
def test_tag_filter_integration(tmp_path):
    """Search with tag filter."""
    bundle_dir = tmp_path / "tags"
    write_concept(
        bundle_dir / "a.md",
        {
            "type": "Config Key",
            "title": "Feature Flag A",
            "description": "Enables feature A.",
            "tags": ["feature-flags", "experimental"],
        },
    )
    write_concept(
        bundle_dir / "b.md",
        {
            "type": "Config Key",
            "title": "Feature Flag B",
            "description": "Enables feature B.",
            "tags": ["feature-flags"],
        },
    )

    bundle = load_bundle(bundle_dir)
    catalog = get_catalog()
    catalog.build_catalog(bundle, tenant_id="tags")

    results = catalog.search("feature", tenant_id="tags", tag_filter=["experimental"], top_k=10)
    assert len(results) == 1
    assert results[0].concept_id == "a"


@pytest.mark.integration
def test_fts_punctuation_in_search(tmp_path):
    """FTS search with punctuation in query."""
    bundle_dir = tmp_path / "punct"
    write_concept(
        bundle_dir / "api.md",
        {
            "type": "API Endpoint",
            "title": "GET /users/:id",
            "description": "Fetch a user by ID.",
            "tags": ["api", "users"],
        },
        body="The endpoint accepts a user ID path parameter.\n",
    )

    bundle = load_bundle(bundle_dir)
    catalog = get_catalog()
    catalog.build_catalog(bundle, tenant_id="punct")

    results = catalog.search("GET /users/:id", tenant_id="punct", top_k=5)
    assert len(results) == 1
    assert results[0].concept_id == "api"

    results2 = catalog.search("user ID?", tenant_id="punct", top_k=5)
    assert len(results2) == 1


@pytest.mark.integration
def test_structured_where_alias(tmp_path):
    """Structured filters use table alias to avoid ambiguous columns."""
    bundle_dir = tmp_path / "alias"
    write_concept(
        bundle_dir / "x.md",
        {
            "type": "Event",
            "title": "Order Placed",
            "description": "Emitted when an order is placed.",
            "tags": ["events", "orders"],
        },
    )
    write_concept(
        bundle_dir / "y.md",
        {
            "type": "Event",
            "title": "Payment Received",
            "description": "Emitted when payment is received.",
            "tags": ["events", "payments"],
        },
    )

    bundle = load_bundle(bundle_dir)
    catalog = get_catalog()
    catalog.build_catalog(bundle, tenant_id="alias")

    results = catalog.search(
        "order", tenant_id="alias", type_filter=["Event"], tag_filter=["orders"], top_k=5
    )
    assert len(results) == 1
    assert results[0].concept_id == "x"


@pytest.mark.integration
def test_empty_query_with_type_filter(tmp_path):
    """Empty query with type filter returns all matching concepts."""
    bundle_dir = tmp_path / "empty"
    write_concept(
        bundle_dir / "a.md",
        {
            "type": "Guide",
            "title": "Getting Started",
            "description": "How to get started.",
            "tags": ["docs"],
        },
    )
    write_concept(
        bundle_dir / "b.md",
        {
            "type": "API Endpoint",
            "title": "Health Check",
            "description": "Returns 200 OK.",
            "tags": ["api"],
        },
    )

    bundle = load_bundle(bundle_dir)
    catalog = get_catalog()
    catalog.build_catalog(bundle, tenant_id="empty")

    results = catalog.search("", tenant_id="empty", type_filter=["Guide"], top_k=10)
    assert len(results) == 1
    assert results[0].concept_id == "a"


@pytest.mark.integration
def test_empty_query_no_filter_returns_all(tmp_path):
    """Empty query with no filter returns all non-reserved concepts."""
    bundle_dir = tmp_path / "all"
    write_concept(
        bundle_dir / "a.md", {"type": "Guide", "title": "A", "description": "A.", "tags": []}
    )
    write_concept(
        bundle_dir / "b.md", {"type": "Guide", "title": "B", "description": "B.", "tags": []}
    )

    bundle = load_bundle(bundle_dir)
    catalog = get_catalog()
    catalog.build_catalog(bundle, tenant_id="all")

    results = catalog.search("", tenant_id="all", top_k=10)
    assert len(results) == 2


@pytest.mark.integration
def test_vector_weight_validation():
    """Vector weight must be in [0, 1]."""
    catalog = get_catalog()
    with pytest.raises(ValueError, match="vector_weight must be in"):
        catalog.search("q", tenant_id="x", vector_weight=-0.1)
    with pytest.raises(ValueError, match="vector_weight must be in"):
        catalog.search("q", tenant_id="x", vector_weight=1.1)

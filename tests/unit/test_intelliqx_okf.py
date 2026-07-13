"""Tests for intelliqx-okf: reader, writer, validator, bundle, catalog."""

from pathlib import Path

import pytest
from intelliqx_okf.bundle import OKFBundle, load_bundle
from intelliqx_okf.concept import OKFConcept, load_concept, save_concept
from intelliqx_okf.frontmatter import OKFFrontmatter
from intelliqx_okf.validator import (
    OKFValidationError,
    ValidationIssue,
    ValidationResult,
    validate_bundle,
    validate_concept,
)


def _write_concept(path: Path, fm: dict, body: str = "Body text.\n") -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    fm_text = yaml.safe_dump(fm, sort_keys=False).rstrip("\n")
    path.write_text(f"---\n{fm_text}\n---\n\n{body}", encoding="utf-8")


# --- Frontmatter ---------------------------------------------------------


@pytest.mark.unit
def test_frontmatter_round_trip():
    fm = OKFFrontmatter(
        type="API Endpoint",
        title="Create User",
        description="Creates a new user",
        tags=["auth", "users"],
    )
    dumped = fm.model_dump_okf()
    assert dumped["type"] == "API Endpoint"
    assert dumped["tags"] == ["auth", "users"]
    fm2 = OKFFrontmatter(**dumped)
    assert fm2.type == "API Endpoint"
    assert fm2.tags == ["auth", "users"]


@pytest.mark.unit
def test_frontmatter_required_type():
    from pydantic import ValidationError as PydanticValidationError

    with pytest.raises(PydanticValidationError):
        OKFFrontmatter(type="")


@pytest.mark.unit
def test_frontmatter_extras_preserved():
    fm = OKFFrontmatter(type="X", extra_fields={"custom_key": "value"})
    dumped = fm.model_dump_okf()
    assert dumped["custom_key"] == "value"
    fm2 = OKFFrontmatter(**dumped)
    assert fm2.custom_key == "value"


# --- Concept reader / writer -------------------------------------------


@pytest.mark.unit
def test_load_concept_minimal(tmp_path: Path):
    p = tmp_path / "test.md"
    _write_concept(p, {"type": "Endpoint"}, "Some body.\n")
    c = load_concept(p)
    assert c.frontmatter.type == "Endpoint"
    assert "Some body" in c.body
    assert c.concept_id == str(p).removesuffix(".md")


@pytest.mark.unit
def test_load_concept_missing_type_raises(tmp_path: Path):
    p = tmp_path / "bad.md"
    p.write_text("---\ntitle: X\n---\nBody", encoding="utf-8")
    with pytest.raises(ValueError, match="type"):
        load_concept(p)


@pytest.mark.unit
def test_save_concept_round_trip(tmp_path: Path):
    p = tmp_path / "out.md"
    c = OKFConcept(
        concept_id="out",
        frontmatter=OKFFrontmatter(type="Table", title="Users"),
        body="The users table.\n",
    )
    save_concept(c, p)
    c2 = load_concept(p)
    assert c2.frontmatter.type == "Table"
    assert c2.frontmatter.title == "Users"
    assert "users table" in c2.body.lower()


@pytest.mark.unit
def test_load_concept_sections(tmp_path: Path):
    p = tmp_path / "sections.md"
    p.write_text(
        "---\ntype: X\n---\nIntro\n\n# Schema\nid INT\n# Examples\nfoo\n", encoding="utf-8"
    )
    c = load_concept(p)
    headings = [s.heading for s in c.sections]
    assert "" in headings
    assert "Schema" in headings
    assert "Examples" in headings


@pytest.mark.unit
def test_load_concept_links(tmp_path: Path):
    p = tmp_path / "links.md"
    p.write_text(
        "---\ntype: X\n---\nSee [other](/tables/other.md) and [ext](https://example.com).\n",
        encoding="utf-8",
    )
    c = load_concept(p)
    texts = {link.text for link in c.links}
    assert "other" in texts
    assert "ext" in texts


@pytest.mark.unit
def test_load_concept_citations(tmp_path: Path):
    p = tmp_path / "cites.md"
    p.write_text(
        "---\ntype: X\n---\nBody\n\n# Citations\n1. [RFC 7231](https://example.com/rfc)\n",
        encoding="utf-8",
    )
    c = load_concept(p)
    assert len(c.citations) == 1
    assert c.citations[0].label == "RFC 7231"


# --- Bundle loader ------------------------------------------------------


@pytest.mark.unit
def test_bundle_walks_tree(tmp_path: Path):
    _write_concept(tmp_path / "index.md", {"type": "Index", "okf_version": "0.1"})
    _write_concept(tmp_path / "users.md", {"type": "Table"}, "Users table.")
    _write_concept(tmp_path / "sub" / "roles.md", {"type": "Table"}, "Roles.")
    bundle = load_bundle(tmp_path)
    assert len(bundle) == 3
    assert "index" in bundle.reserved
    assert "users" in bundle.concepts
    assert "sub/roles" in bundle.concepts


@pytest.mark.unit
def test_bundle_collects_errors(tmp_path: Path):
    p = tmp_path / "bad.md"
    p.write_text("---\ntitle: X\n---\n", encoding="utf-8")
    _write_concept(tmp_path / "ok.md", {"type": "X"})
    bundle = load_bundle(tmp_path)
    assert len(bundle.errors) == 1
    assert "bad.md" in str(bundle.errors[0][0])


@pytest.mark.unit
def test_link_resolver_absolute_and_relative(tmp_path: Path):
    _write_concept(tmp_path / "a.md", {"type": "X"}, "[link b](/b.md)")
    _write_concept(tmp_path / "b.md", {"type": "Y"}, "Target.")
    bundle = load_bundle(tmp_path)
    from intelliqx_okf.bundle import OKFLinkResolver

    resolver = OKFLinkResolver(bundle)
    edges = resolver.edges()
    assert any(e.source == "a" and e.target == "b" for e in edges)
    assert resolver.unresolved_count == 0


@pytest.mark.unit
def test_link_resolver_skips_external(tmp_path: Path):
    _write_concept(tmp_path / "a.md", {"type": "X"}, "[ext](https://example.com)")
    bundle = load_bundle(tmp_path)
    from intelliqx_okf.bundle import OKFLinkResolver

    resolver = OKFLinkResolver(bundle)
    edges = resolver.edges()
    assert len(edges) == 0


# --- Validator -----------------------------------------------------------


@pytest.mark.unit
def test_validate_concept_valid(tmp_path: Path):
    p = tmp_path / "good.md"
    _write_concept(p, {"type": "Endpoint", "title": "Create"}, "Does something.")
    c = load_concept(p)
    result = validate_concept(c)
    assert result.ok
    assert len(result.errors) == 0


@pytest.mark.unit
def test_validate_concept_missing_title(tmp_path: Path):
    p = tmp_path / "no_title.md"
    _write_concept(p, {"type": "X"}, "Body.")
    c = load_concept(p)
    result = validate_concept(c)
    assert result.ok  # title+description missing is a warning, not error


@pytest.mark.unit
def test_validate_concept_empty_body(tmp_path: Path):
    p = tmp_path / "empty.md"
    p.write_text("---\ntype: X\n---\n", encoding="utf-8")
    c = load_concept(p)
    result = validate_concept(c)
    assert not any(i.level == "error" for i in result.issues)
    assert any("empty" in i.message for i in result.warnings)


@pytest.mark.unit
def test_validate_bundle_valid(tmp_path: Path):
    _write_concept(tmp_path / "index.md", {"type": "Index"})
    _write_concept(tmp_path / "a.md", {"type": "X"}, "Body.")
    bundle = load_bundle(tmp_path)
    result = validate_bundle(bundle)
    assert result.ok


@pytest.mark.unit
def test_validate_bundle_missing_index(tmp_path: Path):
    _write_concept(tmp_path / "a.md", {"type": "X"}, "Body.")
    bundle = load_bundle(tmp_path)
    result = validate_bundle(bundle)
    assert any("index.md" in i.message for i in result.warnings)


@pytest.mark.unit
def test_validate_bundle_broken_links(tmp_path: Path):
    _write_concept(tmp_path / "a.md", {"type": "X"}, "[missing](/nonexistent.md)")
    bundle = load_bundle(tmp_path)
    result = validate_bundle(bundle)
    assert any("unresolved" in i.message for i in result.warnings)


@pytest.mark.unit
def test_validation_error_exception():
    r = ValidationResult(issues=[ValidationIssue("error", "x", "bad")])
    exc = OKFValidationError(r)
    assert "1 issue" in str(exc)
    assert exc.result is r


# --- Catalog basics (FTS-only, no sqlite-vec required) ------------------


@pytest.mark.unit
def test_catalog_build_and_search():
    from intelliqx_okf.catalog import OKFCatalog

    cat = OKFCatalog()
    bundle = OKFBundle(
        root=Path("."),
        concepts={
            "a": OKFConcept(
                concept_id="a",
                frontmatter=OKFFrontmatter(type="Endpoint", title="Get Users"),
                body="Returns all users.",
            ),
            "b": OKFConcept(
                concept_id="b",
                frontmatter=OKFFrontmatter(type="Table", title="Orders"),
                body="Customer orders.",
            ),
        },
    )
    n = cat.build_catalog(bundle)
    assert n == 2
    hits = cat.search("users")
    assert any(h.concept_id == "a" for h in hits)
    cat.close()


@pytest.mark.unit
def test_catalog_type_filter():
    from intelliqx_okf.catalog import OKFCatalog

    cat = OKFCatalog()
    bundle = OKFBundle(
        root=Path("."),
        concepts={
            "a": OKFConcept(
                concept_id="a",
                frontmatter=OKFFrontmatter(type="Endpoint", title="A"),
                body="Body A.",
            ),
            "b": OKFConcept(
                concept_id="b", frontmatter=OKFFrontmatter(type="Table", title="B"), body="Body B."
            ),
        },
    )
    cat.build_catalog(bundle)
    hits = cat.search("body", type_filter=["Endpoint"])
    assert len(hits) == 1
    assert hits[0].type == "Endpoint"
    cat.close()


@pytest.mark.unit
def test_catalog_singleton():
    from intelliqx_okf.catalog import OKFCatalog, get_catalog, reset_catalog, set_catalog

    cat = OKFCatalog()
    set_catalog(cat)
    assert get_catalog() is cat
    reset_catalog()
    cat2 = get_catalog()
    assert cat2 is not cat
    cat2.close()
    reset_catalog()


@pytest.mark.unit
def test_catalog_list_types_and_tags():
    from intelliqx_okf.catalog import OKFCatalog

    cat = OKFCatalog()
    bundle = OKFBundle(
        root=Path("."),
        concepts={
            "a": OKFConcept(
                concept_id="a",
                frontmatter=OKFFrontmatter(type="Endpoint", title="A", tags=["auth"]),
                body="Body.",
            ),
            "b": OKFConcept(
                concept_id="b",
                frontmatter=OKFFrontmatter(type="Table", title="B", tags=["auth", "data"]),
                body="Body.",
            ),
        },
    )
    cat.build_catalog(bundle)
    assert set(cat.list_types()) == {"Endpoint", "Table"}
    assert set(cat.list_tags()) == {"auth", "data"}
    cat.close()


# --- Catalog: tenant scoping --------------------------------------------


@pytest.mark.unit
def test_catalog_tenant_isolation():
    from intelliqx_okf.catalog import OKFCatalog

    cat = OKFCatalog()
    bundle_a = OKFBundle(
        root=Path("."),
        concepts={
            "a": OKFConcept(
                concept_id="a",
                frontmatter=OKFFrontmatter(type="X", title="Tenant A doc"),
                body="Body A.",
            )
        },
    )
    bundle_b = OKFBundle(
        root=Path("."),
        concepts={
            "b": OKFConcept(
                concept_id="b",
                frontmatter=OKFFrontmatter(type="X", title="Tenant B doc"),
                body="Body B.",
            )
        },
    )
    cat.build_catalog(bundle_a, tenant_id="tA")
    cat.build_catalog(bundle_b, tenant_id="tB")
    hits_a = cat.search("doc", tenant_id="tA")
    assert all(h.concept_id == "a" for h in hits_a)
    hits_b = cat.search("doc", tenant_id="tB")
    assert all(h.concept_id == "b" for h in hits_b)
    cat.close()


@pytest.mark.unit
def test_catalog_tenant_list_types():
    from intelliqx_okf.catalog import OKFCatalog

    cat = OKFCatalog()
    cat.build_catalog(
        OKFBundle(
            root=Path("."),
            concepts={
                "a": OKFConcept(
                    concept_id="a",
                    frontmatter=OKFFrontmatter(type="Endpoint", title="A"),
                    body="Body.",
                )
            },
        ),
        tenant_id="t1",
    )
    cat.build_catalog(
        OKFBundle(
            root=Path("."),
            concepts={
                "b": OKFConcept(
                    concept_id="b",
                    frontmatter=OKFFrontmatter(type="Table", title="B"),
                    body="Body.",
                )
            },
        ),
        tenant_id="t2",
    )
    assert set(cat.list_types(tenant_id="t1")) == {"Endpoint"}
    assert set(cat.list_types(tenant_id="t2")) == {"Table"}
    cat.close()


# --- Catalog: FTS tokenization ------------------------------------------


@pytest.mark.unit
def test_catalog_fts_punctuation_query():
    from intelliqx_okf.catalog import OKFCatalog

    cat = OKFCatalog()
    bundle = OKFBundle(
        root=Path("."),
        concepts={
            "a": OKFConcept(
                concept_id="a",
                frontmatter=OKFFrontmatter(type="X", title="User API"),
                body="The user API handles authentication.",
            )
        },
    )
    cat.build_catalog(bundle)
    # These queries used to produce FTS5 syntax errors
    hits1 = cat.search("hello-world")
    assert isinstance(hits1, list)
    hits2 = cat.search("how do I test?")
    assert isinstance(hits2, list)
    hits3 = cat.search('"quoted" phrase')
    assert isinstance(hits3, list)
    cat.close()


# --- Catalog: empty query with filters ----------------------------------


@pytest.mark.unit
def test_catalog_empty_query_type_filter():
    from intelliqx_okf.catalog import OKFCatalog

    cat = OKFCatalog()
    bundle = OKFBundle(
        root=Path("."),
        concepts={
            "a": OKFConcept(
                concept_id="a",
                frontmatter=OKFFrontmatter(type="Endpoint", title="A"),
                body="Body A.",
            ),
            "b": OKFConcept(
                concept_id="b", frontmatter=OKFFrontmatter(type="Table", title="B"), body="Body B."
            ),
        },
    )
    cat.build_catalog(bundle)
    hits = cat.search("", type_filter=["Endpoint"])
    assert len(hits) == 1
    assert hits[0].type == "Endpoint"
    cat.close()


# --- Catalog: tag filter -------------------------------------------------


@pytest.mark.unit
def test_catalog_tag_filter():
    from intelliqx_okf.catalog import OKFCatalog

    cat = OKFCatalog()
    bundle = OKFBundle(
        root=Path("."),
        concepts={
            "a": OKFConcept(
                concept_id="a",
                frontmatter=OKFFrontmatter(type="X", title="A", tags=["auth"]),
                body="Auth related.",
            ),
            "b": OKFConcept(
                concept_id="b",
                frontmatter=OKFFrontmatter(type="X", title="B", tags=["data"]),
                body="Data related.",
            ),
        },
    )
    cat.build_catalog(bundle)
    hits = cat.search("related", tag_filter=["auth"])
    assert len(hits) == 1
    assert hits[0].concept_id == "a"
    cat.close()


# --- Catalog: vector_weight validation ----------------------------------


@pytest.mark.unit
def test_catalog_vector_weight_validation():
    from intelliqx_okf.catalog import OKFCatalog

    cat = OKFCatalog()
    with pytest.raises(ValueError, match="vector_weight"):
        cat.search("test", vector_weight=1.5)
    with pytest.raises(ValueError, match="vector_weight"):
        cat.search("test", vector_weight=-0.1)
    cat.close()


# --- Catalog: reserve_reserved -------------------------------------------


@pytest.mark.unit
def test_catalog_reserve_reserved():
    from intelliqx_okf.catalog import OKFCatalog

    cat = OKFCatalog()
    bundle = OKFBundle(
        root=Path("."),
        concepts={
            "index": OKFConcept(
                concept_id="index",
                frontmatter=OKFFrontmatter(type="Index", title="Index"),
                body="Index body.",
            ),
            "a": OKFConcept(
                concept_id="a", frontmatter=OKFFrontmatter(type="X", title="A"), body="Body."
            ),
        },
        reserved={"index"},
    )
    cat.build_catalog(bundle, reserve_reserved=False)
    hits = cat.search("")
    assert len(hits) == 1
    assert hits[0].concept_id == "a"
    cat.build_catalog(bundle, reserve_reserved=True)
    hits2 = cat.search("")
    assert len(hits2) == 2
    cat.close()

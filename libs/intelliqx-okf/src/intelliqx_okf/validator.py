"""OKF concept and bundle validation.

Implements validation for OKF concepts and bundles beyond what Pydantic
enforces on the frontmatter model.  Validators return structured results
so callers can collect all issues in one pass rather than failing fast.

Typical usage::

    from intelliqx_observability.logging import configure_logging, get_logger
    from intelliqx_okf.validator import validate_concept, validate_bundle
    from intelliqx_okf import load_concept, load_bundle

    configure_logging(json_logs=False, component="okf-validator")
    logger = get_logger(__name__)
    concept = load_concept("tables/users.md")
    result = validate_concept(concept)
    if not result.ok:
        for issue in result.issues:
            logger.info("{}", issue)

    bundle = load_bundle("./okf-bundle")
    bundle_result = validate_bundle(bundle)

"""

from __future__ import annotations

from dataclasses import dataclass, field

from intelliqx_core.errors import IntelliqxError

from intelliqx_okf.bundle import OKFBundle
from intelliqx_okf.concept import OKFConcept


class OKFValidationError(IntelliqxError):
    """Raised when an OKF concept or bundle fails validation.

    Carries the structured :class:`ValidationResult` so callers can
    inspect individual issues programmatically.

    Args:
        result: The structured validation result being raised.
            Becomes the exception's ``result`` attribute.
    """

    def __init__(self, result: ValidationResult) -> None:
        self.result = result
        count = len(result.issues)
        super().__init__(f"OKF validation failed with {count} issue(s)")


@dataclass
class ValidationIssue:
    """A single validation issue.

    Attributes:
        level: ``"error"`` (must fix) or ``"warning"`` (advisory).
        path: Stable identifier of the affected concept or file —
            typically ``concept_id`` for concept issues, the file
            path for bundle-level issues.
        message: Human-readable description.
    """

    level: str  # "error" | "warning"
    path: str  # concept_id or file path
    message: str


@dataclass
class ValidationResult:
    """Structured validation result for a concept or bundle.

    Attributes:
        issues: Every issue discovered, in discovery order.
    """

    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """``True`` iff no issue has ``level == "error"``."""
        return not any(i.level == "error" for i in self.issues)

    @property
    def errors(self) -> list[ValidationIssue]:
        """Just the errors."""
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Just the warnings."""
        return [i for i in self.issues if i.level == "warning"]


def validate_concept(concept: OKFConcept) -> ValidationResult:
    """Validate a single OKF concept.

    Checks:
    - Frontmatter ``type`` is non-empty.
    - Concept body is non-empty.
    - Title or description is present (recommended by OKF spec).
    - No duplicate section headings.

    Args:
        concept: The parsed concept to validate.

    Returns:
        A :class:`ValidationResult` containing every issue
        discovered. Empty issues list means the concept passed
        every check.
    """
    issues: list[ValidationIssue] = []
    cid = concept.concept_id

    if not concept.frontmatter.type or not concept.frontmatter.type.strip():
        issues.append(ValidationIssue("error", cid, "frontmatter 'type' must be non-empty"))

    if not concept.body or not concept.body.strip():
        issues.append(ValidationIssue("warning", cid, "concept body is empty"))

    if not concept.frontmatter.title and not concept.frontmatter.description:
        issues.append(ValidationIssue("warning", cid, "neither 'title' nor 'description' is set"))

    headings = [s.heading for s in concept.sections if s.heading]
    seen: set[str] = set()
    for h in headings:
        if h in seen:
            issues.append(ValidationIssue("warning", cid, f"duplicate section heading: '{h}'"))
        seen.add(h)

    return ValidationResult(issues=issues)


def validate_bundle(bundle: OKFBundle) -> ValidationResult:
    """Validate an OKF bundle.

    Checks:
    - No malformed concepts in ``bundle.errors``.
    - All link targets resolve (informational warning for broken links).
    - ``index.md`` is present at the bundle root.
    - Concepts have required ``type`` values.

    Args:
        bundle: The parsed bundle to validate.

    Returns:
        A :class:`ValidationResult` aggregating per-concept
        issues plus bundle-wide checks.
    """
    issues: list[ValidationIssue] = []
    seen_headings: dict[str, set[str]] = {}

    for path, error in bundle.errors:
        issues.append(ValidationIssue("error", str(path), f"failed to parse: {error}"))

    for concept in bundle.concepts.values():
        cid = concept.concept_id
        result = validate_concept(concept)
        issues.extend(result.issues)

        headings = seen_headings.setdefault(cid, set())
        for s in concept.sections:
            if s.heading and s.heading in headings:
                issues.append(
                    ValidationIssue("warning", cid, f"section heading repeated: '{s.heading}'")
                )
            headings.add(s.heading)

    if "index" not in bundle.reserved:
        issues.append(
            ValidationIssue("warning", str(bundle.root), "bundle root 'index.md' is missing")
        )

    from intelliqx_okf.bundle import OKFLinkResolver

    resolver = OKFLinkResolver(bundle)
    _edges = resolver.edges()
    if resolver.unresolved_count:
        issues.append(
            ValidationIssue(
                "warning",
                str(bundle.root),
                f"{resolver.unresolved_count} unresolved internal link(s)",
            )
        )

    return ValidationResult(issues=issues)

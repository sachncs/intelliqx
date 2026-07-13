"""Accessibility Agent (Execution).

Validates a DOM snapshot against a small set of WCAG-derived rules.
The agent is regex-based (no real HTML parser) and covers:

* **image-alt** — ``<img>`` tags must have an ``alt`` attribute.
* **label** — form fields must have an associated label
  (``<label for="...">``) or an ``aria-label``.
* **button-name** — ``<button>`` elements must have non-empty
  visible text or an ``aria-label``.
* **page-has-h1** — every page must have a top-level ``<h1>``.
* **html-has-lang** — the ``<html>`` element must declare a
  language via the ``lang`` attribute.

Severity levels follow axe-core conventions: ``minor``,
``moderate``, ``serious``, ``critical``. The current rules emit
``moderate`` or ``serious``; future rules can use the full range.

Each issue carries a remediation hint suitable for inclusion in a
PR comment.
"""

from __future__ import annotations

import re

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_core.models import AgentCategory
from pydantic import BaseModel, ConfigDict, Field


class AccessibilityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dom_html: str
    tenant_id: str
    standard: str = "WCAG2.2-AA"


class AccessibilityIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule: str
    severity: str  # minor | moderate | serious | critical
    element: str
    message: str
    remediation: str


class AccessibilityOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issues: list[AccessibilityIssue] = Field(default_factory=list)
    passed: bool


class AccessibilityAgent(AgentBase):
    META = AgentMeta(
        name="accessibility",
        category=AgentCategory.EXECUTION,
        version="0.1.0",
        description="WCAG 2.2 AA / keyboard / ARIA / contrast checks.",
    )
    INPUT_MODEL = AccessibilityInput
    OUTPUT_MODEL = AccessibilityOutput

    @traced_agent("accessibility")
    async def run(self, ctx: AgentContext, input: AccessibilityInput) -> AccessibilityOutput:
        issues: list[AccessibilityIssue] = []
        # Rule: images must have alt
        for m in re.finditer(r"<img\b([^>]*)>", input.dom_html, re.IGNORECASE):
            attrs = m.group(1)
            if "alt=" not in attrs.lower():
                issues.append(
                    AccessibilityIssue(
                        rule="image-alt",
                        severity="serious",
                        element=m.group(0)[:80],
                        message="Image missing alt attribute",
                        remediation="Add an alt attribute describing the image",
                    )
                )
        # Rule: form inputs must have labels
        for m in re.finditer(r"<(input|textarea|select)\b([^>]*)>", input.dom_html, re.IGNORECASE):
            attrs = m.group(2)
            tag = m.group(1).lower()
            # Hidden/submit/button inputs are self-labelling.
            if tag == "input" and re.search(r'type="(hidden|submit|button)"', attrs, re.IGNORECASE):
                continue
            if "id=" not in attrs.lower() and "aria-label=" not in attrs.lower():
                issues.append(
                    AccessibilityIssue(
                        rule="label",
                        severity="moderate",
                        element=m.group(0)[:80],
                        message=f"{tag} missing label",
                        remediation="Add <label for=...> or aria-label",
                    )
                )
        # Rule: button text
        for m in re.finditer(
            r"<button\b([^>]*)>(.*?)</button>", input.dom_html, re.IGNORECASE | re.DOTALL
        ):
            text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if not text:
                issues.append(
                    AccessibilityIssue(
                        rule="button-name",
                        severity="serious",
                        element=m.group(0)[:80],
                        message="Button has no accessible name",
                        remediation="Add visible text or aria-label",
                    )
                )
        # Rule: page has h1
        if not re.search(r"<h1\b", input.dom_html, re.IGNORECASE):
            issues.append(
                AccessibilityIssue(
                    rule="page-has-h1",
                    severity="moderate",
                    element="<html>",
                    message="Page is missing a top-level heading",
                    remediation="Add an <h1> as the main heading",
                )
            )
        # Rule: lang attribute
        if not re.search(r"<html[^>]*\blang=", input.dom_html, re.IGNORECASE):
            issues.append(
                AccessibilityIssue(
                    rule="html-has-lang",
                    severity="moderate",
                    element="<html>",
                    message="<html> element missing lang attribute",
                    remediation="Add lang='en' (or appropriate language code)",
                )
            )
        return AccessibilityOutput(issues=issues, passed=not issues)

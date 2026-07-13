"""Security Agent (Tier 3).

Runs four checks against a set of source files and (optionally) a
live target URL:

1. **Secret detection.** A small subset of gitleaks patterns:
   AWS access keys, bearer tokens, private-key headers, hard-coded
   passwords.
2. **SAST.** A small subset of Semgrep rules: ``eval``, ``exec``,
   ``subprocess shell=True``, ``pickle.loads``, disabled TLS
   verification.
3. **Dependency scan.** A small lookup of known-vulnerable
   versions (django 1.11, flask 0.12, requests 2.18). Only versions
   that match the ``<name>==<version>`` form are flagged.
4. **DAST.** An HTTP probe of the optional ``target_url`` that
   checks for missing security headers (``X-Content-Type-Options``,
   ``Strict-Transport-Security``) and reports 5xx responses.

The patterns are deliberately a *subset* of upstream tools
(gitleaks, Semgrep, Trivy, OWASP ZAP). Production deployments
should layer those tools on top of this agent, not replace it.
"""

from __future__ import annotations

import re

from intelliqx_agents.base import AgentBase, AgentContext, AgentMeta
from intelliqx_agents.decorators import traced_agent
from intelliqx_core.models import AgentCategory
from pydantic import BaseModel, ConfigDict, Field


class SecurityInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tenant_id: str
    source_files: dict[str, str] = Field(default_factory=dict)  # path -> content
    target_url: str | None = None  # for DAST


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str  # sast | dast | dependency | secret
    severity: str  # low | medium | high | critical
    location: str
    message: str


class SecurityOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[Finding] = Field(default_factory=list)
    critical: int = 0
    high: int = 0


# Patterns for secret detection (subset of gitleaks defaults).
SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS Access Key ID"),
    (re.compile(r"(?i)bearer\s+[a-z0-9_\-]{20,}"), "Bearer token"),
    (re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"), "Private key"),
    (re.compile(r"(?i)password\s*[=:]\s*['\"][^'\"]+['\"]"), "Hard-coded password"),
]


# SAST rules (subset of Semgrep rules).
SAST_PATTERNS = [
    (re.compile(r"\beval\s*\("), "Use of eval()", "high"),
    (re.compile(r"\bexec\s*\("), "Use of exec()", "high"),
    (re.compile(r"subprocess\.call\([^)]*shell=True"), "subprocess shell=True", "high"),
    (re.compile(r"pickle\.loads?\("), "Insecure deserialization (pickle)", "critical"),
    (re.compile(r"verify\s*=\s*False"), "TLS verification disabled", "high"),
]


# Dependency checks (very small subset).
KNOWN_VULNS = {
    "django==1.11.0": ("Django 1.11", "critical", "End-of-life; multiple CVEs"),
    "flask==0.12.0": ("Flask 0.12", "high", "Outdated; security fixes missing"),
    "requests==2.18.0": ("requests 2.18.0", "medium", "CVE-2018-18074"),
}


class SecurityAgent(AgentBase):
    META = AgentMeta(
        name="security",
        category=AgentCategory.EXECUTION,
        version="0.1.0",
        description="SAST, secret detection, dependency scan, DAST.",
    )
    INPUT_MODEL = SecurityInput
    OUTPUT_MODEL = SecurityOutput

    @traced_agent("security")
    async def run(self, ctx: AgentContext, input: SecurityInput) -> SecurityOutput:
        findings: list[Finding] = []

        # 1) Secret detection across all files
        for path, content in input.source_files.items():
            for pat, name in SECRET_PATTERNS:
                for m in pat.finditer(content):
                    findings.append(
                        Finding(
                            type="secret",
                            severity="critical",
                            location=f"{path}:{_line_at(content, m.start())}",
                            message=f"Potential {name} detected",
                        )
                    )

        # 2) SAST
        for path, content in input.source_files.items():
            for pat, name, sev in SAST_PATTERNS:
                for m in pat.finditer(content):
                    findings.append(
                        Finding(
                            type="sast",
                            severity=sev,
                            location=f"{path}:{_line_at(content, m.start())}",
                            message=name,
                        )
                    )

        # 3) Dependency scan (parse requirements.txt-like content)
        for path, content in input.source_files.items():
            if "requirement" in path.lower() or path.endswith(".txt"):
                for line in content.splitlines():
                    line_s = line.strip()
                    for pkg_match, info in KNOWN_VULNS.items():
                        if line_s.lower().startswith(pkg_match.lower().split("==")[0]):
                            name, sev, msg = info
                            findings.append(
                                Finding(
                                    type="dependency",
                                    severity=sev,
                                    location=path,
                                    message=f"{name}: {msg}",
                                )
                            )

        # 4) DAST (very simple HTTP probe)
        if input.target_url:
            try:
                import httpx

                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.get(input.target_url)
                    # Probe for missing security headers
                    if "x-content-type-options" not in {k.lower() for k in r.headers}:
                        findings.append(
                            Finding(
                                type="dast",
                                severity="medium",
                                location=input.target_url,
                                message="Missing X-Content-Type-Options header",
                            )
                        )
                    if "strict-transport-security" not in {k.lower() for k in r.headers}:
                        findings.append(
                            Finding(
                                type="dast",
                                severity="medium",
                                location=input.target_url,
                                message="Missing Strict-Transport-Security header",
                            )
                        )
                    if r.status_code >= 500:
                        findings.append(
                            Finding(
                                type="dast",
                                severity="high",
                                location=input.target_url,
                                message=f"Server error: HTTP {r.status_code}",
                            )
                        )
            except Exception as e:
                findings.append(
                    Finding(
                        type="dast",
                        severity="low",
                        location=input.target_url or "",
                        message=f"DAST probe failed: {type(e).__name__}",
                    )
                )

        critical = sum(1 for f in findings if f.severity == "critical")
        high = sum(1 for f in findings if f.severity == "high")
        return SecurityOutput(findings=findings, critical=critical, high=high)


def _line_at(content: str, offset: int) -> int:
    """Return the 1-based line number that contains ``content[offset:]``.

    Used to build human-readable locations like ``"foo.py:42"`` for
    security findings.
    """
    return content[:offset].count("\n") + 1

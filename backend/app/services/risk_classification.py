"""Risk classification and ordering of assessment gaps (HU-17).

HU-17: as a security officer at the assessed organization, I want to see the gaps
ordered by criticality, so that I know where to start when I cannot tackle them all.

The rules follow Aligo's classification guide (handover 06_classification):

- Priority (Critical, High, Medium, Low) is a property of the control and its risk
  exposure. It does not depend on the control status or on the remediation effort.
- Each gap carries one or more named risks. The severity (Extreme, High, Medium, Low)
  belongs to the risk and is fixed: the rule only selects which risks apply.

The classification is a deterministic rule, not a model call. Its decision trace uses
prompt_id "rule:risk-classification" (docs/design/trace-schema.md), so every priority
and risk can be traced back to this rule and its version.

The per-control priorities and risk selections are provisional until Aligo or the
Product Owner confirms them. A test checks that every control in the knowledge-base
scope has a rule, so a new control cannot be left unclassified by mistake.
"""

from dataclasses import dataclass
from uuid import UUID

from app.schemas.decision_trace import DecisionTrace, TraceSource

RULE_ID = "rule:risk-classification"
RULE_VERSION = "0.1"
RULES_PROVISIONAL = True

# Aligo's value sets, most important first.
PRIORITY_ORDER = ("Critical", "High", "Medium", "Low")
SEVERITY_ORDER = ("Extreme", "High", "Medium", "Low")

# Control statuses that make a control a gap. A not_implemented gap comes before a
# partially_implemented gap when everything else is equal.
GAP_STATUS_ORDER = ("not_implemented", "partially_implemented")

# Risk vocabulary with fixed severities, taken only from Aligo's handover materials:
# - Unauthorized access: classification guide, section 2, and the finding data model
# - System compromise: Risk Remediation Plan (Aligo Demo), Key Risks
# - Privilege escalation: finding data model, example of the risks field
# - Improper assignment of privileged functions: Risk Remediation Plan (Aligo Demo), Key Risks
RISK_SEVERITIES = {
    "Unauthorized access": "Extreme",
    "System compromise": "Extreme",
    "Privilege escalation": "High",
    "Improper assignment of privileged functions": "High",
}

# Named in the classification guide, but no Aligo material gives their severity.
# They are not assigned to any control until Aligo confirms a severity.
RISKS_WITHOUT_SEVERITY = (
    "Unaddressed vulnerabilities",
    "Lack of individual accountability",
    "Lack of third-party controls oversight",
    "Use of product / service",
)


@dataclass(frozen=True)
class ControlRule:
    priority: str
    risks: tuple[str, ...]
    reason: str


# Provisional rules for the controls in the demo knowledge base (demo-0.2).
# Each reason points to the pattern in section 1 of the classification guide.
CONTROL_RULES = {
    "PR.AA-01": ControlRule(
        priority="High",
        risks=("Unauthorized access",),
        reason=(
            "Identity and credential lifecycle, including disabling accounts of people who leave, "
            "is access management (guide, section 1: High)."
        ),
    ),
    "PR.AA-03": ControlRule(
        priority="High",
        risks=("Unauthorized access", "System compromise"),
        reason=(
            "Authentication of administrator accounts governs privileged access "
            "(guide, section 1: High)."
        ),
    ),
    "PR.AA-05": ControlRule(
        priority="High",
        risks=(
            "Unauthorized access",
            "Privilege escalation",
            "Improper assignment of privileged functions",
        ),
        reason=(
            "Least privilege and periodic access review are privileged account restriction and "
            "account audit (guide, section 1: High)."
        ),
    ),
}


@dataclass(frozen=True)
class GapClassification:
    control_code: str
    control_status: str
    priority: str
    risks: tuple[tuple[str, str], ...]  # (risk name, severity), most severe first
    reason: str

    @property
    def worst_severity(self) -> str:
        return self.risks[0][1]


def classify_gap(control_code: str, control_status: str) -> GapClassification | None:
    """Priority and risks of one control result.

    Returns None when the status is not a gap (implemented, not_applicable, not_assessed).
    Raises ValueError for a control without a rule, so a gap is never given an invented priority.
    """
    if control_status not in GAP_STATUS_ORDER:
        return None
    rule = CONTROL_RULES.get(control_code)
    if rule is None:
        raise ValueError(f"No risk classification rule for control {control_code}.")

    risks = sorted(
        ((name, RISK_SEVERITIES[name]) for name in rule.risks),
        key=lambda risk: SEVERITY_ORDER.index(risk[1]),
    )
    return GapClassification(
        control_code=control_code,
        control_status=control_status,
        priority=rule.priority,
        risks=tuple(risks),
        reason=rule.reason,
    )


def order_gaps(gaps: list[GapClassification]) -> list[GapClassification]:
    """Gaps ordered by criticality, where to start first.

    1. Priority: Critical, High, Medium, Low.
    2. Most severe risk: Extreme, High, Medium, Low.
    3. Status: not_implemented before partially_implemented.
    4. Control code, so the order is always the same.
    """
    return sorted(
        gaps,
        key=lambda gap: (
            PRIORITY_ORDER.index(gap.priority),
            SEVERITY_ORDER.index(gap.worst_severity),
            GAP_STATUS_ORDER.index(gap.control_status),
            gap.control_code,
        ),
    )


def classification_output(gap: GapClassification) -> dict:
    """The classification as stored in the trace output and shown in the gap list."""
    return {
        "control_code": gap.control_code,
        "control_status": gap.control_status,
        "priority": gap.priority,
        "risks": [{"name": name, "severity": severity} for name, severity in gap.risks],
        "rules_version": RULE_VERSION,
        "rules_provisional": RULES_PROVISIONAL,
    }


def build_classification_trace(
    organization_id: UUID,
    assessment_id: UUID,
    gap: GapClassification,
    kb_version: str,
    sources: list[TraceSource],
) -> DecisionTrace:
    """The decision trace of one classified gap.

    sources are the sources of the control result's own decision (usually the
    participant's answers), so the classification is linked to what the gap is based on.
    """
    risk_text = ", ".join(f"{name} ({severity})" for name, severity in gap.risks)
    return DecisionTrace(
        organization_id=organization_id,
        assessment_id=assessment_id,
        decision_type="finding_generated",
        control_ids=[gap.control_code],
        sources=sources,
        actor_type="agent",
        prompt_id=RULE_ID,
        prompt_version=RULE_VERSION,
        kb_version=kb_version,
        output=classification_output(gap),
        rationale=f"{gap.control_code} is {gap.priority}: {gap.reason} Risks: {risk_text}.",
    )

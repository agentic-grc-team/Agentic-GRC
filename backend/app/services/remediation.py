"""Remediation recommendations for assessment gaps (HU-18), part 1.

HU-18: recommend remediation with justification, so that the organization knows what to do
about each gap and why.

Each gap classified by HU-17 (`risk_classification.classify_gap`) gets one recommendation,
shaped like a finding in Aligo's finding data model (handover 07_cynomi_data_model):

- `issue` and `requirement` are a matched pair: the consequence of the gap and the target state.
- `task`, `task_description` and ordered `how_to` steps say what to do.
- `dependency` (People, Process, Technology) says what kind of change closes the gap.
- `time_horizon` (Short term, Mid term, Long term) places it on the roadmap, as in Aligo's
  Risk Remediation Plan.
- `evidence_to_close` says what proof will show the gap is closed. It repeats the
  knowledge-base `evidence_examples` of the question mapped to the control (a test checks this).

Priority and risks come unchanged from HU-17. The recommendation never changes them, and the
status, the priority and the remediation are separate scales (docs/design/trace-schema.md).

The recommendation is a deterministic template per control, not a model call: the same gap
always gets the same recommendation, it adds no model latency, and its decision trace uses
prompt_id "rule:remediation". A partially implemented control gets steps that start from what
already exists; a control that is not implemented gets the full steps.

Not included yet: `estimated_effort_hours` and `improvement_score`. Aligo's materials give no
values for these controls, so none are invented. The templates are provisional until Aligo or
the Product Owner confirms them, and every recommendation is preliminary until a consultant
reviews it (HU-19).
"""

from dataclasses import dataclass
from uuid import UUID

from app.schemas.decision_trace import DecisionTrace, TraceSource
from app.services.risk_classification import GapClassification, order_gaps

RULE_ID = "rule:remediation"
RULE_VERSION = "0.1"
RULES_PROVISIONAL = True

# Aligo's value sets.
DEPENDENCIES = ("People", "Process", "Technology")
TIME_HORIZONS = ("Short term", "Mid term", "Long term")

STATUS_LABELS = {
    "not_implemented": "not implemented",
    "partially_implemented": "partially implemented",
}


@dataclass(frozen=True)
class RemediationTemplate:
    question_code: str
    statement: str
    issue: str
    requirement: str
    task: str
    task_description: str
    how_to: tuple[str, ...]
    partial_how_to: tuple[str, ...]
    dependency: str
    time_horizon: str
    basis: str
    evidence_to_close: tuple[str, ...]


# Provisional templates for the controls in the demo knowledge base (demo-0.2).
# question_code is the KB question mapped to the control; the recommendation answers that
# question's intent, because that is what the participant was assessed on.
REMEDIATION_TEMPLATES = {
    "PR.AA-01": RemediationTemplate(
        question_code="IAM-03",
        statement="Identity lifecycle and offboarding",
        issue=(
            "Accounts of people who have left the organization can stay active, so former "
            "employees or anyone who obtains their credentials could still sign in to company "
            "systems."
        ),
        requirement=(
            "Accounts and access of people who leave are disabled in every system within a "
            "defined time, and each removal is recorded."
        ),
        task="Define and enforce an offboarding procedure for accounts and access",
        task_description=(
            "Agree on a maximum time to disable a leaver's accounts, make HR notify IT of every "
            "departure, and disable access in all systems, cloud services included, with a record "
            "of when each account was disabled."
        ),
        how_to=(
            "Agree on the maximum time between an employee's last day and disabling their "
            "accounts (for example, the same working day).",
            "List every system where people have accounts, including cloud services and shared "
            "or service accounts they used.",
            "Make HR notify IT of every departure on or before the last day, through a ticket or "
            "an automated feed.",
            "Disable the leaver's accounts in every listed system and revoke active sessions and "
            "tokens.",
            "Record the leaving date and the date each account was disabled.",
            "Every month, compare the HR leavers list with active accounts and disable any that "
            "were missed.",
        ),
        partial_how_to=(
            "Compare the HR leavers list for the last three months with the accounts that are "
            "still active, and disable any that were missed.",
            "Find the systems or account types the current procedure does not cover, such as "
            "cloud services or shared accounts, and add them to it.",
            "Set or confirm the maximum time to disable a leaver's accounts, and record the "
            "disable date for every leaver.",
            "Every month, compare the HR leavers list with active accounts.",
        ),
        dependency="Process",
        time_horizon="Short term",
        basis=(
            "Disabling leavers' accounts closes the most direct path to unauthorized access, and "
            "it needs a procedure and coordination with HR rather than new tools."
        ),
        evidence_to_close=(
            "Offboarding procedure",
            "List of disabled accounts with each employee's leaving date",
        ),
    ),
    "PR.AA-03": RemediationTemplate(
        question_code="IAM-01",
        statement="Authentication of privileged accounts",
        issue=(
            "Administrator accounts that sign in with a password alone can be taken over with a "
            "single stolen or guessed password, which gives an attacker control over critical "
            "settings and data."
        ),
        requirement=(
            "Every account with administrator privileges, cloud services included, must use a "
            "second authentication factor, and this is enforced by policy, not left to each user."
        ),
        task="Enforce multi-factor authentication for all administrator accounts",
        task_description=(
            "Identify every privileged account and enforce a second factor for all of them "
            "through a central policy, such as a conditional access policy scoped to "
            "administrator roles, with a short, documented list of exceptions."
        ),
        how_to=(
            "List every account with administrator privileges in each system, including cloud "
            "services such as Microsoft 365 and emergency (break-glass) accounts.",
            "Choose the second factor (authenticator app or hardware key) and register it for "
            "each administrator.",
            "Enforce it centrally, for example with a conditional access policy that requires "
            "MFA for all administrator roles.",
            "Keep exceptions to a documented minimum, such as one monitored break-glass account "
            "with a long, securely stored password.",
            "Check the authentication methods report and confirm that every administrator is "
            "registered and covered by the policy.",
        ),
        partial_how_to=(
            "Compare the list of administrator accounts with the accounts covered by the MFA "
            "policy, cloud services included.",
            "Register a second factor for the administrators who do not have one.",
            "Extend the enforcing policy to every administrator role, so MFA does not depend on "
            "each user's own setting.",
            "Document the remaining exceptions and check coverage again in the authentication "
            "methods report.",
        ),
        dependency="Technology",
        time_horizon="Short term",
        basis=(
            "A second factor on privileged accounts blocks most account takeovers, and it can be "
            "enforced with settings the organization usually already has."
        ),
        evidence_to_close=(
            "Conditional access policy requiring MFA for administrative roles (Entra ID)",
            "Authentication methods registration report for administrators",
        ),
    ),
    "PR.AA-05": RemediationTemplate(
        question_code="IAM-02",
        statement="Least privilege and periodic access review",
        issue=(
            "Without a regular access review, people keep permissions they no longer need, which "
            "widens the damage a compromised or misused account can do and allows privilege "
            "escalation."
        ),
        requirement=(
            "Access to important systems is reviewed on a defined schedule by a named owner, and "
            "permissions that are no longer needed are removed and recorded."
        ),
        task="Establish a periodic access review with named owners",
        task_description=(
            "Decide which systems are reviewed, how often and by whom, run the first review, "
            "remove unneeded permissions, and keep a dated record of each review and its result."
        ),
        how_to=(
            "List the important systems and, for each one, the owner who approves access.",
            "Set the review frequency (for example, quarterly for privileged access and every "
            "six months for other access).",
            "Export the current access of each system and ask its owner to confirm or remove "
            "each permission.",
            "Remove the permissions that are no longer needed and record what was removed.",
            "Keep a dated record of each review with its owner and result, and schedule the next "
            "one.",
        ),
        partial_how_to=(
            "Find the important systems that the current review does not cover and assign each "
            "one an owner.",
            "Set a fixed frequency for every review, if it is not defined yet.",
            "Make sure unneeded permissions found in a review are actually removed, not only "
            "reported.",
            "Keep a dated record of each review with its owner and result.",
        ),
        dependency="Process",
        time_horizon="Mid term",
        basis=(
            "A review cycle needs system owners and a first full review before it runs on its "
            "own, so it takes longer than a configuration change."
        ),
        evidence_to_close=("Record of the last access review with its date and owner",),
    ),
}


@dataclass(frozen=True)
class RemediationRecommendation:
    control_code: str
    control_status: str
    priority: str
    risks: tuple[tuple[str, str], ...]  # from HU-17, most severe first
    question_code: str
    statement: str
    issue: str
    requirement: str
    task: str
    task_description: str
    how_to: tuple[str, ...]
    dependency: str
    time_horizon: str
    evidence_to_close: tuple[str, ...]
    justification: str


def recommend_remediation(gap: GapClassification) -> RemediationRecommendation:
    """The recommendation for one classified gap.

    Raises ValueError for a control without a template, so a gap never gets an invented
    recommendation. The caller shows such a gap without a recommendation.
    """
    template = REMEDIATION_TEMPLATES.get(gap.control_code)
    if template is None:
        raise ValueError(f"No remediation template for control {gap.control_code}.")
    if gap.control_status not in STATUS_LABELS:
        raise ValueError(f"Control status {gap.control_status} is not a gap.")

    partial = gap.control_status == "partially_implemented"
    how_to = template.partial_how_to if partial else template.how_to
    task_description = (
        "Part of this is already in place. " + template.task_description
        if partial
        else template.task_description
    )
    justification = (
        f"{gap.control_code} was assessed as {STATUS_LABELS[gap.control_status]} "
        f"(question {template.question_code}). {template.issue} "
        f"Recommended: {template.task}. {template.basis} "
        f"Priority {gap.priority}: {gap.reason}"
    )
    return RemediationRecommendation(
        control_code=gap.control_code,
        control_status=gap.control_status,
        priority=gap.priority,
        risks=gap.risks,
        question_code=template.question_code,
        statement=template.statement,
        issue=template.issue,
        requirement=template.requirement,
        task=template.task,
        task_description=task_description,
        how_to=how_to,
        dependency=template.dependency,
        time_horizon=template.time_horizon,
        evidence_to_close=template.evidence_to_close,
        justification=justification,
    )


def recommend_for_gaps(gaps: list[GapClassification]) -> list[RemediationRecommendation]:
    """Recommendations in the HU-17 order of the gaps (most critical first)."""
    return [recommend_remediation(gap) for gap in order_gaps(gaps)]


def group_by_time_horizon(
    recommendations: list[RemediationRecommendation],
) -> dict[str, list[RemediationRecommendation]]:
    """Short, mid and long term buckets, keeping the given order inside each bucket."""
    groups: dict[str, list[RemediationRecommendation]] = {horizon: [] for horizon in TIME_HORIZONS}
    for recommendation in recommendations:
        groups[recommendation.time_horizon].append(recommendation)
    return groups


def remediation_output(recommendation: RemediationRecommendation) -> dict:
    """The recommendation as stored in the trace output and shown in the remediation plan."""
    return {
        "kind": "remediation",
        "control_code": recommendation.control_code,
        "control_status": recommendation.control_status,
        "priority": recommendation.priority,
        "risks": [
            {"name": name, "severity": severity} for name, severity in recommendation.risks
        ],
        "statement": recommendation.statement,
        "issue": recommendation.issue,
        "requirement": recommendation.requirement,
        "task": recommendation.task,
        "task_description": recommendation.task_description,
        "how_to": list(recommendation.how_to),
        "dependency": recommendation.dependency,
        "time_horizon": recommendation.time_horizon,
        "evidence_to_close": list(recommendation.evidence_to_close),
        "is_preliminary": True,
        "rules_version": RULE_VERSION,
        "rules_provisional": RULES_PROVISIONAL,
    }


def build_remediation_trace(
    organization_id: UUID,
    assessment_id: UUID,
    recommendation: RemediationRecommendation,
    kb_version: str,
    sources: list[TraceSource],
) -> DecisionTrace:
    """The decision trace of one recommendation.

    sources are the sources of the control result's own decision (usually the participant's
    answers), so the recommendation is linked to what the gap is based on. While the templates
    are provisional, every recommendation requires human review.
    """
    return DecisionTrace(
        organization_id=organization_id,
        assessment_id=assessment_id,
        decision_type="finding_generated",
        control_ids=[recommendation.control_code],
        sources=sources,
        actor_type="agent",
        prompt_id=RULE_ID,
        prompt_version=RULE_VERSION,
        kb_version=kb_version,
        output=remediation_output(recommendation),
        rationale=recommendation.justification,
        requires_human_review=RULES_PROVISIONAL,
    )

"""Acceptance tests for HU-17 — See the gaps ordered by criticality.

User story: As a security officer at the assessed organization, I want to see the gaps ordered by
criticality, so that I know where to start when I cannot tackle them all.

Each test is one acceptance criterion of HU-17, written as Given / When / Then. They run through the
HTTP API against PostgreSQL. The assessment is always created through the API. AC 3 follows the whole
flow (interview answer, agent draft, consultant review); the other criteria give the controls their
final results directly, as a consultant version would. Only the Supabase login is replaced by a fixed
user and the language model by a deterministic fake. Results are recorded in
docs/testing/acceptance-tests.md.
"""

import uuid
from types import SimpleNamespace

from app.db.models import AssessmentControl
from app.services.risk_classification import CONTROL_RULES, ControlRule
from tests.acceptance.test_hu25_inspect_reasoning_trace import (
    agent_draft,
    api,
    db,
    member,
)  # noqa: F401
from tests.test_assessments_db import make_organization
from tests.test_expert_review_db import make_result


def gaps_url(organization_id, assessment_id):
    return f"/api/v1/organizations/{organization_id}/assessments/{assessment_id}/gaps"


def assessment_with_results(db, api, statuses):
    """An assessment created through the API whose controls get final consultant results.

    statuses maps a control code to its final status; controls not listed keep no result.
    """
    organization = make_organization(db)
    consultant = member(db, organization, "consultant")
    representative = member(db, organization, "representative")

    api.login(consultant)
    created = api.post(
        f"/api/v1/organizations/{organization.id}/assessments",
        json={"title": "Q4 identity review"},
    )
    assert created.status_code == 201, created.text
    assessment_id = uuid.UUID(created.json()["id"])

    controls = {
        control.control_code: control
        for control in db.query(AssessmentControl).filter(
            AssessmentControl.assessment_id == assessment_id
        )
    }
    for code, status in statuses.items():
        extra = {}
        if status == "not_assessed":
            extra["not_assessed_reason"] = "Nobody could answer."
        if status == "not_applicable":
            extra["justification"] = "Out of scope."
        make_result(
            db,
            organization,
            controls[code],
            author_actor="aligo_consultant",
            author_user_id=consultant.id,
            control_status=status,
            explanation=f"Consultant set {status}.",
            **extra,
        )

    return SimpleNamespace(
        organization=organization,
        consultant=consultant,
        representative=representative,
        assessment_id=assessment_id,
        url=gaps_url(organization.id, assessment_id),
    )


def gap_codes(response):
    return [gap["control_code"] for gap in response.json()["gaps"]]


def test_hu17_ac1_only_partially_or_not_implemented_controls_are_gaps(db, api):
    """AC 1
    Given an assessment with control results,
    when the security officer views the gaps,
    then only controls whose result is partially implemented or not implemented are listed as gaps,
    and implemented, not applicable and not assessed controls are not.
    """
    setup = assessment_with_results(
        db,
        api,
        {
            "PR.AA-01": "implemented",
            "PR.AA-03": "not_assessed",
            "PR.AA-05": "partially_implemented",
        },
    )

    api.login(setup.representative)
    response = api.get(setup.url)

    assert response.status_code == 200, response.text
    assert gap_codes(response) == ["PR.AA-05"]

    # Not applicable is not a gap either.
    other = assessment_with_results(
        db, api, {"PR.AA-01": "not_applicable", "PR.AA-03": "not_implemented"}
    )
    api.login(other.representative)
    assert gap_codes(api.get(other.url)) == ["PR.AA-03"]


def test_hu17_ac2_gaps_are_ordered_by_criticality_the_same_way_every_time(
    db, api, monkeypatch
):
    """AC 2
    Given several gaps,
    when the security officer views them,
    then they are ordered by priority (Critical first), then by their most severe risk (Extreme first),
    then not implemented before partially implemented, then by control code,
    and the order is the same every time.
    """
    setup = assessment_with_results(
        db,
        api,
        {
            "PR.AA-05": "partially_implemented",
            "PR.AA-03": "not_implemented",
            "PR.AA-01": "partially_implemented",
        },
    )
    api.login(setup.representative)

    # With the current rules all three are High with an Extreme risk: not implemented first, then by code.
    first = api.get(setup.url)
    assert gap_codes(first) == ["PR.AA-03", "PR.AA-01", "PR.AA-05"]
    assert gap_codes(api.get(setup.url)) == gap_codes(first)

    # A higher priority comes before everything else.
    monkeypatch.setitem(
        CONTROL_RULES,
        "PR.AA-05",
        ControlRule(
            priority="Critical", risks=("Privilege escalation",), reason="Test rule."
        ),
    )
    assert gap_codes(api.get(setup.url)) == ["PR.AA-05", "PR.AA-03", "PR.AA-01"]

    # Equal priority: the gap whose worst risk is Extreme comes before the one whose worst risk is High.
    monkeypatch.setitem(
        CONTROL_RULES,
        "PR.AA-05",
        ControlRule(
            priority="High", risks=("Privilege escalation",), reason="Test rule."
        ),
    )
    assert gap_codes(api.get(setup.url)) == ["PR.AA-03", "PR.AA-01", "PR.AA-05"]


def test_hu17_ac3_each_gap_shows_its_classification_and_what_it_is_based_on(db, api):
    """AC 3
    Given a gap,
    when the security officer views it,
    then it shows its priority, its risks with their severity and the reason for the priority,
    it is marked as provisional while the rules are provisional,
    and it identifies the control result it is based on.
    """
    draft = agent_draft(db, api)
    # Before the consultant has reviewed the agent's draft, it is not a gap yet.
    url = gaps_url(draft.organization.id, draft.assessment["id"])
    api.login(draft.representative)
    before = api.get(url).json()
    assert before["gaps"] == []
    assert before["pending_controls"] >= 1

    api.login(draft.consultant)
    accepted = api.post(
        f"/api/v1/expert-reviews/{draft.item['result_id']}/decision",
        json={"outcome": "accepted", "comment": "Confirmed in the interview."},
    )
    assert accepted.status_code == 200, accepted.text

    api.login(draft.representative)
    response = api.get(url)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rules_id"] == "rule:risk-classification"
    assert body["rules_provisional"] is True
    (gap,) = body["gaps"]
    code = draft.item["control_code"]
    rule = CONTROL_RULES[code]
    assert gap["control_code"] == code
    assert gap["control_status"] == "not_implemented"
    assert gap["classified"] is True
    assert gap["priority"] == rule.priority
    assert {risk["name"] for risk in gap["risks"]} == set(rule.risks)
    severities = [risk["severity"] for risk in gap["risks"]]
    order = ["Extreme", "High", "Medium", "Low"]
    assert severities == sorted(severities, key=order.index)
    assert gap["reason"] == rule.reason
    # The gap names the result it rests on: the agent's version 1, accepted by the consultant.
    assert gap["result_version"] == 1
    assert gap["basis"] == "accepted_agent_result"


def test_hu17_ac4_a_control_without_a_rule_is_shown_as_not_classified(
    db, api, monkeypatch
):
    """AC 4
    Given a gap whose control has no classification rule,
    when the gaps are listed,
    then that gap is shown as not classified, without an invented priority,
    and the other gaps are still listed in order.
    """
    monkeypatch.delitem(CONTROL_RULES, "PR.AA-01")
    setup = assessment_with_results(
        db,
        api,
        {
            "PR.AA-01": "not_implemented",
            "PR.AA-03": "partially_implemented",
            "PR.AA-05": "not_implemented",
        },
    )

    api.login(setup.representative)
    response = api.get(setup.url)

    assert response.status_code == 200, response.text
    assert gap_codes(response) == ["PR.AA-05", "PR.AA-03", "PR.AA-01"]
    unclassified = response.json()["gaps"][-1]
    assert unclassified["classified"] is False
    assert unclassified["priority"] is None
    assert unclassified["risks"] == []
    assert unclassified["reason"] is None


def test_hu17_ac5_users_without_access_get_no_gap_data(db, api):
    """AC 5
    Given a user without access to the organization or assessment,
    when they request the gaps,
    then access is denied and no gap data is disclosed.
    """
    setup = assessment_with_results(db, api, {"PR.AA-03": "not_implemented"})
    outsider_org = make_organization(db)
    outsider = member(db, outsider_org, "consultant")
    suspended = member(db, setup.organization, "consultant", status="suspended")

    for user in (outsider, suspended):
        api.login(user)
        response = api.get(setup.url)
        assert response.status_code == 404, response.text
        assert response.json() == {"detail": "Assessment not found."}

    # Asking through the outsider's own organization with this assessment's id finds nothing either.
    api.login(outsider)
    crossed = api.get(gaps_url(outsider_org.id, setup.assessment_id))
    assert crossed.status_code == 404
    assert "PR.AA-03" not in crossed.text

"""Acceptance tests for HU-18 — Recommend remediation with justification.

User story: As a security officer at the assessed organization, I want a remediation recommendation
for each gap, with the reason behind it, so that I know what to do about the gap and why.

Each test is one acceptance criterion of HU-18, written as Given / When / Then. They run through the
HTTP API against PostgreSQL, on the same gap list as HU-17 (GET .../gaps). The assessment is always
created through the API. AC 2 follows the whole flow (interview answer, agent draft, consultant
review); the other criteria give the controls their final results directly, as a consultant version
would. Only the Supabase login is replaced by a fixed user and the language model by a deterministic
fake. Results are recorded in docs/testing/acceptance-tests.md.
"""

from app.services.remediation import REMEDIATION_TEMPLATES
from app.services.risk_classification import CONTROL_RULES
from tests.acceptance.test_hu17_gaps_ordered_by_criticality import (
    assessment_with_results,
    gap_codes,
    gaps_url,
)
from tests.acceptance.test_hu25_inspect_reasoning_trace import (
    agent_draft,
    api,
    db,
    member,
)  # noqa: F401
from tests.test_assessments_db import make_organization


def gaps_by_code(response):
    return {gap["control_code"]: gap for gap in response.json()["gaps"]}


def test_hu18_ac1_each_gap_gets_a_task_with_steps_kind_of_change_horizon_and_closing_evidence(db, api):
    """AC 1
    Given a classified gap,
    when the security officer views the gaps,
    then the gap shows a recommended task with ordered steps, the kind of change it needs
    (People, Process or Technology), when to do it (Short, Mid or Long term)
    and the evidence that will show the gap is closed.
    """
    setup = assessment_with_results(
        db, api, {"PR.AA-01": "not_implemented", "PR.AA-03": "not_implemented", "PR.AA-05": "not_implemented"}
    )

    api.login(setup.representative)
    response = api.get(setup.url)

    assert response.status_code == 200, response.text
    for code, gap in gaps_by_code(response).items():
        template = REMEDIATION_TEMPLATES[code]
        recommendation = gap["remediation"]
        assert recommendation["task"] == template.task, code
        assert recommendation["how_to"] == list(template.how_to), code
        assert len(recommendation["how_to"]) >= 3, code
        assert recommendation["dependency"] in ("People", "Process", "Technology"), code
        assert recommendation["time_horizon"] in ("Short term", "Mid term", "Long term"), code
        assert recommendation["evidence_to_close"] == list(template.evidence_to_close), code
    by_code = gaps_by_code(response)
    assert by_code["PR.AA-03"]["remediation"]["dependency"] == "Technology"
    assert by_code["PR.AA-05"]["remediation"]["time_horizon"] == "Mid term"


def test_hu18_ac2_the_recommendation_explains_why(db, api):
    """AC 2
    Given a gap that a consultant has confirmed,
    when the security officer views its recommendation,
    then it states the consequence of the gap and the target state,
    and a justification that cites the assessed status, the question it is based on and the reason
    for the priority.
    """
    draft = agent_draft(db, api)
    url = gaps_url(draft.organization.id, draft.assessment["id"])
    api.login(draft.consultant)
    accepted = api.post(
        f"/api/v1/expert-reviews/{draft.item['result_id']}/decision",
        json={"outcome": "accepted", "comment": "Confirmed in the interview."},
    )
    assert accepted.status_code == 200, accepted.text

    api.login(draft.representative)
    response = api.get(url)

    assert response.status_code == 200, response.text
    (gap,) = response.json()["gaps"]
    code = draft.item["control_code"]
    template = REMEDIATION_TEMPLATES[code]
    recommendation = gap["remediation"]
    assert recommendation["issue"] == template.issue
    assert recommendation["requirement"] == template.requirement
    justification = recommendation["justification"]
    assert justification.startswith(f"{code} was assessed as not implemented (question {template.question_code}).")
    assert f"Recommended: {template.task}." in justification
    assert f"Priority {gap['priority']}: {CONTROL_RULES[code].reason}" in justification


def test_hu18_ac3_a_partially_implemented_control_starts_from_what_is_in_place(db, api):
    """AC 3
    Given one control that is partially implemented and one that is not implemented,
    when the security officer views their recommendations,
    then the partially implemented control gets steps that start from what is already in place,
    and the control that is not implemented gets the full steps.
    """
    setup = assessment_with_results(
        db, api, {"PR.AA-03": "partially_implemented", "PR.AA-05": "not_implemented"}
    )

    api.login(setup.representative)
    by_code = gaps_by_code(api.get(setup.url))

    partial = by_code["PR.AA-03"]["remediation"]
    full = by_code["PR.AA-05"]["remediation"]
    assert partial["how_to"] == list(REMEDIATION_TEMPLATES["PR.AA-03"].partial_how_to)
    assert partial["task_description"].startswith("Part of this is already in place.")
    assert full["how_to"] == list(REMEDIATION_TEMPLATES["PR.AA-05"].how_to)
    assert not full["task_description"].startswith("Part of this is already in place.")


def test_hu18_ac4_a_gap_without_a_template_gets_no_invented_recommendation(db, api, monkeypatch):
    """AC 4
    Given a gap whose control has no remediation template,
    when the gaps are listed,
    then that gap is shown without a recommendation, rather than an invented one,
    and the other gaps keep their recommendations and their order.
    """
    monkeypatch.delitem(REMEDIATION_TEMPLATES, "PR.AA-01")
    setup = assessment_with_results(
        db,
        api,
        {"PR.AA-01": "not_implemented", "PR.AA-03": "partially_implemented", "PR.AA-05": "not_implemented"},
    )

    api.login(setup.representative)
    response = api.get(setup.url)

    assert response.status_code == 200, response.text
    assert gap_codes(response) == ["PR.AA-01", "PR.AA-05", "PR.AA-03"]
    by_code = gaps_by_code(response)
    assert by_code["PR.AA-01"]["classified"] is True
    assert by_code["PR.AA-01"]["remediation"] is None
    assert by_code["PR.AA-03"]["remediation"] is not None
    assert by_code["PR.AA-05"]["remediation"] is not None


def test_hu18_ac5_recommendations_are_provisional_and_change_nothing_else(db, api):
    """AC 5
    Given the gaps with their recommendations,
    when they are listed,
    then the recommendations are marked as provisional while the templates are provisional,
    and the status, priority, risks and order of the gaps are the same as without them (HU-17).
    """
    setup = assessment_with_results(
        db, api, {"PR.AA-03": "not_implemented", "PR.AA-05": "partially_implemented"}
    )

    api.login(setup.representative)
    body = api.get(setup.url).json()

    assert body["remediation_rules_id"] == "rule:remediation"
    assert body["remediation_rules_provisional"] is True
    assert [gap["control_code"] for gap in body["gaps"]] == ["PR.AA-03", "PR.AA-05"]
    for gap in body["gaps"]:
        rule = CONTROL_RULES[gap["control_code"]]
        assert gap["priority"] == rule.priority
        assert {risk["name"] for risk in gap["risks"]} == set(rule.risks)
    assert body["gaps"][0]["control_status"] == "not_implemented"
    assert body["gaps"][1]["control_status"] == "partially_implemented"


def test_hu18_ac6_users_without_access_get_no_recommendations(db, api):
    """AC 6
    Given a user without access to the organization or assessment,
    when they request the gaps,
    then access is denied and no recommendation is disclosed.
    """
    setup = assessment_with_results(db, api, {"PR.AA-03": "not_implemented"})
    outsider = member(db, make_organization(db), "consultant")
    suspended = member(db, setup.organization, "consultant", status="suspended")

    for user in (outsider, suspended):
        api.login(user)
        response = api.get(setup.url)
        assert response.status_code == 404, response.text
        assert REMEDIATION_TEMPLATES["PR.AA-03"].task not in response.text

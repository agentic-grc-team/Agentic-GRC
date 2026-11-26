"""Passage matches of an assessment through the API (HU-12), against PostgreSQL."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.db.models import OrganizationMembership
from app.db.session import get_engine
from app.main import app
from app.security.auth import get_current_user
from app.services.evidence_links import link_evidence_to_control
from app.services.passage_matching import MATCHER_VERSION
from tests.test_assessments_db import make_assessment, make_control, make_organization, make_user
from tests.test_evidence_db import store

MFA_POLICY = (
    "Cover page of the policy.\f1. Access Control Policy\nSection on privileged accounts.\n\n"
    "All administrator accounts must use multi-factor authentication with an authenticator app."
)
ACCESS_REVIEW = "Revisión de accesos: el responsable del sistema revisa los permisos cada trimestre."
UNRELATED = "The cafeteria opens at eight."


@pytest.fixture
def db():
    """A session inside a transaction that is rolled back after each test, so nothing is left behind."""
    try:
        engine = get_engine()
        connection = engine.connect()
    except (OSError, SQLAlchemyError, RuntimeError):
        pytest.skip("PostgreSQL is unavailable for integration tests.")
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def member(db, organization, role="consultant", status="active"):
    user = make_user(db)
    db.add(OrganizationMembership(organization_id=organization.id, user_id=user.id, role=role, status=status))
    db.commit()
    return user


def text_file(db, organization, text, **changes):
    content = text.encode()
    return store(db, organization, content=content, original_filename=changes.pop("name", "policy.txt"), **changes)


@pytest.fixture
def setup(db):
    organization = make_organization(db)
    assessment = make_assessment(db, organization)
    mfa = make_control(db, organization, assessment, control_code="PR.AA-03")
    review = make_control(db, organization, assessment, control_code="PR.AA-05", control_title="Access is reviewed")
    make_control(
        db, organization, assessment,
        control_code="PR.AA-01", control_title="Out of scope here",
        in_scope=False, scope_rationale="Not assessed in this test.",
    )
    mfa_file = text_file(db, organization, MFA_POLICY, name="mfa-policy.pdf", assessment_id=assessment.id)
    review_file = text_file(db, organization, ACCESS_REVIEW, name="revision.docx")  # no assessment: shared
    text_file(db, organization, UNRELATED, name="cafeteria.txt", assessment_id=assessment.id)

    other_assessment = make_assessment(db, organization)
    text_file(db, organization, MFA_POLICY, name="other-assessment.pdf", assessment_id=other_assessment.id)
    other_organization = make_organization(db)
    text_file(db, other_organization, MFA_POLICY, name="foreign.pdf")

    return SimpleNamespace(
        organization=organization, assessment=assessment, mfa=mfa, review=review,
        mfa_file=mfa_file, review_file=review_file, other_organization=other_organization,
        consultant=member(db, organization),
    )


@pytest.fixture
def api(db):
    saved = dict(app.dependency_overrides)
    app.dependency_overrides[get_db_session] = lambda: db
    client = TestClient(app)

    def as_user(user):
        app.dependency_overrides[get_current_user] = lambda: user
        return client

    try:
        yield as_user
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)


def url(setup, query=""):
    return (
        f"/api/v1/organizations/{setup.organization.id}/assessments/{setup.assessment.id}/passage-matches{query}"
    )


def test_matches_come_from_this_assessment_and_shared_files_only(api, setup):
    response = api(setup.consultant).get(url(setup))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["matcher_version"] == MATCHER_VERSION
    assert body["files_checked"] == 3  # mfa-policy, revision (shared) and cafeteria
    assert {match["file_name"] for match in body["matches"]} == {"mfa-policy.pdf", "revision.docx"}
    assert {match["control_code"] for match in body["matches"]} == {"PR.AA-03", "PR.AA-05"}


def test_a_match_names_the_file_control_passage_and_terms(api, setup):
    body = api(setup.consultant).get(url(setup)).json()
    [mfa] = [match for match in body["matches"] if match["control_code"] == "PR.AA-03"]

    assert mfa["assessment_control_id"] == str(setup.mfa.id)
    assert mfa["evidence_file_id"] == str(setup.mfa_file.id)
    assert mfa["reference"] == f"document_span:{setup.mfa_file.id}#page=2"
    assert mfa["locator"]["page"] == 2
    assert mfa["locator"]["section"] == "1. Access Control Policy"
    start, end = mfa["locator"]["char_start"], mfa["locator"]["char_end"]
    assert MFA_POLICY[start:end] == (
        "All administrator accounts must use multi-factor authentication with an authenticator app."
    )
    assert mfa["excerpt"] == MFA_POLICY[start:end]
    assert mfa["matched_terms"] == ["multi factor authentication", "administrator", "authenticator"]
    assert mfa["confidence"] == 0.75
    assert mfa["verification"] == "not_verified"
    assert mfa["linked"] is False


def test_a_spanish_document_matches_its_control(api, setup):
    body = api(setup.consultant).get(url(setup)).json()
    [review] = [match for match in body["matches"] if match["control_code"] == "PR.AA-05"]

    assert review["evidence_file_id"] == str(setup.review_file.id)
    assert review["matched_terms"][0] == "revision de accesos"
    assert review["locator"]["page"] is None
    assert review["excerpt"] == ACCESS_REVIEW


def test_a_file_already_linked_to_the_control_is_marked(api, setup, db):
    link_evidence_to_control(db, setup.organization.id, setup.mfa_file.id, setup.mfa.id, None)

    body = api(setup.consultant).get(url(setup)).json()

    linked = {match["control_code"]: match["linked"] for match in body["matches"]}
    assert linked == {"PR.AA-03": True, "PR.AA-05": False}
    # Linking the file does not make the passage verified evidence.
    assert {match["verification"] for match in body["matches"]} == {"not_verified"}


def test_the_list_can_be_limited_to_one_file_and_to_a_minimum_confidence(api, setup):
    client = api(setup.consultant)

    one_file = client.get(url(setup, f"?evidence_file_id={setup.review_file.id}")).json()
    confident = client.get(url(setup, "?min_confidence=0.7")).json()

    assert one_file["files_checked"] == 1
    assert {match["control_code"] for match in one_file["matches"]} == {"PR.AA-05"}
    assert confident["min_confidence"] == 0.7
    assert {match["control_code"] for match in confident["matches"]} == {"PR.AA-03"}


def test_an_in_scope_control_without_terms_is_reported(api, setup, db):
    make_control(db, setup.organization, setup.assessment, control_code="DE.CM-01", control_title="Networks are monitored")

    body = api(setup.consultant).get(url(setup)).json()

    assert body["controls_without_terms"] == ["DE.CM-01"]


def test_a_representative_of_the_organization_can_read_the_matches(api, setup, db):
    representative = member(db, setup.organization, role="representative")

    assert api(representative).get(url(setup)).status_code == 200


def test_users_without_an_active_membership_get_404(api, setup, db):
    outsider = member(db, setup.other_organization)
    suspended = member(db, setup.organization, status="suspended")

    for user in (outsider, suspended):
        response = api(user).get(url(setup))
        assert response.status_code == 404, response.text
        assert "matches" not in response.json()


def test_an_assessment_of_another_organization_is_not_found(api, setup, db):
    other_assessment = make_assessment(db, setup.other_organization)
    outsider = member(db, setup.other_organization)

    # The outsider asks with their own organization and this organization's assessment, and the other way round.
    crossed = f"/api/v1/organizations/{setup.other_organization.id}/assessments/{setup.assessment.id}/passage-matches"
    assert api(outsider).get(crossed).status_code == 404
    unknown = f"/api/v1/organizations/{setup.organization.id}/assessments/{uuid4()}/passage-matches"
    assert api(setup.consultant).get(unknown).status_code == 404
    other = f"/api/v1/organizations/{setup.organization.id}/assessments/{other_assessment.id}/passage-matches"
    assert api(setup.consultant).get(other).status_code == 404

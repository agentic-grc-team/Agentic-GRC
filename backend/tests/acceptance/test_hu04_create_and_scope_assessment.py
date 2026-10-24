"""Acceptance tests for HU-04 — Create and scope a security assessment (Jira AGRC-80, task AGRC-65).

User story: As an authorized member of an organization, I want to create an assessment and see its
selected NIST CSF 2.0 functions and categories before starting the interview, so that I understand
the assessment scope and can provide information for the controls that apply to my organization.

Each test is one acceptance criterion of HU-04, written as Given / When / Then. They run through
the HTTP API against PostgreSQL; only the Supabase login is replaced by a fixed user.
Results are recorded in docs/testing/acceptance-tests.md.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.db.models import Assessment, AssessmentControl, OrganizationMembership
from app.db.session import get_engine
from app.main import app
from app.security.auth import get_current_user
from tests.test_assessments_db import make_organization, make_user


@pytest.fixture
def db():
    """A session inside a transaction that is rolled back after each test, so nothing is left behind."""
    try:
        engine = get_engine()
        connection = engine.connect()
    except (OSError, SQLAlchemyError, RuntimeError):
        pytest.skip("PostgreSQL is unavailable for acceptance tests.")
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def api(db, monkeypatch):
    """HTTP client on the real app and database. `api.login(user)` sets who is calling."""
    monkeypatch.setitem(app.dependency_overrides, get_db_session, lambda: db)
    client = TestClient(app)

    def login(user):
        signed_in = SimpleNamespace(id=user.id, is_platform_admin=False)
        monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: signed_in)

    client.login = login
    return client


def member(db, organization, role, status="active"):
    user = make_user(db)
    db.add(OrganizationMembership(organization_id=organization.id, user_id=user.id, role=role, status=status))
    db.commit()
    return user


def assessments_url(organization):
    return f"/api/v1/organizations/{organization.id}/assessments"


def assessment_count(db, organization):
    return db.scalar(select(func.count()).select_from(Assessment).where(Assessment.organization_id == organization.id))


def test_hu04_ac1_non_member_is_denied_and_gets_no_assessment_data(db, api):
    """AC 1
    Given a user has no active membership in the selected organization,
    when the user attempts to open or create an assessment for that organization,
    then access is denied and assessment data is not loaded.
    """
    organization = make_organization(db)
    consultant = member(db, organization, "consultant")
    api.login(consultant)
    created = api.post(assessments_url(organization), json={"title": "Q4 identity review"}).json()
    scope_url = f"{assessments_url(organization)}/{created['id']}/scope"

    other_organization = make_organization(db)
    outsider = member(db, other_organization, "consultant")
    suspended = member(db, organization, "consultant", status="suspended")

    for user in (outsider, suspended):
        api.login(user)
        responses = [
            api.get(assessments_url(organization)),
            api.get(f"{assessments_url(organization)}/{created['id']}"),
            api.get(scope_url),
            api.post(assessments_url(organization), json={"title": "Not allowed"}),
        ]
        for response in responses:
            assert response.status_code == 404
            body = response.json()
            assert body == {"detail": "Organization not found."}
            assert created["id"] not in response.text

    assert assessment_count(db, organization) == 1


def test_hu04_ac2_scope_is_shown_before_the_interview_starts(db, api):
    """AC 2
    Given an authorized organization member selects an organization,
    when the member creates an assessment,
    then the selected organization and assessment scope are shown clearly before the interview starts.
    """
    organization = make_organization(db)
    consultant = member(db, organization, "consultant")
    representative = member(db, organization, "representative")

    api.login(consultant)
    response = api.post(assessments_url(organization), json={"title": "Q4 identity review"})
    assert response.status_code == 201
    assessment_id = response.json()["id"]
    assert response.json()["status"] == "in_progress"

    for user in (consultant, representative):
        api.login(user)
        scope = api.get(f"{assessments_url(organization)}/{assessment_id}/scope")

        assert scope.status_code == 200
        body = scope.json()
        assert body["organization_id"] == str(organization.id)
        assert body["organization_name"] == organization.name
        assert body["assessment"]["title"] == "Q4 identity review"
        assert body["control_count"] == 3
        assert body["functions"] == [
            {
                "code": "PR",
                "name": "Protect",
                "categories": [
                    {
                        "code": "PR.AA",
                        "name": "Identity Management, Authentication, and Access Control",
                        "controls": [
                            {
                                "code": "PR.AA-01",
                                "title": "Identities and credentials for authorized users, services, and hardware are managed by the organization",
                            },
                            {"code": "PR.AA-03", "title": "Users, services, and hardware are authenticated"},
                            {
                                "code": "PR.AA-05",
                                "title": "Access permissions, entitlements, and authorizations are defined in a policy, managed, enforced, and reviewed, and incorporate the principles of least privilege and separation of duties",
                            },
                        ],
                    }
                ],
            }
        ]

    # A representative sees the scope but does not create it: creation is limited to administrators and
    # consultants (ASSESSMENT_CREATOR_ROLES). The roles are to be confirmed in AGRC-85.
    api.login(representative)
    assert api.post(assessments_url(organization), json={"title": "Representative"}).status_code == 403
    assert assessment_count(db, organization) == 1


def test_hu04_ac3_summary_shows_only_in_scope_domains_and_controls(db, api):
    """AC 3
    Given an assessment has been created with selected NIST CSF 2.0 functions or categories,
    when the member opens the assessment summary,
    then only the selected in-scope domains and controls are shown.
    """
    organization = make_organization(db)
    consultant = member(db, organization, "consultant")
    api.login(consultant)
    assessment_id = api.post(assessments_url(organization), json={"title": "Scoped review"}).json()["id"]

    # A control outside the scope, in another function, must not appear in the summary.
    db.add(
        AssessmentControl(
            organization_id=organization.id,
            assessment_id=uuid.UUID(assessment_id),
            control_code="DE.CM-01",
            control_title="Networks and network services are monitored to find potentially adverse events",
            in_scope=False,
            scope_rationale="Not covered by the demo knowledge base.",
        )
    )
    db.commit()

    body = api.get(f"{assessments_url(organization)}/{assessment_id}/scope").json()

    assert body["control_count"] == 3
    assert [function["code"] for function in body["functions"]] == ["PR"]
    shown_controls = [
        control["code"]
        for function in body["functions"]
        for category in function["categories"]
        for control in category["controls"]
    ]
    assert shown_controls == ["PR.AA-01", "PR.AA-03", "PR.AA-05"]
    assert "DE.CM-01" not in str(body)


def test_hu04_ac4_date_and_versions_remain_available_on_reopen(db, api):
    """AC 4
    Given an assessment is saved,
    when the member reopens it,
    then its assessment date and framework or knowledge-base version remain available.
    """
    organization = make_organization(db)
    consultant = member(db, organization, "consultant")
    api.login(consultant)
    created = api.post(assessments_url(organization), json={"title": "Q4 identity review"}).json()
    assert created["started_at"] is not None

    # Reopen later, as a different member, through a new client.
    representative = member(db, organization, "representative")
    reopened_client = TestClient(app)
    api.login(representative)
    reopened = reopened_client.get(f"{assessments_url(organization)}/{created['id']}").json()
    scope = reopened_client.get(f"{assessments_url(organization)}/{created['id']}/scope").json()
    listed = reopened_client.get(assessments_url(organization)).json()

    for view in (reopened, scope["assessment"], next(item for item in listed if item["id"] == created["id"])):
        assert view["started_at"] == created["started_at"]
        assert view["framework_code"] == "NIST-CSF"
        assert view["framework_version"] == "2.0"
        assert view["kb_version"] == "demo-0.2"

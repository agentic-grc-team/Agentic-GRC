"""Microsoft 365 configuration snapshots through the API (AGRC-161), against PostgreSQL."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.api.v1.endpoints.tenant_snapshots import get_graph_transport
from app.core.config import Settings, get_settings
from app.db.models import OrganizationMembership, TenantConfigurationSnapshot
from app.db.session import get_engine
from app.main import app
from app.security.auth import get_current_user
from app.services.m365.sample import SAMPLE_TENANT_ID, sample_transport
from tests.test_assessments_db import make_assessment, make_organization, make_user


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


def member(db, organization, role="consultant"):
    user = make_user(db)
    db.add(OrganizationMembership(organization_id=organization.id, user_id=user.id, role=role, status="active"))
    db.commit()
    return user


@pytest.fixture
def setup(db):
    organization = make_organization(db)
    return SimpleNamespace(
        organization=organization,
        assessment=make_assessment(db, organization),
        consultant=member(db, organization),
        representative=member(db, organization, role="representative"),
        outsider=member(db, make_organization(db)),
    )


@pytest.fixture
def api(db):
    saved = dict(app.dependency_overrides)
    state = SimpleNamespace(settings=Settings(_env_file=None, ms365_data_mode="sample"), transport=None)
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_settings] = lambda: state.settings
    app.dependency_overrides[get_graph_transport] = lambda: state.transport
    client = TestClient(app)

    def as_user(user, settings=None, transport=None):
        if settings is not None:
            state.settings = settings
        state.transport = transport
        app.dependency_overrides[get_current_user] = lambda: user
        return client

    try:
        yield as_user
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)


def url(setup, suffix=""):
    return (
        f"/api/v1/organizations/{setup.organization.id}/assessments/{setup.assessment.id}"
        f"/tenant-snapshots{suffix}"
    )


def count_snapshots(db):
    return db.scalar(select(func.count()).select_from(TenantConfigurationSnapshot))


def graph_settings(organization_id):
    return Settings(
        _env_file=None,
        ms365_data_mode="graph",
        ms365_tenant_id="contoso-tenant",
        ms365_client_id="client",
        ms365_client_secret="secret",
        ms365_organization_id=organization_id,
    )


def test_a_consultant_collects_a_dated_snapshot_for_the_assessment(api, setup, db):
    response = api(setup.consultant).post(url(setup))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["organization_id"] == str(setup.organization.id)
    assert body["assessment_id"] == str(setup.assessment.id)
    assert body["collected_by_user_id"] == str(setup.consultant.id)
    assert body["source"] == "sample"
    assert body["tenant_id"] == SAMPLE_TENANT_ID
    assert body["collected_at"]
    assert body["reference"] == f"tenant_configuration:{body['id']}/"
    assert body["sections"]["securityDefaults"] == "collected"
    assert body["data"]["sections"]["securityDefaults"]["data"]["isEnabled"] is False

    stored = db.get(TenantConfigurationSnapshot, body["id"])
    assert stored is not None and stored.organization_id == setup.organization.id


def test_each_collection_adds_a_snapshot(api, setup):
    client = api(setup.consultant)
    first = client.post(url(setup)).json()
    second = client.post(url(setup)).json()

    listed = client.get(url(setup))
    assert listed.status_code == 200
    assert {item["id"] for item in listed.json()} == {first["id"], second["id"]}
    assert "data" not in listed.json()[0]

    detail = client.get(url(setup, f"/{first['id']}"))
    assert detail.status_code == 200
    assert detail.json()["data"]["tenant"]["id"] == SAMPLE_TENANT_ID


def test_a_failed_collection_returns_the_reason_and_stores_nothing(api, setup, db):
    denied = httpx.Response(403, json={"error": {"code": "Authorization_RequestDenied"}})
    before = count_snapshots(db)

    response = api(setup.consultant, transport=sample_transport({"/v1.0/subscribedSkus": denied})).post(url(setup))

    assert response.status_code == 502
    assert "Authorization_RequestDenied" in response.json()["detail"]
    assert "permissions" in response.json()["detail"]
    assert count_snapshots(db) == before


def test_an_unreachable_tenant_stores_nothing(api, setup, db):
    def offline(request):
        raise httpx.ConnectError("no route to host", request=request)

    before = count_snapshots(db)
    response = api(setup.consultant, transport=httpx.MockTransport(offline)).post(url(setup))

    assert response.status_code == 502
    assert "Could not reach" in response.json()["detail"]
    assert count_snapshots(db) == before


def test_collection_is_refused_while_turned_off(api, setup, db):
    before = count_snapshots(db)
    response = api(setup.consultant, settings=Settings(_env_file=None)).post(url(setup))

    assert response.status_code == 409
    assert "MS365_DATA_MODE" in response.json()["detail"]
    assert count_snapshots(db) == before


def test_only_the_linked_organization_can_read_the_real_tenant(api, setup, db):
    other = make_organization(db)
    response = api(setup.consultant, settings=graph_settings(other.id), transport=sample_transport()).post(url(setup))

    assert response.status_code == 409
    assert "not linked" in response.json()["detail"]


def test_the_linked_organization_reads_the_tenant_through_graph(api, setup):
    settings = graph_settings(setup.organization.id)
    response = api(setup.consultant, settings=settings, transport=sample_transport()).post(url(setup))

    assert response.status_code == 201, response.text
    assert response.json()["source"] == "microsoft_graph"


def test_a_representative_can_neither_collect_nor_read(api, setup):
    client = api(setup.representative)
    assert client.post(url(setup)).status_code == 403
    assert client.get(url(setup)).status_code == 403


def test_another_organization_gets_not_found(api, setup):
    snapshot = api(setup.consultant).post(url(setup)).json()
    client = api(setup.outsider)

    assert client.post(url(setup)).status_code == 404
    assert client.get(url(setup)).status_code == 404
    assert client.get(url(setup, f"/{snapshot['id']}")).status_code == 404

"""The run endpoints enforce access, assessment state, and transaction boundaries."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.api.v1.endpoints import gaps as endpoints
from app.main import app
from app.security.auth import get_current_user
from app.services.gaps import build_gap_list
from tests.test_gaps import consultant_version, report_input


@pytest.fixture
def context(monkeypatch):
    data = report_input(**{"PR.AA-03": [consultant_version("not_implemented")]})
    user = SimpleNamespace(id=uuid4())
    db = Mock(spec=Session)
    run = SimpleNamespace(
        id=uuid4(),
        organization_id=data.organization.id,
        assessment_id=data.assessment.id,
        trigger="regeneration",
        requested_by_user_id=user.id,
        created_at=datetime.now(timezone.utc),
        gap_count=1,
        snapshot=build_gap_list(data, datetime.now(timezone.utc)).model_dump(mode="json"),
    )
    load = Mock(return_value=data)
    access = Mock()
    record = Mock(return_value=run)
    list_runs = Mock(return_value=[run])
    monkeypatch.setattr(endpoints, "load_report_input", load)
    monkeypatch.setattr(endpoints, "require_expert_review_access", access)
    monkeypatch.setattr(endpoints, "record_gap_analysis_run", record)
    monkeypatch.setattr(endpoints, "list_gap_analysis_runs", list_runs)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db_session] = lambda: db
    yield SimpleNamespace(
        client=TestClient(app), data=data, db=db, user=user,
        load=load, access=access, record=record, list_runs=list_runs, run=run,
    )
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


def _url(context, action):
    return (
        f"/api/v1/organizations/{context.data.organization.id}/assessments/"
        f"{context.data.assessment.id}/gaps/{action}"
    )


def test_run_history_requires_report_access(context):
    context.load.side_effect = HTTPException(status_code=404, detail="Assessment not found.")

    response = context.client.get(_url(context, "runs"))

    assert response.status_code == 404
    context.list_runs.assert_not_called()


def test_run_history_returns_saved_snapshot(context):
    response = context.client.get(_url(context, "runs"))

    assert response.status_code == 200
    assert response.json()[0]["gap_list"]["gaps"][0]["control_code"] == "PR.AA-03"
    context.list_runs.assert_called_once_with(
        context.db, context.data.organization.id, context.data.assessment.id
    )


def test_representative_cannot_regenerate(context):
    context.access.side_effect = HTTPException(status_code=403, detail="Consultant access required.")

    response = context.client.post(_url(context, "regenerate"))

    assert response.status_code == 403
    context.record.assert_not_called()
    context.db.commit.assert_not_called()


def test_regeneration_requires_completed_assessment_in_same_organization(context):
    context.db.scalar.return_value = None
    assert context.client.post(_url(context, "regenerate")).status_code == 404

    context.db.scalar.return_value = SimpleNamespace(status="awaiting_review")
    assert context.client.post(_url(context, "regenerate")).status_code == 409
    context.record.assert_not_called()
    context.db.commit.assert_not_called()


def test_consultant_regeneration_saves_one_run(context):
    context.db.scalar.return_value = SimpleNamespace(status="completed")

    response = context.client.post(_url(context, "regenerate"))

    assert response.status_code == 201
    assert response.json()["id"] == str(context.run.id)
    context.record.assert_called_once_with(
        context.db, context.data.organization.id, context.data.assessment.id,
        trigger="regeneration", requested_by_user_id=context.user.id,
    )
    context.db.commit.assert_called_once_with()

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.security.expert_reviews import require_expert_review_access


def test_allows_platform_administrator():
    db = Mock(spec=Session)
    user = SimpleNamespace(
        id=uuid4(),
        is_platform_admin=True,
    )

    require_expert_review_access(db, uuid4(), user)

    db.scalar.assert_not_called()


@pytest.mark.parametrize("role", ["administrator", "consultant"])
def test_allows_authorized_organization_member(role):
    db = Mock(spec=Session)
    db.scalar.return_value = SimpleNamespace(role=role)
    user = SimpleNamespace(
        id=uuid4(),
        is_platform_admin=False,
    )

    require_expert_review_access(db, uuid4(), user)

    db.scalar.assert_called_once()


def test_rejects_missing_active_membership():
    db = Mock(spec=Session)
    db.scalar.return_value = None
    user = SimpleNamespace(
        id=uuid4(),
        is_platform_admin=False,
    )

    with pytest.raises(HTTPException) as error:
        require_expert_review_access(db, uuid4(), user)

    assert error.value.status_code == 404
    assert error.value.detail == "Review result not found."


def test_rejects_representative():
    db = Mock(spec=Session)
    db.scalar.return_value = SimpleNamespace(role="representative")
    user = SimpleNamespace(
        id=uuid4(),
        is_platform_admin=False,
    )

    with pytest.raises(HTTPException) as error:
        require_expert_review_access(db, uuid4(), user)

    assert error.value.status_code == 403
    assert error.value.detail == "Administrator or consultant access required."


def test_membership_query_is_scoped_to_user_and_organization():
    db = Mock(spec=Session)
    db.scalar.return_value = SimpleNamespace(role="consultant")
    organization_id = uuid4()
    user = SimpleNamespace(
        id=uuid4(),
        is_platform_admin=False,
    )

    require_expert_review_access(db, organization_id, user)

    statement = db.scalar.call_args.args[0]
    compiled = statement.compile()
    parameters = compiled.params
    query = str(compiled)

    assert "organization_memberships.organization_id =" in query
    assert "organization_memberships.user_id =" in query
    assert "organization_memberships.status =" in query
    assert organization_id in parameters.values()
    assert user.id in parameters.values()
    assert "active" in parameters.values()
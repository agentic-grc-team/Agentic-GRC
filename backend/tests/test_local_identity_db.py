"""Integration tests for the local auth.users mirror on a plain PostgreSQL (the CI auth stub)."""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import User
from app.db.session import get_engine
from app.security.auth import _profile_for_identity
from app.security.supabase import SupabaseIdentity


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
    if session.scalar(text("SELECT to_regclass('auth.schema_migrations') IS NOT NULL")):
        session.close()
        transaction.rollback()
        connection.close()
        pytest.skip("These tests need the local auth.users stub, not a Supabase database.")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def mirror_settings(enabled: bool) -> Settings:
    return Settings(auth_mirror_local_identities=enabled)


def auth_rows(db: Session, user_id: uuid.UUID):
    return db.execute(
        text("SELECT email, email_confirmed_at FROM auth.users WHERE id = :id"), {"id": user_id}
    ).all()


def new_identity() -> SupabaseIdentity:
    user_id = uuid.uuid4()
    return SupabaseIdentity(user_id, f"mirror-{user_id}@example.com", True)


def test_first_login_creates_auth_row_and_profile(db):
    identity = new_identity()

    user = _profile_for_identity(identity, db, mirror_settings(True))

    assert user.id == identity.id
    rows = auth_rows(db, identity.id)
    assert len(rows) == 1
    assert rows[0].email == identity.email
    assert rows[0].email_confirmed_at is not None
    assert db.get(User, identity.id).email == identity.email


def test_changed_email_updates_both_tables(db):
    identity = new_identity()
    _profile_for_identity(identity, db, mirror_settings(True))

    changed = SupabaseIdentity(identity.id, f"changed-{identity.id}@example.com", True)
    user = _profile_for_identity(changed, db, mirror_settings(True))

    assert user.email == changed.email
    assert auth_rows(db, identity.id)[0].email == changed.email


def test_mirror_is_idempotent(db):
    identity = new_identity()
    _profile_for_identity(identity, db, mirror_settings(True))
    _profile_for_identity(identity, db, mirror_settings(True))

    assert len(auth_rows(db, identity.id)) == 1


def test_without_the_mirror_a_new_user_is_rejected(db):
    identity = new_identity()

    with pytest.raises(HTTPException) as response:
        _profile_for_identity(identity, db, mirror_settings(False))

    assert response.value.status_code == 401
    assert auth_rows(db, identity.id) == []

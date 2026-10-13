"""Evidence file metadata persistence and constraint integration tests."""

import hashlib
import uuid

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import EvidenceFile
from app.db.session import get_engine
from app.services.evidence import list_evidence_files, store_evidence_file
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


def store(db, organization, **changes):
    content = changes.pop("content", b"Valid compliance rules.")
    fields = dict(
        organization_id=organization.id,
        uploaded_by_user_id=None,
        assessment_id=None,
        original_filename="policy.txt",
        stored_filename=f"{organization.id}_{uuid.uuid4()}.txt",
        content_type="text/plain",
        file_extension=".txt",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        extracted_text=content.decode(),
    )
    fields.update(changes)
    return store_evidence_file(db, **fields)


def test_store_evidence_file_saves_metadata(db):
    organization = make_organization(db)
    user = make_user(db)
    assessment = make_assessment(db, organization)

    record = store(db, organization, uploaded_by_user_id=user.id, assessment_id=assessment.id)

    saved = db.get(EvidenceFile, record.id)
    assert saved.organization_id == organization.id
    assert saved.assessment_id == assessment.id
    assert saved.uploaded_by_user_id == user.id
    assert saved.original_filename == "policy.txt"
    assert saved.file_extension == ".txt"
    assert saved.size_bytes == len(b"Valid compliance rules.")
    assert saved.sha256 == hashlib.sha256(b"Valid compliance rules.").hexdigest()
    assert saved.extracted_text == "Valid compliance rules."
    assert saved.created_at is not None


def test_evidence_without_assessment_is_accepted(db):
    organization = make_organization(db)

    record = store(db, organization)

    assert record.assessment_id is None


def test_list_evidence_files_returns_only_requested_organization(db):
    org_a = make_organization(db)
    org_b = make_organization(db)
    mine = store(db, org_a)
    store(db, org_b)

    listed = list_evidence_files(db, org_a.id)

    assert [item.id for item in listed] == [mine.id]


def test_list_evidence_files_filters_by_assessment(db):
    organization = make_organization(db)
    assessment = make_assessment(db, organization)
    linked = store(db, organization, assessment_id=assessment.id)
    store(db, organization)

    assert [item.id for item in list_evidence_files(db, organization.id, assessment.id)] == [linked.id]
    assert len(list_evidence_files(db, organization.id)) == 2


def test_evidence_for_assessment_of_another_organization_rejected(db):
    org_a = make_organization(db)
    org_b = make_organization(db)
    assessment_b = make_assessment(db, org_b)

    with pytest.raises(IntegrityError, match="fk_evidence_files_assessment_same_org"):
        store(db, org_a, assessment_id=assessment_b.id)


def test_evidence_for_unknown_organization_rejected(db):
    organization = make_organization(db)
    organization.id = uuid.uuid4()

    with pytest.raises(IntegrityError, match="fk_evidence_files_organization_id_organizations"):
        store(db, organization)


@pytest.mark.parametrize(
    "changes, constraint",
    [
        ({"original_filename": "   "}, "ck_evidence_files_filename_not_blank"),
        ({"file_extension": ".exe"}, "ck_evidence_files_file_extension"),
        ({"size_bytes": 0}, "ck_evidence_files_size_bytes"),
        ({"size_bytes": 10 * 1024 * 1024 + 1}, "ck_evidence_files_size_bytes"),
        ({"sha256": "not-a-hash"}, "ck_evidence_files_sha256_format"),
        ({"sha256": "A" * 64}, "ck_evidence_files_sha256_format"),
    ],
)
def test_invalid_evidence_metadata_rejected(db, changes, constraint):
    organization = make_organization(db)

    with pytest.raises(IntegrityError, match=constraint):
        store(db, organization, **changes)


def test_stored_filename_must_be_unique(db):
    organization = make_organization(db)
    store(db, organization, stored_filename="duplicate.txt")

    with pytest.raises(IntegrityError, match="uq_evidence_files_stored_filename"):
        store(db, organization, stored_filename="duplicate.txt")

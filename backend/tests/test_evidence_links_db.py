"""Evidence-to-control link persistence and constraint integration tests."""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import EvidenceControlLink
from app.db.session import get_engine
from app.services.evidence_links import (
    ControlNotFoundError,
    EvidenceAssessmentMismatchError,
    EvidenceNotFoundError,
    link_evidence_to_control,
    list_evidence_for_control,
    list_links_for_assessment,
    unlink_evidence_from_control,
)
from tests.test_assessments_db import make_assessment, make_control, make_organization, make_user
from tests.test_evidence_db import store


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


def make_context(db):
    organization = make_organization(db)
    assessment = make_assessment(db, organization)
    control = make_control(db, organization, assessment)
    return organization, assessment, control


def test_link_stores_organization_assessment_and_user(db):
    organization, assessment, control = make_context(db)
    user = make_user(db)
    evidence = store(db, organization, assessment_id=assessment.id)

    link, created = link_evidence_to_control(db, organization.id, evidence.id, control.id, user.id)

    assert created is True
    saved = db.get(EvidenceControlLink, link.id)
    assert saved.organization_id == organization.id
    assert saved.assessment_id == assessment.id
    assert saved.assessment_control_id == control.id
    assert saved.evidence_file_id == evidence.id
    assert saved.linked_by_user_id == user.id
    assert saved.created_at is not None


def test_linking_the_same_pair_twice_returns_the_existing_link(db):
    organization, assessment, control = make_context(db)
    evidence = store(db, organization, assessment_id=assessment.id)

    first, first_created = link_evidence_to_control(db, organization.id, evidence.id, control.id, None)
    second, second_created = link_evidence_to_control(db, organization.id, evidence.id, control.id, None)

    assert (first_created, second_created) == (True, False)
    assert second.id == first.id
    assert db.query(EvidenceControlLink).count() == 1


def test_evidence_without_assessment_can_be_linked_to_a_control(db):
    organization, _, control = make_context(db)
    evidence = store(db, organization)

    link, created = link_evidence_to_control(db, organization.id, evidence.id, control.id, None)

    assert created is True
    assert link.assessment_id == control.assessment_id


def test_one_file_can_support_several_controls(db):
    organization, assessment, control = make_context(db)
    other_control = make_control(db, organization, assessment, control_code="PR.AA-05")
    evidence = store(db, organization, assessment_id=assessment.id)

    link_evidence_to_control(db, organization.id, evidence.id, control.id, None)
    link_evidence_to_control(db, organization.id, evidence.id, other_control.id, None)

    assert [item.id for item in list_evidence_for_control(db, organization.id, control.id)] == [evidence.id]
    assert [item.id for item in list_evidence_for_control(db, organization.id, other_control.id)] == [evidence.id]


def test_evidence_of_another_assessment_cannot_be_linked(db):
    organization, assessment, control = make_context(db)
    other_assessment = make_assessment(db, organization)
    evidence = store(db, organization, assessment_id=other_assessment.id)

    with pytest.raises(EvidenceAssessmentMismatchError):
        link_evidence_to_control(db, organization.id, evidence.id, control.id, None)

    assert db.query(EvidenceControlLink).count() == 0


def test_evidence_of_another_organization_cannot_be_linked(db):
    organization, _, control = make_context(db)
    other_organization = make_organization(db)
    foreign_evidence = store(db, other_organization)

    with pytest.raises(EvidenceNotFoundError):
        link_evidence_to_control(db, organization.id, foreign_evidence.id, control.id, None)

    assert db.query(EvidenceControlLink).count() == 0


def test_control_of_another_organization_cannot_be_linked(db):
    organization, assessment, _ = make_context(db)
    _, _, foreign_control = make_context(db)
    evidence = store(db, organization, assessment_id=assessment.id)

    with pytest.raises(ControlNotFoundError):
        link_evidence_to_control(db, organization.id, evidence.id, foreign_control.id, None)

    assert db.query(EvidenceControlLink).count() == 0


def test_unknown_ids_are_not_found(db):
    organization, assessment, control = make_context(db)
    evidence = store(db, organization, assessment_id=assessment.id)

    with pytest.raises(EvidenceNotFoundError):
        link_evidence_to_control(db, organization.id, uuid.uuid4(), control.id, None)
    with pytest.raises(ControlNotFoundError):
        link_evidence_to_control(db, organization.id, evidence.id, uuid.uuid4(), None)


def test_list_for_control_returns_only_linked_evidence_of_the_organization(db):
    organization, assessment, control = make_context(db)
    linked = store(db, organization, assessment_id=assessment.id)
    store(db, organization, assessment_id=assessment.id)
    link_evidence_to_control(db, organization.id, linked.id, control.id, None)

    other_organization = make_organization(db)

    assert [item.id for item in list_evidence_for_control(db, organization.id, control.id)] == [linked.id]
    assert list_evidence_for_control(db, other_organization.id, control.id) == []


def test_list_for_control_with_assessment_requires_the_control_to_belong_to_it(db):
    organization, assessment_a, control_a = make_context(db)
    assessment_b = make_assessment(db, organization)
    control_b = make_control(db, organization, assessment_b)
    evidence_a = store(db, organization, assessment_id=assessment_a.id)
    evidence_b = store(db, organization, assessment_id=assessment_b.id)
    link_evidence_to_control(db, organization.id, evidence_a.id, control_a.id, None)
    link_evidence_to_control(db, organization.id, evidence_b.id, control_b.id, None)

    matching = list_evidence_for_control(db, organization.id, control_a.id, assessment_a.id)
    mismatched = list_evidence_for_control(db, organization.id, control_a.id, assessment_b.id)
    without_assessment = list_evidence_for_control(db, organization.id, control_a.id)

    assert [item.id for item in matching] == [evidence_a.id]
    assert mismatched == []
    assert [item.id for item in without_assessment] == [evidence_a.id]


def test_unlink_removes_only_the_requested_link(db):
    organization, assessment, control = make_context(db)
    other_control = make_control(db, organization, assessment, control_code="PR.AA-05")
    evidence = store(db, organization, assessment_id=assessment.id)
    link_evidence_to_control(db, organization.id, evidence.id, control.id, None)
    link_evidence_to_control(db, organization.id, evidence.id, other_control.id, None)

    removed = unlink_evidence_from_control(db, organization.id, evidence.id, control.id)

    assert removed is True
    assert list_evidence_for_control(db, organization.id, control.id) == []
    assert [item.id for item in list_evidence_for_control(db, organization.id, other_control.id)] == [evidence.id]
    assert unlink_evidence_from_control(db, organization.id, evidence.id, control.id) is False


def test_unlink_cannot_remove_a_link_of_another_organization(db):
    organization, assessment, control = make_context(db)
    evidence = store(db, organization, assessment_id=assessment.id)
    link_evidence_to_control(db, organization.id, evidence.id, control.id, None)
    other_organization = make_organization(db)

    removed = unlink_evidence_from_control(db, other_organization.id, evidence.id, control.id)

    assert removed is False
    assert len(list_evidence_for_control(db, organization.id, control.id)) == 1


def test_link_row_with_control_of_another_organization_rejected_by_database(db):
    organization, assessment, _ = make_context(db)
    other_organization, _, foreign_control = make_context(db)
    evidence = store(db, organization, assessment_id=assessment.id)

    db.add(
        EvidenceControlLink(
            organization_id=organization.id,
            assessment_id=foreign_control.assessment_id,
            assessment_control_id=foreign_control.id,
            evidence_file_id=evidence.id,
        )
    )
    with pytest.raises(IntegrityError, match="fk_evidence_control_links_control_same_assessment"):
        db.commit()


def test_link_row_with_evidence_of_another_organization_rejected_by_database(db):
    organization, assessment, control = make_context(db)
    other_organization = make_organization(db)
    foreign_evidence = store(db, other_organization)

    db.add(
        EvidenceControlLink(
            organization_id=organization.id,
            assessment_id=assessment.id,
            assessment_control_id=control.id,
            evidence_file_id=foreign_evidence.id,
        )
    )
    with pytest.raises(IntegrityError, match="fk_evidence_control_links_evidence_same_org"):
        db.commit()


def test_duplicate_link_rejected_by_database(db):
    organization, assessment, control = make_context(db)
    evidence = store(db, organization, assessment_id=assessment.id)
    fields = dict(
        organization_id=organization.id,
        assessment_id=assessment.id,
        assessment_control_id=control.id,
        evidence_file_id=evidence.id,
    )
    db.add(EvidenceControlLink(**fields))
    db.commit()

    db.add(EvidenceControlLink(**fields))
    with pytest.raises(IntegrityError, match="uq_evidence_control_links_control_evidence"):
        db.commit()

def test_assessment_links_are_scoped_to_the_assessment_and_organization(db):
    organization, assessment, control = make_context(db)
    other_assessment = make_assessment(db, organization)
    other_control = make_control(db, organization, other_assessment)
    other_organization = make_organization(db)
    foreign_assessment = make_assessment(db, other_organization)
    foreign_control = make_control(db, other_organization, foreign_assessment)

    mine = store(db, organization, assessment_id=assessment.id)
    elsewhere = store(db, organization, assessment_id=other_assessment.id)
    foreign = store(db, other_organization, assessment_id=foreign_assessment.id)

    link_evidence_to_control(db, organization.id, mine.id, control.id, None)
    link_evidence_to_control(db, organization.id, elsewhere.id, other_control.id, None)
    link_evidence_to_control(db, other_organization.id, foreign.id, foreign_control.id, None)

    links = list_links_for_assessment(db, organization.id, assessment.id)

    assert [(link.evidence_file_id, link.assessment_control_id) for link in links] == [(mine.id, control.id)]
    assert list_links_for_assessment(db, organization.id, foreign_assessment.id) == []

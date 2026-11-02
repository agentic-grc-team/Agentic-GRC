"""Start, list and read assessments (AGRC-61) and their scope (AGRC-63)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.api.v1.endpoints.organizations import _active_membership
from app.db.models import Organization, User
from app.schemas.assessments import (
    AssessmentControlRead,
    AssessmentCreate,
    AssessmentRead,
    AssessmentScopeRead,
)
from app.security.auth import get_current_user
from app.services.assessment_scope import group_controls_by_domain
from app.services.assessments import (
    get_assessment,
    list_assessments,
    list_in_scope_controls,
    start_assessment,
)

router = APIRouter(prefix="/organizations", tags=["assessments"])

# Aligo scopes the assessment (process stage 1). HU-04 mentions the representative; revisit with the team.
ASSESSMENT_CREATOR_ROLES = ("administrator", "consultant")


def _require_assessment_access(
    db: Session,
    organization_id: UUID,
    user: User,
    required_roles: tuple[str, ...] | None = None,
) -> None:
    if user.is_platform_admin:
        if db.get(Organization, organization_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found.",
            )
        return

    membership = _active_membership(db, organization_id, user.id)
    if membership is None:
        # Same answer as for an organization that does not exist, so nothing leaks.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found.",
        )
    if required_roles is not None and membership.role not in required_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators and consultants can start an assessment.",
        )


@router.post(
    "/{organization_id}/assessments",
    response_model=AssessmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_assessment(
    organization_id: UUID,
    data: AssessmentCreate,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> AssessmentRead:
    _require_assessment_access(db, organization_id, user, required_roles=ASSESSMENT_CREATOR_ROLES)
    record = start_assessment(db, organization_id, user.id, data)
    return AssessmentRead.model_validate(record)


@router.get(
    "/{organization_id}/assessments",
    response_model=list[AssessmentRead],
)
def read_assessments(
    organization_id: UUID,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> list[AssessmentRead]:
    _require_assessment_access(db, organization_id, user)
    records = list_assessments(db, organization_id)
    return [AssessmentRead.model_validate(record) for record in records]


@router.get(
    "/{organization_id}/assessments/{assessment_id}",
    response_model=AssessmentRead,
)
def read_assessment(
    organization_id: UUID,
    assessment_id: UUID,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> AssessmentRead:
    _require_assessment_access(db, organization_id, user)
    record = get_assessment(db, organization_id, assessment_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found.",
        )
    return AssessmentRead.model_validate(record)


@router.get(
    "/{organization_id}/assessments/{assessment_id}/scope",
    response_model=AssessmentScopeRead,
)
def read_assessment_scope(
    organization_id: UUID,
    assessment_id: UUID,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> AssessmentScopeRead:
    """The CSF 2.0 functions, categories and controls in scope (HU-04). Every member can see it."""
    _require_assessment_access(db, organization_id, user)
    record = get_assessment(db, organization_id, assessment_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found.",
        )
    organization = db.get(Organization, organization_id)
    controls = list_in_scope_controls(db, organization_id, assessment_id)
    return AssessmentScopeRead(
        organization_id=organization_id,
        organization_name=organization.name,
        assessment=AssessmentRead.model_validate(record),
        control_count=len(controls),
        functions=group_controls_by_domain(
            [(control.control_code, control.control_title) for control in controls]
        ),
    )


@router.get(
    "/{organization_id}/assessments/{assessment_id}/controls",
    response_model=list[AssessmentControlRead],
)
def read_assessment_controls(
    organization_id: UUID,
    assessment_id: UUID,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> list[AssessmentControlRead]:
    """The in-scope controls with their ids, so evidence can be linked to them."""
    _require_assessment_access(db, organization_id, user)
    if get_assessment(db, organization_id, assessment_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found.",
        )
    return [
        AssessmentControlRead.model_validate(control)
        for control in list_in_scope_controls(db, organization_id, assessment_id)
    ]

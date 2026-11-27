from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.api.v1.endpoints.organizations import _active_membership
from app.db.models import User
from app.schemas.passage_matches import PassageLocator, PassageMatchList, PassageMatchRead
from app.security.auth import get_current_user
from app.services.assessments import get_assessment
from app.services.evidence_links import document_reference
from app.services.passage_matching import MATCHER_VERSION, MIN_MATCH_CONFIDENCE, find_passage_matches

router = APIRouter(prefix="/organizations", tags=["passage-matches"])


@router.get(
    "/{organization_id}/assessments/{assessment_id}/passage-matches",
    response_model=PassageMatchList,
)
def get_passage_matches(
    organization_id: UUID,
    assessment_id: UUID,
    evidence_file_id: UUID | None = Query(None),
    min_confidence: float = Query(MIN_MATCH_CONFIDENCE, ge=0, le=1),
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> PassageMatchList:
    """Passages of the organization's uploaded documents that are relevant to this assessment's controls.

    The excerpts are document content, so the access rule is the one for evidence files: an active
    member of the organization, whatever the role. Anyone else gets 404, as for a missing assessment.
    """
    if _active_membership(db, organization_id, user.id) is None or get_assessment(
        db, organization_id, assessment_id
    ) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found.")

    result = find_passage_matches(
        db,
        organization_id,
        assessment_id,
        evidence_file_id=evidence_file_id,
        min_confidence=min_confidence,
    )
    return PassageMatchList(
        organization_id=organization_id,
        assessment_id=assessment_id,
        matcher_version=MATCHER_VERSION,
        min_confidence=min_confidence,
        files_checked=result.files_checked,
        controls_without_terms=result.controls_without_terms,
        matches=[
            PassageMatchRead(
                organization_id=organization_id,
                assessment_id=assessment_id,
                assessment_control_id=item.assessment_control_id,
                control_code=item.control_code,
                evidence_file_id=item.evidence_file_id,
                file_name=item.file_name,
                reference=document_reference(item.evidence_file_id, item.match.passage.page),
                locator=PassageLocator(
                    page=item.match.passage.page,
                    section=item.match.passage.section,
                    char_start=item.match.passage.char_start,
                    char_end=item.match.passage.char_end,
                ),
                excerpt=item.match.excerpt,
                matched_terms=list(item.match.matched_terms),
                confidence=item.match.confidence,
                matcher_version=MATCHER_VERSION,
                linked=item.linked,
            )
            for item in result.matches
        ],
    )

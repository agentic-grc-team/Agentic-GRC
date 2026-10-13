from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import OrganizationMembership, User


def require_expert_review_access(
    db: Session,
    organization_id: UUID,
    user: User,
) -> None:
    if user.is_platform_admin:
        return

    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.status == "active",
        )
    )

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review result not found.",
        )

    if membership.role not in ("administrator", "consultant"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator or consultant access required.",
        )
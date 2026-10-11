from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.core.config import Settings, get_settings
from app.db.models import (
    IndustrySector,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    OrganizationSize,
    User,
)
from app.schemas.organizations import (
    InvitationAccepted,
    InvitationCreate,
    InvitationCreated,
    InvitationSummary,
    OrganizationCreate,
    OrganizationCreated,
    OrganizationSummary,
    OrganizationUpdate,
)
from app.security.auth import get_current_user
from app.security.invitations import create_invitation_token
from app.services.email import EmailDeliveryError, send_invitation_email


router = APIRouter(prefix="/organizations", tags=["organizations"])
INVITATION_TTL = timedelta(days=7)


def _normalized(value: str) -> str:
    return value.strip().lower()


def _active_membership(db: Session, organization_id: UUID, user_id: UUID) -> OrganizationMembership | None:
    return db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.status == "active",
        )
    )


def _is_organization_administrator(db: Session, user: User) -> bool:
    if user.is_platform_admin:
        return True
    return (
        db.scalar(
            select(OrganizationMembership.id).where(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.role == "administrator",
                OrganizationMembership.status == "active",
            ).limit(1)
        )
        is not None
    )


def _organization_administrator(
    db: Session, organization_id: UUID, user: User
) -> bool:
    if user.is_platform_admin:
        return True
    membership = _active_membership(db, organization_id, user.id)
    return membership is not None and membership.role == "administrator"


def _duplicate_matches(db: Session, name: str, exclude_id: UUID | None = None) -> list[Organization]:
    statement = (
        select(Organization)
        .where(func.lower(func.btrim(Organization.name)) == _normalized(name))
        .order_by(Organization.created_at, Organization.id)
    )
    if exclude_id is not None:
        statement = statement.where(Organization.id != exclude_id)
    return list(db.scalars(statement))


def _organization_summary(organization: Organization, role: str) -> OrganizationSummary:
    return OrganizationSummary(
        id=organization.id,
        name=organization.name,
        sector_code=organization.sector_code,
        sector=organization.industry_sector.label,
        size_code=organization.size_code,
        size=organization.organization_size.label,
        created_at=organization.created_at,
        role=role,
    )


def _load_organization(db: Session, organization_id: UUID) -> Organization | None:
    return db.scalar(
        select(Organization)
        .where(Organization.id == organization_id)
        .execution_options(populate_existing=True)
    )


@router.post("", response_model=OrganizationCreated, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> OrganizationCreated:
    if not _is_organization_administrator(db, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An organization administrator is required to create organizations.",
        )
    try:
        db.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(_normalized(payload.name), 0)))
        )
        matches = _duplicate_matches(db, payload.name)
        selected_duplicate: Organization | None = None
        if matches:
            if payload.confirm_duplicate_of is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "duplicate_name_requires_confirmation",
                        "message": "An organization with this name already exists. Confirm which one is a duplicate of, or choose another name.",
                        "matches": [{"id": str(org.id), "name": org.name} for org in matches],
                    },
                )
            selected_duplicate = next(
                (org for org in matches if org.id == payload.confirm_duplicate_of), None
            )
            if selected_duplicate is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The selected duplicate no longer matches. Refresh and confirm again.",
                )
        elif payload.confirm_duplicate_of is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No duplicate with this name exists anymore. Retry without confirmation.",
            )

        sector = db.get(IndustrySector, payload.sector_code)
        organization_size = db.get(OrganizationSize, payload.size_code)
        if sector is None or organization_size is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Choose a valid industry sector and organization size.",
            )

        organization = Organization(
            name=payload.name,
            sector_code=sector.code,
            size_code=organization_size.code,
            created_by_user_id=user.id,
            duplicate_of_organization_id=selected_duplicate.id if selected_duplicate else None,
            duplicate_name_confirmed_at=datetime.now(timezone.utc) if selected_duplicate else None,
            duplicate_name_confirmed_by_user_id=user.id if selected_duplicate else None,
        )
        db.add(organization)
        db.flush()
        db.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=user.id,
                role="administrator",
                status="active",
            )
        )
        db.commit()
        organization = _load_organization(db, organization.id)
        assert organization is not None
        return OrganizationCreated(
            **_organization_summary(organization, "administrator").model_dump()
        )
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The organization or membership conflicts with existing data. Refresh and retry.",
        ) from exc


@router.get("", response_model=list[OrganizationSummary])
def list_organizations(
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> list[OrganizationSummary]:
    statement = (
        select(Organization, OrganizationMembership.role)
        .outerjoin(
            OrganizationMembership,
            (OrganizationMembership.organization_id == Organization.id)
            & (OrganizationMembership.user_id == user.id)
            & (OrganizationMembership.status == "active"),
        )
        .order_by(Organization.created_at.desc())
    )
    if not user.is_platform_admin:
        statement = statement.where(OrganizationMembership.id.is_not(None))
    rows = db.execute(statement).all()
    return [
        _organization_summary(organization, role or "administrator")
        for organization, role in rows
    ]


@router.get("/{organization_id}", response_model=OrganizationSummary)
def get_organization(
    organization_id: UUID,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> OrganizationSummary:
    row = db.execute(
        select(Organization, OrganizationMembership.role)
        .outerjoin(
            OrganizationMembership,
            (OrganizationMembership.organization_id == Organization.id)
            & (OrganizationMembership.user_id == user.id)
            & (OrganizationMembership.status == "active"),
        )
        .where(Organization.id == organization_id)
    ).first()
    if row is None or (row[1] is None and not user.is_platform_admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    organization, role = row
    return _organization_summary(organization, role or "administrator")


@router.patch("/{organization_id}", response_model=OrganizationSummary)
def update_organization(
    organization_id: UUID,
    payload: OrganizationUpdate,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> OrganizationSummary:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    membership = _active_membership(db, organization_id, user.id)
    if not user.is_platform_admin and (membership is None or membership.role != "administrator"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization administrator access required.")

    changes = payload.model_dump(exclude_unset=True)
    new_name = changes.get("name", organization.name)
    new_sector_code = changes.get("sector_code", organization.sector_code)
    new_size_code = changes.get("size_code", organization.size_code)
    name_changed = new_name != organization.name
    name_identity_changed = _normalized(new_name) != _normalized(organization.name)
    selected_duplicate: Organization | None = None
    if name_identity_changed:
        db.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(_normalized(new_name), 0)))
        )
        matches = _duplicate_matches(db, new_name, organization_id)
        duplicate_id = changes.get("confirm_duplicate_of")
        if matches and duplicate_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "duplicate_name_requires_confirmation",
                    "matches": [{"id": str(item.id), "name": item.name} for item in matches],
                },
            )
        if duplicate_id is not None:
            selected_duplicate = next((item for item in matches if item.id == duplicate_id), None)
            if selected_duplicate is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The selected duplicate no longer matches.")

    sector = db.get(IndustrySector, new_sector_code)
    organization_size = db.get(OrganizationSize, new_size_code)
    if sector is None or organization_size is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Choose a valid industry sector and organization size.",
        )

    if name_changed:
        organization.name = new_name
    if name_identity_changed:
        organization.duplicate_of_organization_id = selected_duplicate.id if selected_duplicate else None
        organization.duplicate_name_confirmed_at = datetime.now(timezone.utc) if selected_duplicate else None
        organization.duplicate_name_confirmed_by_user_id = user.id if selected_duplicate else None
    organization.sector_code = sector.code
    organization.size_code = organization_size.code
    try:
        db.commit()
        organization = _load_organization(db, organization_id)
        assert organization is not None
        return _organization_summary(organization, membership.role if membership else "administrator")
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Organization update conflicts with existing data.") from exc


@router.post(
    "/{organization_id}/invitations",
    response_model=InvitationCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(
    organization_id: UUID,
    payload: InvitationCreate,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> InvitationCreated:
    if not _organization_administrator(db, organization_id, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active administrator membership required.")

    email = str(payload.email).strip().lower()
    now = datetime.now(timezone.utc)
    try:
        db.execute(
            update(OrganizationInvitation)
            .where(
                OrganizationInvitation.organization_id == organization_id,
                OrganizationInvitation.status == "pending",
                OrganizationInvitation.expires_at <= now,
            )
            .values(status="expired", token_hash=None)
        )
        existing_member = db.scalar(
            select(OrganizationMembership)
            .join(User, User.id == OrganizationMembership.user_id)
            .where(
                OrganizationMembership.organization_id == organization_id,
                func.lower(func.btrim(User.email)) == email,
            )
        )
        if existing_member:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This user already has a membership in the organization.")
        pending = db.scalar(
            select(OrganizationInvitation).where(
                OrganizationInvitation.organization_id == organization_id,
                func.lower(func.btrim(OrganizationInvitation.email)) == email,
                OrganizationInvitation.status == "pending",
            )
        )
        if pending:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A pending invitation already exists for this email.")
        token, token_hash = create_invitation_token()
        invitation = OrganizationInvitation(
            organization_id=organization_id,
            email=email,
            role=payload.role,
            status="pending",
            invited_by_user_id=user.id,
            expires_at=now + INVITATION_TTL,
            token_hash=token_hash,
        )
        db.add(invitation)
        db.flush()
        organization = db.get(Organization, organization_id)
        assert organization is not None
        send_invitation_email(
            settings,
            recipient=email,
            organization_name=organization.name,
            role=payload.role,
            token=token,
            expires_at=invitation.expires_at,
        )
        db.commit()
        db.refresh(invitation)
        return InvitationCreated(
            id=invitation.id,
            organization_id=invitation.organization_id,
            email=invitation.email,
            role=payload.role,
            status="pending",
            expires_at=invitation.expires_at,
            delivery_status="sent",
        )
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A pending invitation or membership already exists for this email.") from exc
    except EmailDeliveryError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The invitation could not be sent. Configure SMTP and try again.",
        ) from exc


@router.get("/me/invitations", response_model=list[InvitationSummary])
def list_my_invitations(
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> list[InvitationSummary]:
    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(OrganizationInvitation, Organization.name)
        .join(Organization, Organization.id == OrganizationInvitation.organization_id)
        .where(
            func.lower(func.btrim(OrganizationInvitation.email)) == user.email,
            OrganizationInvitation.status == "pending",
            OrganizationInvitation.expires_at > now,
        )
        .order_by(OrganizationInvitation.created_at.desc())
    ).all()
    return [
        InvitationSummary(
            id=invitation.id,
            organization_id=invitation.organization_id,
            organization_name=name,
            role=invitation.role,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
        )
        for invitation, name in rows
    ]


@router.post("/invitations/{invitation_id}/accept", response_model=InvitationAccepted)
def accept_invitation(
    invitation_id: UUID,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> InvitationAccepted:
    now = datetime.now(timezone.utc)
    try:
        invitation = db.scalar(
            select(OrganizationInvitation)
            .where(OrganizationInvitation.id == invitation_id)
            .with_for_update()
        )
        if invitation is None or _normalized(invitation.email) != _normalized(user.email):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found.")
        if invitation.status != "pending" or invitation.expires_at <= now:
            if invitation.status == "pending" and invitation.expires_at <= now:
                invitation.status = "expired"
                invitation.token_hash = None
                db.commit()
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="This invitation is no longer active.")
        existing_membership = db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == invitation.organization_id,
                OrganizationMembership.user_id == user.id,
            )
        )
        if existing_membership:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This user already has a membership in the organization.")

        db.add(
            OrganizationMembership(
                organization_id=invitation.organization_id,
                user_id=user.id,
                role=invitation.role,
                status="active",
            )
        )
        invitation.status = "accepted"
        invitation.accepted_by_user_id = user.id
        invitation.accepted_at = now
        invitation.token_hash = None
        db.commit()
        return InvitationAccepted(
            invitation_id=invitation.id,
            organization_id=invitation.organization_id,
            email=user.email,
            role=invitation.role,
            membership_status="active",
        )
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The invitation could not be accepted because membership already exists.") from exc

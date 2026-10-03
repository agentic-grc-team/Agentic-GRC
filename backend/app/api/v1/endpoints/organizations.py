from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.db.models import Organization, OrganizationInvitation, OrganizationMembership, User
from app.schemas.organizations import (
    InvitationAccepted,
    InvitationCreate,
    InvitationCreated,
    InvitationSummary,
    OrganizationCreate,
    OrganizationCreated,
    OrganizationSummary,
)
from app.security.auth import AuthenticatedIdentity, get_authenticated_identity


router = APIRouter(prefix="/organizations", tags=["organizations"])
INVITATION_TTL = timedelta(days=7)  # Provisional until the product team sets a policy.


def _normalized(value: str) -> str:
    return value.strip().lower()


def _resolve_user(
    db: Session,
    identity: AuthenticatedIdentity,
    *,
    create: bool,
) -> User | None:
    user = db.scalar(
        select(User).where(
            User.oidc_issuer == identity.issuer,
            User.oidc_subject == identity.subject,
        )
    )
    if user:
        if _normalized(user.email) != identity.email:
            email_owner = db.scalar(
                select(User).where(func.lower(func.btrim(User.email)) == identity.email)
            )
            if email_owner and email_owner.id != user.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This verified email is already associated with another account.",
                )
            user.email = identity.email
        return user

    user = db.scalar(select(User).where(func.lower(func.btrim(User.email)) == identity.email))
    if user:
        if user.oidc_issuer is not None or user.oidc_subject is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This verified email is already associated with another identity.",
            )
        user.oidc_issuer = identity.issuer
        user.oidc_subject = identity.subject
        return user

    if not create:
        return None
    user = User(email=identity.email, oidc_issuer=identity.issuer, oidc_subject=identity.subject)
    db.add(user)
    db.flush()
    return user


def _active_membership(db: Session, organization_id: UUID, user_id: UUID) -> OrganizationMembership | None:
    return db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.status == "active",
        )
    )


def _duplicate_matches(db: Session, name: str) -> list[Organization]:
    name_key = _normalized(name)
    return list(
        db.scalars(
            select(Organization)
            .where(func.lower(func.btrim(Organization.name)) == name_key)
            .order_by(Organization.created_at, Organization.id)
        )
    )


@router.post("", response_model=OrganizationCreated, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_authenticated_identity),
) -> OrganizationCreated:
    try:
        # Serialize duplicate checks for the same normalized name on PostgreSQL.
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
                        "message": "An organization with this name already exists. Confirm which one this is a duplicate of, or choose another name.",
                        "matches": [{"id": str(org.id), "name": org.name} for org in matches],
                    },
                )
            selected_duplicate = next(
                (org for org in matches if org.id == payload.confirm_duplicate_of), None
            )
            if selected_duplicate is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The selected duplicate is no longer a matching organization. Refresh and confirm again.",
                )
        elif payload.confirm_duplicate_of is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No duplicate with this name exists anymore. Retry without duplicate confirmation.",
            )

        user = _resolve_user(db, identity, create=True)
        assert user is not None
        organization = Organization(
            name=payload.name,
            sector=payload.sector,
            size=payload.size,
            created_by_user_id=user.id,
            duplicate_of_organization_id=selected_duplicate.id if selected_duplicate else None,
            duplicate_name_confirmed_at=datetime.now(timezone.utc) if selected_duplicate else None,
            duplicate_name_confirmed_by_user_id=user.id if selected_duplicate else None,
        )
        db.add(organization)
        db.flush()
        membership = OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role="administrator",
            status="active",
        )
        db.add(membership)
        db.commit()
        db.refresh(organization)
        return OrganizationCreated(
            id=organization.id,
            name=organization.name,
            sector=organization.sector,
            size=organization.size,
            created_at=organization.created_at,
        )
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The organization or user conflicts with existing data. Refresh and retry.",
        ) from exc


@router.get("", response_model=list[OrganizationSummary])
def list_organizations(
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_authenticated_identity),
) -> list[OrganizationSummary]:
    user = _resolve_user(db, identity, create=False)
    if user is None:
        return []
    rows = db.execute(
        select(Organization, OrganizationMembership.role)
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.status == "active",
        )
        .order_by(Organization.created_at.desc())
    ).all()
    return [
        OrganizationSummary(
            id=organization.id,
            name=organization.name,
            sector=organization.sector,
            size=organization.size,
            created_at=organization.created_at,
            role=role,
        )
        for organization, role in rows
    ]


@router.get("/{organization_id}", response_model=OrganizationSummary)
def get_organization(
    organization_id: UUID,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_authenticated_identity),
) -> OrganizationSummary:
    user = _resolve_user(db, identity, create=False)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    row = db.execute(
        select(Organization, OrganizationMembership.role)
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .where(
            Organization.id == organization_id,
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.status == "active",
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    organization, role = row
    return OrganizationSummary(
        id=organization.id,
        name=organization.name,
        sector=organization.sector,
        size=organization.size,
        created_at=organization.created_at,
        role=role,
    )


@router.post(
    "/{organization_id}/invitations",
    response_model=InvitationCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(
    organization_id: UUID,
    payload: InvitationCreate,
    response: Response,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_authenticated_identity),
) -> InvitationCreated:
    user = _resolve_user(db, identity, create=False)
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active administrator membership required.")
    membership = _active_membership(db, organization_id, user.id)
    if membership is None or membership.role != "administrator":
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
            .values(status="expired")
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
        organization = db.get(Organization, organization_id)
        assert organization is not None
        invitation = OrganizationInvitation(
            organization_id=organization_id,
            email=email,
            role="consultant",
            status="pending",
            invited_by_user_id=user.id,
            expires_at=now + INVITATION_TTL,
        )
        db.add(invitation)
        db.commit()
        db.refresh(invitation)
        response.headers["X-Invitation-Email-Delivery"] = "not-sent"
        return InvitationCreated(
            id=invitation.id,
            organization_id=invitation.organization_id,
            email=invitation.email,
            role="consultant",
            status="pending",
            expires_at=invitation.expires_at,
        )
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pending invitation or membership already exists for this email.",
        ) from exc


@router.get("/me/invitations", response_model=list[InvitationSummary])
def list_my_invitations(
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_authenticated_identity),
) -> list[InvitationSummary]:
    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(OrganizationInvitation, Organization.name)
        .join(Organization, Organization.id == OrganizationInvitation.organization_id)
        .where(
            func.lower(func.btrim(OrganizationInvitation.email)) == identity.email,
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
            role="consultant",
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
        )
        for invitation, name in rows
    ]


@router.post("/invitations/{invitation_id}/accept", response_model=InvitationAccepted)
def accept_invitation(
    invitation_id: UUID,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_authenticated_identity),
) -> InvitationAccepted:
    now = datetime.now(timezone.utc)
    try:
        invitation = db.scalar(
            select(OrganizationInvitation)
            .where(OrganizationInvitation.id == invitation_id)
            .with_for_update()
        )
        if invitation is None or _normalized(invitation.email) != identity.email:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found.")
        if invitation.status != "pending" or invitation.expires_at <= now:
            if invitation.status == "pending" and invitation.expires_at <= now:
                invitation.status = "expired"
                db.commit()
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="This invitation is no longer active.")

        user = _resolve_user(db, identity, create=True)
        assert user is not None
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
        db.commit()
        return InvitationAccepted(
            invitation_id=invitation.id,
            organization_id=invitation.organization_id,
            role="consultant",
            membership_status="active",
        )
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The invitation could not be accepted because membership already exists.") from exc

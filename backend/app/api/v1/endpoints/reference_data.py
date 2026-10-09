from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.db.models import IndustrySector, OrganizationSize, User
from app.schemas.organizations import CatalogOption
from app.security.auth import get_current_user


router = APIRouter(prefix="/reference-data", tags=["reference data"])


@router.get("/industry-sectors", response_model=list[CatalogOption])
def list_industry_sectors(
    db: Session = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> list[CatalogOption]:
    rows = db.scalars(select(IndustrySector).order_by(IndustrySector.label)).all()
    return [CatalogOption(code=row.code, label=row.label) for row in rows]


@router.get("/organization-sizes", response_model=list[CatalogOption])
def list_organization_sizes(
    db: Session = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> list[CatalogOption]:
    rows = db.scalars(select(OrganizationSize).order_by(OrganizationSize.label)).all()
    return [CatalogOption(code=row.code, label=row.label) for row in rows]

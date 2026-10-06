from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


InviteeRole = Literal["consultant", "representative"]


class CatalogOption(BaseModel):
    code: str
    label: str


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sector_code: str = Field(min_length=1, max_length=50)
    size_code: str = Field(min_length=1, max_length=30)
    confirm_duplicate_of: UUID | None = None

    @field_validator("name", "sector_code", "size_code")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank.")
        return value


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    sector_code: str | None = Field(default=None, min_length=1, max_length=50)
    size_code: str | None = Field(default=None, min_length=1, max_length=30)
    confirm_duplicate_of: UUID | None = None

    @field_validator("name", "sector_code", "size_code")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank.")
        return value


class OrganizationSummary(BaseModel):
    id: UUID
    name: str
    sector_code: str
    sector: str
    size_code: str
    size: str
    created_at: datetime
    role: str


class OrganizationCreated(OrganizationSummary):
    role: Literal["administrator"] = "administrator"


class InvitationCreate(BaseModel):
    email: EmailStr
    role: InviteeRole = "consultant"

    @field_validator("email", mode="after")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class InvitationCreated(BaseModel):
    id: UUID
    organization_id: UUID
    email: EmailStr
    role: InviteeRole
    status: Literal["pending"]
    expires_at: datetime
    delivery_status: Literal["sent", "not_sent"]


class InvitationSummary(BaseModel):
    id: UUID
    organization_id: UUID
    organization_name: str
    role: InviteeRole
    expires_at: datetime
    created_at: datetime


class InvitationAccept(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    password: str = Field(min_length=12, max_length=128)


class InvitationAccepted(BaseModel):
    invitation_id: UUID
    organization_id: UUID
    email: EmailStr
    role: InviteeRole
    membership_status: Literal["active"]

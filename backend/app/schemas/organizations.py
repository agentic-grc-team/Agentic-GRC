from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sector: str = Field(min_length=1, max_length=100)
    size: str = Field(min_length=1, max_length=50)
    confirm_duplicate_of: UUID | None = None

    @field_validator("name", "sector", "size")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank.")
        return value


class OrganizationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    sector: str
    size: str
    created_at: datetime
    role: str


class OrganizationCreated(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    sector: str
    size: str
    created_at: datetime
    role: Literal["administrator"] = "administrator"


class InvitationCreate(BaseModel):
    email: EmailStr

    @field_validator("email", mode="after")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class InvitationCreated(BaseModel):
    id: UUID
    organization_id: UUID
    email: EmailStr
    role: Literal["consultant"]
    status: Literal["pending"]
    expires_at: datetime
    delivery_status: Literal["not_sent"] = "not_sent"
    message: str = "Invitation saved. Email delivery is not configured yet."


class InvitationSummary(BaseModel):
    id: UUID
    organization_id: UUID
    organization_name: str
    role: Literal["consultant"]
    expires_at: datetime
    created_at: datetime


class InvitationAccepted(BaseModel):
    invitation_id: UUID
    organization_id: UUID
    role: Literal["consultant"]
    membership_status: Literal["active"]

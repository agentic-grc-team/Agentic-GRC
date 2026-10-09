from uuid import UUID

from pydantic import BaseModel, EmailStr


class AuthenticatedUser(BaseModel):
    id: UUID
    email: EmailStr
    is_platform_admin: bool


class CurrentUserResponse(AuthenticatedUser):
    pass

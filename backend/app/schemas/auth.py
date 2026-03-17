"""Auth-related Pydantic schemas."""

import uuid
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: str = Field(..., description="User email")
    password: str = Field(..., min_length=8, description="Password (min 8 chars)")
    name: str = Field(..., min_length=1, description="Full name")
    org_slug: str = Field(default="default", description="Organization slug")


class LoginRequest(BaseModel):
    email: str
    password: str
    org_slug: str = Field(default="default")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    role: str
    org_id: uuid.UUID
    org_name: str | None = None
    created_at: str

    model_config = {"from_attributes": True}

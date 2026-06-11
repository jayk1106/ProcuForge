from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    password: str = Field(min_length=1)


class OrgAddress(BaseModel):
    address: str = ""
    country: str
    state: str
    city: str
    pincode: str = ""


class AdminUserProfile(BaseModel):
    """Public-facing user profile. Safe to expose to the frontend."""

    user_id: str
    name: str
    email: str
    role: str
    active: bool = True


class AdminOrgProfile(BaseModel):
    """Public-facing organisation profile."""

    org_id: str
    name: str
    currency: str
    address: OrgAddress | None = None
    active: bool = True


class LoginResponse(BaseModel):
    user: AdminUserProfile
    org: AdminOrgProfile


class MeResponse(BaseModel):
    user: AdminUserProfile
    org: AdminOrgProfile


class WsTicketResponse(BaseModel):
    ticket: str
    expires_in: int


class AdminPrincipal(BaseModel):
    """Internal — derived from the JWT. Not exposed over HTTP."""

    user_id: str
    org_id: str
    issued_at: datetime
    expires_at: datetime

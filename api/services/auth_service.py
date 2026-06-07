from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Final

import bcrypt
import jwt

from api.config import APISettings
from api.schemas.auth import AdminOrgProfile, AdminPrincipal, AdminUserProfile, OrgAddress
from db.firestore.repositories.organisations import OrganisationRepository
from db.firestore.repositories.users import UserRepository

logger = logging.getLogger(__name__)

_TOKEN_TYPE_SESSION: Final[str] = "session"
_TOKEN_TYPE_WS_TICKET: Final[str] = "ws_ticket"


async def resolve_user_profile(
    settings: APISettings,
    user_repo: UserRepository,
) -> tuple[AdminUserProfile, str | None]:
    """Load the admin user profile.

    Firestore is the source of truth for display fields (name, email, role).
    Env defaults are used only as fallbacks for resilience (Firestore down,
    fresh install before seed data exists, etc.).

    Returns ``(profile, firestore_org_id)`` — the org id linked on the
    Firestore user doc, or ``None`` when the user wasn't found. The caller
    can use this to align the org lookup with the user's actual org.
    """
    user_id = settings.admin_user_id
    try:
        user = await user_repo.get(user_id)
    except Exception:
        logger.exception("auth.user_profile.lookup_failed user_id=%s", user_id)
        user = None

    if user is None:
        logger.warning(
            "auth.user_profile.fallback_to_env user_id=%s reason=not_in_firestore",
            user_id,
        )
        return (
            AdminUserProfile(
                user_id=user_id,
                name=settings.admin_user_name or user_id,
                email=settings.admin_user_email,
                role=settings.admin_user_role,
                active=True,
            ),
            None,
        )

    profile = AdminUserProfile(
        user_id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        active=user.active,
    )
    return profile, user.organization_id


async def resolve_org_profile(
    settings: APISettings,
    org_repo: OrganisationRepository,
    org_id_override: str | None = None,
) -> AdminOrgProfile:
    """Load the admin org profile.

    ``org_id_override`` (typically the user document's ``organizationId``)
    takes precedence so the profile reflects the user's real linkage rather
    than a stale env value.
    """
    org_id = org_id_override or settings.admin_org_id
    try:
        org = await org_repo.get(org_id)
    except Exception:
        logger.exception("auth.org_profile.lookup_failed org_id=%s", org_id)
        org = None

    if org is None:
        logger.warning(
            "auth.org_profile.fallback_to_env org_id=%s reason=not_in_firestore",
            org_id,
        )
        return AdminOrgProfile(
            org_id=org_id,
            name=settings.admin_org_name or org_id,
            currency=settings.admin_org_currency,
            address=None,
            active=True,
        )

    return AdminOrgProfile(
        org_id=org.id,
        name=org.name,
        currency=settings.admin_org_currency,
        address=OrgAddress(
            address=org.address.address,
            country=org.address.country,
            state=org.address.state,
            city=org.address.city,
            pincode=org.address.pincode,
        ),
        active=org.active,
    )


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        logger.warning("auth.password.invalid_hash_format")
        return False


def create_session_token(settings: APISettings) -> tuple[str, int, datetime, datetime]:
    return _create_token(
        settings=settings,
        token_type=_TOKEN_TYPE_SESSION,
        ttl_seconds=settings.jwt_expiration_seconds,
    )


def create_ws_ticket(settings: APISettings) -> tuple[str, int]:
    token, ttl, _, _ = _create_token(
        settings=settings,
        token_type=_TOKEN_TYPE_WS_TICKET,
        ttl_seconds=settings.jwt_ws_ticket_ttl_seconds,
    )
    return token, ttl


def decode_session_token(token: str, settings: APISettings) -> AdminPrincipal:
    return _decode(token, settings, expected_type=_TOKEN_TYPE_SESSION)


def decode_ws_ticket(token: str, settings: APISettings) -> AdminPrincipal:
    return _decode(token, settings, expected_type=_TOKEN_TYPE_WS_TICKET)


def _create_token(
    *,
    settings: APISettings,
    token_type: str,
    ttl_seconds: int,
) -> tuple[str, int, datetime, datetime]:
    issued = datetime.now(timezone.utc)
    expires = datetime.fromtimestamp(issued.timestamp() + ttl_seconds, tz=timezone.utc)
    payload = {
        "sub": settings.admin_user_id,
        "org": settings.admin_org_id,
        "typ": token_type,
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, ttl_seconds, issued, expires


def _decode(token: str, settings: APISettings, *, expected_type: str) -> AdminPrincipal:
    decoded = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["sub", "exp", "iat", "typ"]},
    )
    if decoded.get("typ") != expected_type:
        raise jwt.InvalidTokenError(
            f"unexpected token type: {decoded.get('typ')!r} (expected {expected_type!r})"
        )
    if decoded.get("sub") != settings.admin_user_id:
        raise jwt.InvalidTokenError("subject mismatch")
    return AdminPrincipal(
        user_id=decoded["sub"],
        org_id=decoded.get("org", settings.admin_org_id),
        issued_at=datetime.fromtimestamp(decoded["iat"], tz=timezone.utc),
        expires_at=datetime.fromtimestamp(decoded["exp"], tz=timezone.utc),
    )

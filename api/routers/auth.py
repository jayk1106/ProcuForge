from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Response, status

from api.dependencies import (
    CurrentAdminDep,
    OrganisationRepositoryDep,
    SettingsDep,
    UserRepositoryDep,
)
from api.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MeResponse,
    WsTicketResponse,
)
from api.services.auth_service import (
    create_session_token,
    create_ws_ticket,
    resolve_org_profile,
    resolve_user_profile,
    verify_password,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _is_dev(settings) -> bool:
    return settings.environment == "development"


def _set_session_cookie(
    response: Response,
    *,
    name: str,
    value: str,
    max_age: int,
    is_dev: bool,
) -> None:
    response.set_cookie(
        key=name,
        value=value,
        max_age=max_age,
        path="/",
        httponly=True,
        secure=True,
        samesite="none",
    )


def _clear_session_cookie(response: Response, *, name: str) -> None:
    response.delete_cookie(
        key=name,
        path="/",
        secure=True,
        samesite="none",
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate the admin user and set the session cookie",
    responses={401: {"description": "Invalid credentials."}},
)
async def login(
    payload: LoginRequest,
    response: Response,
    settings: SettingsDep,
    user_repo: UserRepositoryDep,
    org_repo: OrganisationRepositoryDep,
) -> LoginResponse:
    if not settings.admin_password_hash or not settings.jwt_secret:
        logger.error("auth.login.misconfigured reason=missing_hash_or_secret")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="auth_not_configured",
        )

    if not verify_password(payload.password, settings.admin_password_hash):
        logger.warning("auth.login.failure reason=bad_password user_id=%s", settings.admin_user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_credentials",
        )

    user_profile, firestore_org_id = await resolve_user_profile(settings, user_repo)
    org_profile = await resolve_org_profile(settings, org_repo, firestore_org_id)

    token, ttl, _, _ = create_session_token(settings)
    _set_session_cookie(
        response,
        name=settings.session_cookie_name,
        value=token,
        max_age=ttl,
        is_dev=_is_dev(settings),
    )
    logger.info(
        "auth.login.success user_id=%s org_id=%s",
        user_profile.user_id,
        org_profile.org_id,
    )
    return LoginResponse(user=user_profile, org=org_profile)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear the session cookie",
)
async def logout(response: Response, settings: SettingsDep) -> Response:
    _clear_session_cookie(response, name=settings.session_cookie_name)
    logger.info("auth.logout user_id=%s", settings.admin_user_id)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Return the current admin user and organisation profile",
)
async def me(
    current: CurrentAdminDep,
    settings: SettingsDep,
    user_repo: UserRepositoryDep,
    org_repo: OrganisationRepositoryDep,
) -> MeResponse:
    user_profile, firestore_org_id = await resolve_user_profile(settings, user_repo)
    org_profile = await resolve_org_profile(settings, org_repo, firestore_org_id)
    return MeResponse(user=user_profile, org=org_profile)


@router.post(
    "/ws-ticket",
    response_model=WsTicketResponse,
    summary="Issue a short-lived ticket for WebSocket handshake",
)
async def ws_ticket(
    current: CurrentAdminDep,
    settings: SettingsDep,
) -> WsTicketResponse:
    ticket, ttl = create_ws_ticket(settings)
    logger.debug("auth.ws_ticket.issued user_id=%s ttl=%d", current.user_id, ttl)
    return WsTicketResponse(ticket=ticket, expires_in=ttl)

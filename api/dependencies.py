from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from google.cloud import firestore

from api.config import APISettings, get_api_settings
from api.schemas.auth import AdminPrincipal
from api.services.auth_service import decode_session_token
from api.services.vendor_thread_query import VendorThreadQueryService
from api.services.workflow import WorkflowService
from api.services.workflow_chat import WorkflowChatService
from api.services.workflow_query import WorkflowQueryService
from db.firestore.client import get_firestore_client
from db.firestore.repositories.organisations import OrganisationRepository
from db.firestore.repositories.products import ProductRepository
from db.firestore.repositories.rfq_index import RfqIndexRepository
from db.firestore.repositories.users import UserRepository
from db.firestore.repositories.vendors import VendorRepository
from db.firestore.repositories.workflow_events import WorkflowEventsRepository
from db.firestore.repositories.workflow_index import WorkflowIndexRepository


def get_firestore_client_dep() -> firestore.Client:
    """FastAPI dependency wrapper around the process-wide Firestore client."""
    return get_firestore_client()


FirestoreClientDep = Annotated[firestore.Client, Depends(get_firestore_client_dep)]
SettingsDep = Annotated[APISettings, Depends(get_api_settings)]


def get_product_repository(client: FirestoreClientDep) -> ProductRepository:
    return ProductRepository(client)


def get_workflow_index_repository(client: FirestoreClientDep) -> WorkflowIndexRepository:
    return WorkflowIndexRepository(client)


def get_vendor_repository(client: FirestoreClientDep) -> VendorRepository:
    return VendorRepository(client)


def get_rfq_index_repository(client: FirestoreClientDep) -> RfqIndexRepository:
    return RfqIndexRepository(client)


def get_workflow_events_repository(client: FirestoreClientDep) -> WorkflowEventsRepository:
    return WorkflowEventsRepository(client)


def get_user_repository(client: FirestoreClientDep) -> UserRepository:
    return UserRepository(client)


def get_organisation_repository(client: FirestoreClientDep) -> OrganisationRepository:
    return OrganisationRepository(client)


ProductRepositoryDep = Annotated[ProductRepository, Depends(get_product_repository)]
WorkflowIndexRepositoryDep = Annotated[
    WorkflowIndexRepository, Depends(get_workflow_index_repository)
]
VendorRepositoryDep = Annotated[VendorRepository, Depends(get_vendor_repository)]
RfqIndexRepositoryDep = Annotated[RfqIndexRepository, Depends(get_rfq_index_repository)]
WorkflowEventsRepositoryDep = Annotated[
    WorkflowEventsRepository, Depends(get_workflow_events_repository)
]
UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]
OrganisationRepositoryDep = Annotated[
    OrganisationRepository, Depends(get_organisation_repository)
]


def get_workflow_service(
    product_repo: ProductRepositoryDep,
    settings: SettingsDep,
    index_repo: WorkflowIndexRepositoryDep,
) -> WorkflowService:
    return WorkflowService(
        product_repo=product_repo,
        settings=settings,
        index_repo=index_repo,
    )


def get_workflow_query_service(
    settings: SettingsDep,
    index_repo: WorkflowIndexRepositoryDep,
    vendor_repo: VendorRepositoryDep,
    events_repo: WorkflowEventsRepositoryDep,
) -> WorkflowQueryService:
    return WorkflowQueryService(
        settings=settings,
        index_repo=index_repo,
        vendor_repo=vendor_repo,
        events_repo=events_repo,
    )


def get_vendor_thread_query_service(
    settings: SettingsDep,
    index_repo: WorkflowIndexRepositoryDep,
    vendor_repo: VendorRepositoryDep,
    rfq_index_repo: RfqIndexRepositoryDep,
    events_repo: WorkflowEventsRepositoryDep,
    product_repo: ProductRepositoryDep,
) -> VendorThreadQueryService:
    return VendorThreadQueryService(
        settings=settings,
        index_repo=index_repo,
        vendor_repo=vendor_repo,
        rfq_index_repo=rfq_index_repo,
        events_repo=events_repo,
        product_repo=product_repo,
    )


def get_workflow_chat_service(settings: SettingsDep) -> WorkflowChatService:
    return WorkflowChatService(settings=settings)


WorkflowServiceDep = Annotated[WorkflowService, Depends(get_workflow_service)]
WorkflowQueryServiceDep = Annotated[WorkflowQueryService, Depends(get_workflow_query_service)]
WorkflowChatServiceDep = Annotated[WorkflowChatService, Depends(get_workflow_chat_service)]
VendorThreadQueryServiceDep = Annotated[
    VendorThreadQueryService, Depends(get_vendor_thread_query_service)
]


def get_current_admin(
    request: Request,
    settings: SettingsDep,
) -> AdminPrincipal:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not_authenticated",
        )
    try:
        return decode_session_token(token, settings)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_session",
        ) from exc


CurrentAdminDep = Annotated[AdminPrincipal, Depends(get_current_admin)]

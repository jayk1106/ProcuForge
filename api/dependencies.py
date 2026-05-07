from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from google.cloud import firestore

from api.config import APISettings, get_api_settings
from api.services.workflow import WorkflowService
from db.firestore.client import get_firestore_client
from db.firestore.repositories.products import ProductRepository


def get_firestore_client_dep() -> firestore.Client:
    """FastAPI dependency wrapper around the process-wide Firestore client."""
    return get_firestore_client()


FirestoreClientDep = Annotated[firestore.Client, Depends(get_firestore_client_dep)]
SettingsDep = Annotated[APISettings, Depends(get_api_settings)]


def get_product_repository(client: FirestoreClientDep) -> ProductRepository:
    return ProductRepository(client)


ProductRepositoryDep = Annotated[ProductRepository, Depends(get_product_repository)]


def get_workflow_service(
    product_repo: ProductRepositoryDep,
    settings: SettingsDep,
) -> WorkflowService:
    return WorkflowService(product_repo=product_repo, settings=settings)


WorkflowServiceDep = Annotated[WorkflowService, Depends(get_workflow_service)]

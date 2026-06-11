"""Process-wide context for WebSocket DTO factories.

The factories that produce ``state_changed`` payloads live at deep call
sites (subagent tools, event hooks) where threading the FastAPI dependency
graph is impractical. This registry stashes the settings and repositories
once at app startup so factories can construct DTOs with a single import.

Populated from :mod:`api.main` inside the ``lifespan`` startup hook.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from api.config import APISettings, get_api_settings
from api.services.session_reader import BuyerSessionReader, VendorSessionReader
from db.firestore.client import get_firestore_client
from db.firestore.repositories.products import ProductRepository
from db.firestore.repositories.rfq_index import RfqIndexRepository
from db.firestore.repositories.vendor_thread_state import VendorThreadStateRepository
from db.firestore.repositories.vendors import VendorRepository
from db.firestore.repositories.workflow_events import WorkflowEventsRepository
from db.firestore.repositories.workflow_state import WorkflowStateRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WsContext:
    settings: APISettings
    buyer_reader: BuyerSessionReader
    vendor_reader: VendorSessionReader
    vendor_repo: VendorRepository
    product_repo: ProductRepository
    events_repo: WorkflowEventsRepository
    rfq_index_repo: RfqIndexRepository
    workflow_state_repo: WorkflowStateRepository
    vendor_thread_state_repo: VendorThreadStateRepository


_ctx: WsContext | None = None


def init_ws_context() -> WsContext:
    """Build and cache the WS context. Idempotent."""
    global _ctx
    if _ctx is not None:
        return _ctx

    settings = get_api_settings()
    client = get_firestore_client()
    _ctx = WsContext(
        settings=settings,
        buyer_reader=BuyerSessionReader(settings),
        vendor_reader=VendorSessionReader(settings),
        vendor_repo=VendorRepository(client),
        product_repo=ProductRepository(client),
        events_repo=WorkflowEventsRepository(client),
        rfq_index_repo=RfqIndexRepository(client),
        workflow_state_repo=WorkflowStateRepository(client),
        vendor_thread_state_repo=VendorThreadStateRepository(client),
    )
    logger.info("ws.context.initialized")
    return _ctx


def get_ws_context() -> WsContext | None:
    """Return the cached context or ``None`` if startup hasn't run."""
    return _ctx

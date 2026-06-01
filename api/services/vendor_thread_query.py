"""List and detail queries for vendor negotiation threads."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status

from api.config import APISettings
from api.schemas.ui_dto import VendorConvoDTO, VendorThreadRowDTO
from api.schemas.vendor_thread_status import VendorThreadStatus
from api.services.session_reader import BuyerSessionReader, VendorSessionReader
from api.services.ui_mappers import vendor_convo_from_state, vendor_thread_rows_from_state
from api.ws import publish
from db.firestore.repositories.rfq_index import RfqIndexRepository
from db.firestore.repositories.vendors import VendorRepository
from db.firestore.repositories.workflow_events import WorkflowEventsRepository
from db.firestore.repositories.workflow_index import WorkflowIndexRepository
from procu_forge_buyer.state_keys import (
    NEGOTIATION_CONFIG_KEY,
    VENDOR_THREAD_OVERRIDES_KEY,
)

logger_name = __name__


class VendorThreadQueryService:
    def __init__(
        self,
        settings: APISettings,
        index_repo: WorkflowIndexRepository,
        vendor_repo: VendorRepository,
        rfq_index_repo: RfqIndexRepository,
        events_repo: WorkflowEventsRepository,
    ) -> None:
        self._settings = settings
        self._index_repo = index_repo
        self._vendor_repo = vendor_repo
        self._rfq_index_repo = rfq_index_repo
        self._events_repo = events_repo
        self._buyer_reader = BuyerSessionReader(settings)
        self._vendor_reader = VendorSessionReader(settings)

    def _ensure_configured(self) -> None:
        missing = []
        if not self._settings.vertex_project_id:
            missing.append("VERTEX_PROJECT_ID")
        if not self._settings.reasoning_engine_app_name:
            missing.append("BUYER_REASONING_ENGINE")
        if not self._settings.vendor_reasoning_engine_app_name:
            missing.append("VENDOR_REASONING_ENGINE")
        if missing:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Vendor thread runtime is not configured. Missing: {', '.join(missing)}",
            )

    async def list_threads(self, organization_id: str | None = None) -> list[VendorThreadRowDTO]:
        self._ensure_configured()
        org = organization_id or self._settings.workflow_default_organization_id
        if not org:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="organization_id is required.",
            )

        entries = await self._index_repo.list_by_org(org)
        all_rows: list[VendorThreadRowDTO] = []

        for entry in entries:
            session = await self._buyer_reader.get_session(entry.workflow_id)
            if session is None:
                continue
            state = session.state if isinstance(session.state, dict) else {}

            vendor_ids: list[str] = []
            neg = state.get(NEGOTIATION_CONFIG_KEY)
            if isinstance(neg, dict):
                for vid, cfg in neg.items():
                    if isinstance(cfg, dict):
                        vendor_ids.append(str(cfg.get("vendor_id") or vid))
            vendor_names = await self._vendor_repo.get_many(vendor_ids)
            all_rows.extend(
                vendor_thread_rows_from_state(
                    entry.workflow_id,
                    state,
                    vendor_names=vendor_names,
                )
            )

        return all_rows

    async def get_thread(self, rfq_id: str) -> VendorConvoDTO:
        self._ensure_configured()

        workflow_id, vendor_id = await self._resolve_rfq(rfq_id)
        if not vendor_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Vendor thread '{rfq_id}' not found.",
            )

        session = await self._vendor_reader.get_session(rfq_id, vendor_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Vendor session for rfq '{rfq_id}' not found.",
            )

        state = session.state if isinstance(session.state, dict) else {}
        vendor_doc = await self._vendor_repo.get(vendor_id)
        events = await self._events_repo.list_for_vendor_thread(workflow_id, rfq_id)
        return vendor_convo_from_state(
            rfq_id,
            state,
            workflow_id=workflow_id,
            vendor_doc=vendor_doc,
            events=events,
        )

    async def escalate(self, rfq_id: str, reason: str | None = None) -> dict:
        return await self._apply_override(
            rfq_id,
            status=VendorThreadStatus.ESCALATED,
            reason=reason,
            event_type="vendor_thread_escalated",
            api_author="api:escalate",
        )

    async def walk_away(self, rfq_id: str, reason: str | None = None) -> dict:
        return await self._apply_override(
            rfq_id,
            status=VendorThreadStatus.WALKED_AWAY,
            reason=reason,
            event_type="vendor_thread_walked_away",
            api_author="api:walk_away",
        )

    async def _apply_override(
        self,
        rfq_id: str,
        *,
        status: VendorThreadStatus,
        reason: str | None,
        event_type: str,
        api_author: str,
    ) -> dict:
        self._ensure_configured()

        workflow_id, vendor_id = await self._resolve_rfq(rfq_id)
        if not workflow_id or not vendor_id:
            raise HTTPException(
                status_code=404,
                detail=f"Vendor thread '{rfq_id}' not found.",
            )

        session = await self._buyer_reader.get_session(workflow_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail=f"Buyer session '{workflow_id}' not found.",
            )

        from google.adk.events.event import Event
        from google.adk.events.event_actions import EventActions
        from google.adk.sessions import VertexAiSessionService

        current_overrides = (
            session.state.get(VENDOR_THREAD_OVERRIDES_KEY)
            if isinstance(session.state, dict)
            else None
        )
        overrides = dict(current_overrides) if isinstance(current_overrides, dict) else {}
        applied_at = datetime.now(timezone.utc).isoformat()
        overrides[rfq_id] = {
            "status": status.value,
            "reason": reason or "",
            "ts": applied_at,
            "vendor_id": vendor_id,
        }

        session_service = VertexAiSessionService(
            project=self._settings.vertex_project_id,
            location=self._settings.vertex_location,
        )
        await session_service.append_event(
            session,
            Event(
                author=api_author,
                actions=EventActions(
                    state_delta={VENDOR_THREAD_OVERRIDES_KEY: overrides}
                ),
            ),
        )

        publish(
            workflow_id,
            event_type,
            {
                "rfq_id": rfq_id,
                "vendor_id": vendor_id,
                "status": status.value,
                "reason": reason or "",
            },
            vendor_thread_id=rfq_id,
            author=api_author,
        )

        return {
            "rfq_id": rfq_id,
            "workflow_id": workflow_id,
            "vendor_id": vendor_id,
            "status": status.value,
            "applied_at": applied_at,
        }

    async def _resolve_rfq(self, rfq_id: str) -> tuple[str, str]:
        """Find workflow_id and vendor_id for an rfq_id.

        Fast path: O(1) lookup against the rfq_index Firestore collection.
        Fallback: linear scan of buyer sessions for rows not yet indexed
        (backfill-in-progress); emits a warning log so misses are visible.
        """
        import logging

        logger = logging.getLogger(logger_name)

        entry = await self._rfq_index_repo.get(rfq_id)
        if entry is not None:
            return entry.workflow_id, entry.vendor_id

        logger.warning("rfq_index.miss rfq_id=%s falling_back_to_scan", rfq_id)

        org = self._settings.workflow_default_organization_id
        if not org:
            return "", ""

        entries = await self._index_repo.list_by_org(org)
        for wf_entry in entries:
            session = await self._buyer_reader.get_session(wf_entry.workflow_id)
            if session is None:
                continue
            state = session.state if isinstance(session.state, dict) else {}
            neg = state.get(NEGOTIATION_CONFIG_KEY)
            if not isinstance(neg, dict):
                continue
            for vid, cfg in neg.items():
                if not isinstance(cfg, dict):
                    continue
                if str(cfg.get("rfq_id") or "") == rfq_id:
                    vendor_id = str(cfg.get("vendor_id") or vid)
                    return wf_entry.workflow_id, vendor_id
        return "", ""

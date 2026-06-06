"""Vertex ADK session access for buyer and vendor reasoning engines."""

from __future__ import annotations

from typing import Any

from api.config import APISettings


class BuyerSessionReader:
    """Read buyer workflow sessions (session_id = workflow_id)."""

    def __init__(self, settings: APISettings) -> None:
        self._settings = settings
        self._session_service: Any | None = None

    def _service(self) -> Any:
        if self._session_service is None:
            from google.adk.sessions import VertexAiSessionService

            self._session_service = VertexAiSessionService(
                project=self._settings.vertex_project_id,
                location=self._settings.vertex_location,
            )
        return self._session_service

    async def get_session(self, workflow_id: str, user_id: str | None = None) -> Any | None:
        uid = user_id or self._settings.workflow_default_user_id
        return await self._service().get_session(
            app_name=self._settings.reasoning_engine_app_name,
            user_id=uid,
            session_id=workflow_id,
        )


class VendorSessionReader:
    """Read vendor thread sessions (session_id = rfq_id)."""

    def __init__(self, settings: APISettings) -> None:
        self._settings = settings
        self._session_service: Any | None = None

    def _service(self) -> Any:
        if self._session_service is None:
            from google.adk.sessions import VertexAiSessionService

            self._session_service = VertexAiSessionService(
                project=self._settings.vertex_project_id,
                location=self._settings.vertex_location,
            )
        return self._session_service

    @staticmethod
    def vendor_user_id(vendor_id: str) -> str:
        """Matches vendor_server.py rfq_request_converter user_id routing."""
        return vendor_id

    async def get_session(self, rfq_id: str, vendor_id: str) -> Any | None:
        return await self._service().get_session(
            app_name=self._settings.vendor_reasoning_engine_app_name,
            user_id=self.vendor_user_id(vendor_id),
            session_id=rfq_id,
        )

"""WebSocket endpoints for streaming workflow and vendor-thread events."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from api.config import get_api_settings
from api.services.auth_service import decode_ws_ticket
from api.ws import manager
from api.ws.manager import vendor_thread_channel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["ws"])


_PING_INTERVAL_SECONDS = 25.0
_PONG_GRACE_SECONDS = 60.0

# Application-defined close codes (RFC 6455 reserves 4000-4999 for app use).
_WS_CLOSE_UNAUTHORIZED = 4401


async def _authorize_ws(ws: WebSocket, ticket: str | None) -> bool:
    if not ticket:
        await ws.accept()
        await ws.close(code=_WS_CLOSE_UNAUTHORIZED, reason="missing_ticket")
        logger.warning("ws.auth.reject reason=missing_ticket")
        return False
    try:
        decode_ws_ticket(ticket, get_api_settings())
    except jwt.InvalidTokenError as exc:
        await ws.accept()
        await ws.close(code=_WS_CLOSE_UNAUTHORIZED, reason="invalid_ticket")
        logger.warning("ws.auth.reject reason=invalid_ticket detail=%s", exc)
        return False
    return True


async def _serve_channel(channel: str, ws: WebSocket) -> None:
    """Shared connect/receive/heartbeat loop for all channels.

    Sends an application-level ``{"type":"ping","ts":...}`` every 25s. The
    client is expected to reply with ``{"type":"pong"}``. If no pong arrives
    within ``_PONG_GRACE_SECONDS`` the socket is closed with code 1011 so the
    client triggers its reconnect flow (defeats LB idle-timeouts).
    """
    await manager.connect(channel, ws)
    last_pong = time.monotonic()
    heartbeat_task: asyncio.Task | None = None

    async def _heartbeat() -> None:
        try:
            while True:
                await asyncio.sleep(_PING_INTERVAL_SECONDS)
                try:
                    await ws.send_json(
                        {
                            "type": "ping",
                            "ts": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    logger.debug("ws.heartbeat.ping channel=%s", channel)
                except Exception:
                    return
                if time.monotonic() - last_pong > _PONG_GRACE_SECONDS:
                    logger.warning(
                        "ws.heartbeat.pong_overdue channel=%s grace_s=%.1f",
                        channel,
                        _PONG_GRACE_SECONDS,
                    )
                    try:
                        await ws.close(code=1011)
                    except Exception:
                        pass
                    return
        except asyncio.CancelledError:
            return

    try:
        heartbeat_task = asyncio.create_task(_heartbeat())
        while True:
            text = await ws.receive_text()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("type") == "pong":
                last_pong = time.monotonic()
                logger.debug("ws.heartbeat.pong channel=%s", channel)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ws.stream.error channel=%s", channel)
    finally:
        if heartbeat_task is not None:
            heartbeat_task.cancel()
        await manager.disconnect(channel, ws)


@router.websocket("/workflow/{workflow_id}")
async def workflow_stream(
    ws: WebSocket,
    workflow_id: str,
    ticket: str | None = Query(default=None),
) -> None:
    """Subscribe to live events for a single workflow."""
    if not await _authorize_ws(ws, ticket):
        return
    await _serve_channel(workflow_id, ws)


@router.websocket("/vendor-threads/{rfq_id}")
async def vendor_thread_stream(
    ws: WebSocket,
    rfq_id: str,
    ticket: str | None = Query(default=None),
) -> None:
    """Subscribe to live events scoped to a single vendor-thread (rfq_id)."""
    if not await _authorize_ws(ws, ticket):
        return
    await _serve_channel(vendor_thread_channel(rfq_id), ws)

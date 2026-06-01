"""WebSocket endpoints for streaming workflow and vendor-thread events."""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.ws import manager
from api.ws.manager import vendor_thread_channel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["ws"])


@router.websocket("/workflow/{workflow_id}")
async def workflow_stream(ws: WebSocket, workflow_id: str) -> None:
    """Subscribe to live events for a single workflow."""
    channel = workflow_id
    await manager.connect(channel, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ws.workflow_stream.error workflow_id=%s", workflow_id)
    finally:
        await manager.disconnect(channel, ws)


@router.websocket("/vendor-threads/{rfq_id}")
async def vendor_thread_stream(ws: WebSocket, rfq_id: str) -> None:
    """Subscribe to live events scoped to a single vendor-thread (rfq_id)."""
    channel = vendor_thread_channel(rfq_id)
    await manager.connect(channel, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ws.vendor_thread_stream.error rfq_id=%s", rfq_id)
    finally:
        await manager.disconnect(channel, ws)

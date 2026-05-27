"""WebSocket endpoints for streaming workflow events to clients."""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.ws import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["ws"])


@router.websocket("/workflow/{workflow_id}")
async def workflow_stream(ws: WebSocket, workflow_id: str) -> None:
    """Subscribe to live events for a single workflow.

    The connection is kept open; the inbound receive loop only exists to
    detect client disconnects. Messages from clients are ignored.
    """
    await manager.connect(workflow_id, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ws.workflow_stream.error workflow_id=%s", workflow_id)
    finally:
        await manager.disconnect(workflow_id, ws)

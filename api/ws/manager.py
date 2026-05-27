"""Per-workflow WebSocket connection manager.

Provides a process-wide singleton that:
- Tracks active WebSocket connections grouped by ``workflow_id``.
- Captures the FastAPI main asyncio loop at app startup so that publishes from
  any thread (e.g. ADK callbacks running inside ``BackgroundTasks``) can be
  bridged onto the loop via ``asyncio.run_coroutine_threadsafe``.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Final

from fastapi import WebSocket

from .schema import WorkflowEvent

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks WebSocket subscribers keyed by ``workflow_id`` and fans out events."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Capture the main event loop. Call once from the app lifespan."""
        self._loop = loop
        logger.info("ws.manager.loop_bound")

    @property
    def is_ready(self) -> bool:
        return self._loop is not None

    async def connect(self, workflow_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[workflow_id].add(ws)
        logger.info(
            "ws.connect workflow_id=%s subscribers=%s",
            workflow_id,
            len(self._connections[workflow_id]),
        )

    async def disconnect(self, workflow_id: str, ws: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(workflow_id)
            if sockets is not None:
                sockets.discard(ws)
                if not sockets:
                    self._connections.pop(workflow_id, None)
        logger.info("ws.disconnect workflow_id=%s", workflow_id)

    async def broadcast(self, event: WorkflowEvent) -> None:
        """Serialize once and fan out to all subscribers of ``event.workflow_id``.

        Dead sockets are removed silently.
        """
        async with self._lock:
            sockets = list(self._connections.get(event.workflow_id, ()))

        if not sockets:
            return

        payload = event.model_dump(mode="json")
        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                sockets_set = self._connections.get(event.workflow_id)
                if sockets_set is not None:
                    for ws in dead:
                        sockets_set.discard(ws)
                    if not sockets_set:
                        self._connections.pop(event.workflow_id, None)
            logger.debug(
                "ws.broadcast.pruned_dead workflow_id=%s count=%s",
                event.workflow_id,
                len(dead),
            )

    def schedule_broadcast(self, event: WorkflowEvent) -> None:
        """Thread-safe scheduling of a broadcast.

        Safe to call from any context:
        - On the main loop: schedules a task.
        - From a worker thread (e.g. BackgroundTasks): uses
          ``asyncio.run_coroutine_threadsafe`` to hop onto the bound loop.
        Silently no-ops if the loop has not been bound yet (app not started).
        """
        loop = self._loop
        if loop is None:
            return

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        try:
            if running is loop:
                loop.create_task(self.broadcast(event))
            else:
                asyncio.run_coroutine_threadsafe(self.broadcast(event), loop)
        except Exception:
            logger.exception(
                "ws.schedule_broadcast.failed workflow_id=%s event_type=%s",
                event.workflow_id,
                event.event_type,
            )


manager: Final[ConnectionManager] = ConnectionManager()

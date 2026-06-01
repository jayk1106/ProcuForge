"""Per-workflow WebSocket connection manager.

Provides a process-wide singleton that:
- Tracks active WebSocket connections grouped by a string channel key.
  Workflow subscribers use the bare ``workflow_id`` as the key; vendor-thread
  subscribers use ``vt:{rfq_id}`` (see :func:`vendor_thread_channel`).
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


VENDOR_THREAD_CHANNEL_PREFIX = "vt:"


def vendor_thread_channel(rfq_id: str) -> str:
    """Channel key used for vendor-thread WS subscribers."""
    return f"{VENDOR_THREAD_CHANNEL_PREFIX}{rfq_id}"


class ConnectionManager:
    """Tracks WebSocket subscribers by channel key and fans out events."""

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

    async def connect(self, channel: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[channel].add(ws)
        logger.info(
            "ws.connect channel=%s subscribers=%s",
            channel,
            len(self._connections[channel]),
        )

    async def disconnect(self, channel: str, ws: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(channel)
            if sockets is not None:
                sockets.discard(ws)
                if not sockets:
                    self._connections.pop(channel, None)
        logger.info("ws.disconnect channel=%s", channel)

    async def broadcast(self, event: WorkflowEvent) -> None:
        """Fan out an event to its workflow channel and (if set) vendor-thread channel."""
        channels: list[str] = [event.workflow_id]
        if event.vendor_thread_id:
            channels.append(vendor_thread_channel(event.vendor_thread_id))

        payload = event.model_dump(mode="json")
        for channel in channels:
            await self._send_to_channel(channel, payload)

    async def _send_to_channel(self, channel: str, payload: dict) -> None:
        async with self._lock:
            sockets = list(self._connections.get(channel, ()))

        if not sockets:
            return

        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                sockets_set = self._connections.get(channel)
                if sockets_set is not None:
                    for ws in dead:
                        sockets_set.discard(ws)
                    if not sockets_set:
                        self._connections.pop(channel, None)
            logger.debug(
                "ws.broadcast.pruned_dead channel=%s count=%s",
                channel,
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

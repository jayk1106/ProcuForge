"""Per-workflow WebSocket connection manager.

Provides a process-wide singleton that:
- Tracks active WebSocket connections grouped by a string channel key.
  Workflow subscribers use the bare ``workflow_id`` as the key; vendor-thread
  subscribers use ``vt:{rfq_id}`` (see :func:`vendor_thread_channel`).
- Captures the FastAPI main asyncio loop at app startup so that publishes from
  any thread (e.g. ADK callbacks running inside ``BackgroundTasks``) can be
  bridged onto the loop via ``asyncio.run_coroutine_threadsafe``.
- Coalesces and dedupes ``state_changed`` broadcasts per channel: a 100ms
  debounce window collapses bursts; payloads with an unchanged blake2b hash
  are dropped; a per-channel ``seq`` increments on every successful send.
- Caches the last sent payload per channel and replays it as an initial
  snapshot to newly-connected subscribers.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, Final

from fastapi import WebSocket
from pydantic import BaseModel

from .schema import WorkflowEvent

logger = logging.getLogger(__name__)


VENDOR_THREAD_CHANNEL_PREFIX = "vt:"

# Debounce window for state-changed broadcasts. ADK tool turns often emit
# multiple state-delta events within ~10-30ms; 100ms collapses the burst into
# a single DTO build while staying imperceptible to users.
_DEBOUNCE_SECONDS: Final[float] = 0.1


def vendor_thread_channel(rfq_id: str) -> str:
    """Channel key used for vendor-thread WS subscribers."""
    return f"{VENDOR_THREAD_CHANNEL_PREFIX}{rfq_id}"


StateFactory = Callable[[], Awaitable[BaseModel | dict[str, Any] | None]]


def _payload_hash(payload: dict[str, Any]) -> str:
    """Stable 16-byte blake2b hex of a JSON-serializable payload."""
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.blake2b(encoded, digest_size=16).hexdigest()


class ConnectionManager:
    """Tracks WebSocket subscribers by channel key and fans out events."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

        # Per-channel state-broadcast bookkeeping.
        self._last_seq: dict[str, int] = {}
        self._last_hash: dict[str, str] = {}
        self._last_payload: dict[str, dict[str, Any]] = {}
        self._pending_factory: dict[str, StateFactory] = {}
        self._pending_reason: dict[str, str] = {}
        self._pending_timer: dict[str, asyncio.TimerHandle] = {}
        self._build_lock: dict[str, asyncio.Lock] = {}

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Capture the main event loop. Call once from the app lifespan."""
        self._loop = loop
        logger.info("ws.manager.loop_bound")

    @property
    def is_ready(self) -> bool:
        return self._loop is not None

    # ── connection lifecycle ──────────────────────────────────────────────

    async def connect(self, channel: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[channel].add(ws)
            subscribers = len(self._connections[channel])
        logger.info("ws.connect channel=%s subscribers=%d", channel, subscribers)

        cached = self._last_payload.get(channel)
        if cached is not None:
            try:
                await ws.send_json(cached)
                logger.info(
                    "ws.initial_snapshot.sent channel=%s from_cache=true bytes=%d",
                    channel,
                    len(json.dumps(cached, default=str)),
                )
            except Exception:
                logger.exception(
                    "ws.initial_snapshot.send_failed channel=%s", channel
                )
        else:
            logger.info(
                "ws.initial_snapshot.sent channel=%s from_cache=false bytes=0",
                channel,
            )

    async def disconnect(self, channel: str, ws: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(channel)
            if sockets is not None:
                sockets.discard(ws)
                remaining = len(sockets)
                if not sockets:
                    self._connections.pop(channel, None)
            else:
                remaining = 0
        logger.info(
            "ws.disconnect channel=%s subscribers=%d", channel, remaining
        )
        if remaining == 0:
            # Last subscriber left: cancel any pending debounce timer so a
            # late factory call doesn't fire after everyone disconnected.
            timer = self._pending_timer.pop(channel, None)
            if timer is not None:
                timer.cancel()
            self._pending_factory.pop(channel, None)
            self._pending_reason.pop(channel, None)

    # ── granular event broadcast (legacy path, kept for compatibility) ────

    async def broadcast(self, event: WorkflowEvent) -> None:
        """Fan out a granular event envelope to its channels."""
        channels: list[str] = [event.workflow_id]
        if event.vendor_thread_id:
            channels.append(vendor_thread_channel(event.vendor_thread_id))

        payload = event.model_dump(mode="json")
        for channel in channels:
            await self._send_to_channel(channel, payload)

    async def _send_to_channel(self, channel: str, payload: dict) -> int:
        """Send ``payload`` to all subscribers of ``channel``. Returns count sent."""
        async with self._lock:
            sockets = list(self._connections.get(channel, ()))

        if not sockets:
            return 0

        dead: list[WebSocket] = []
        sent = 0
        for ws in sockets:
            try:
                await ws.send_json(payload)
                sent += 1
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
                "ws.broadcast.pruned_dead channel=%s count=%d",
                channel,
                len(dead),
            )
        return sent

    def schedule_broadcast(self, event: WorkflowEvent) -> None:
        """Thread-safe scheduling of a granular event broadcast.

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

    # ── state-changed broadcasts with debounce + dedupe ───────────────────

    def broadcast_state(
        self,
        channel: str,
        factory: StateFactory,
        *,
        reason: str,
        workflow_id: str | None = None,
        vendor_thread_id: str | None = None,
        immediate: bool = False,
    ) -> None:
        """Schedule a ``state_changed`` broadcast on the given channel.

        Safe from any thread. Coalesces concurrent calls within a 100ms
        debounce window per channel: only the latest factory wins. Drops the
        broadcast entirely if the channel has no subscribers (the factory is
        never invoked, so no DTO build cost is paid for unwatched channels).
        Drops the send if the produced payload hashes identical to the last
        sent payload on this channel.

        ``workflow_id`` / ``vendor_thread_id`` are echoed on the envelope so
        clients can identify which channel a frame belongs to.

        Pass ``immediate=True`` to bypass debounce and flush right away — the
        caller is asserting this update must reach subscribers as a distinct
        frame (e.g. an outbound A2A message sent before an awaited reply
        that would otherwise merge into the same debounce window).
        """
        loop = self._loop
        if loop is None:
            logger.debug(
                "ws.broadcast.skipped channel=%s reason=loop_unbound",
                channel,
            )
            return

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        coro = self._enqueue_state(
            channel,
            factory,
            reason=reason,
            workflow_id=workflow_id,
            vendor_thread_id=vendor_thread_id,
            immediate=immediate,
        )
        try:
            if running is loop:
                loop.create_task(coro)
            else:
                asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception:
            logger.exception(
                "ws.broadcast_state.schedule_failed channel=%s reason=%s",
                channel,
                reason,
            )

    async def _enqueue_state(
        self,
        channel: str,
        factory: StateFactory,
        *,
        reason: str,
        workflow_id: str | None,
        vendor_thread_id: str | None,
        immediate: bool = False,
    ) -> None:
        async with self._lock:
            has_subscribers = bool(self._connections.get(channel))

        if not has_subscribers:
            logger.debug(
                "ws.broadcast.skipped channel=%s reason=no_subscribers",
                channel,
            )
            return

        if immediate:
            # Cancel any in-flight debounce timer for this channel and flush
            # the new factory now. A pending merged factory (if any) is
            # superseded by the new one — callers asking for immediate are
            # asserting this snapshot is the one to send.
            timer = self._pending_timer.pop(channel, None)
            if timer is not None:
                timer.cancel()
            self._pending_factory[channel] = factory
            self._pending_reason[channel] = reason
            logger.debug(
                "ws.broadcast.scheduled channel=%s reason=%s state=immediate",
                channel,
                reason,
            )
            await self._do_build_and_send(
                channel,
                workflow_id=workflow_id,
                vendor_thread_id=vendor_thread_id,
            )
            return

        # Latest factory wins inside the debounce window.
        self._pending_factory[channel] = factory
        self._pending_reason[channel] = reason

        existing = self._pending_timer.get(channel)
        if existing is not None:
            logger.debug(
                "ws.broadcast.scheduled channel=%s reason=%s state=debounced_merged",
                channel,
                reason,
            )
            return

        logger.debug(
            "ws.broadcast.scheduled channel=%s reason=%s state=new", channel, reason
        )

        loop = asyncio.get_running_loop()
        timer = loop.call_later(
            _DEBOUNCE_SECONDS,
            lambda: loop.create_task(
                self._do_build_and_send(
                    channel,
                    workflow_id=workflow_id,
                    vendor_thread_id=vendor_thread_id,
                )
            ),
        )
        self._pending_timer[channel] = timer

    async def _do_build_and_send(
        self,
        channel: str,
        *,
        workflow_id: str | None,
        vendor_thread_id: str | None,
    ) -> None:
        # Pop the pending state under a per-channel lock so concurrent
        # debounce fires don't double-build.
        build_lock = self._build_lock.setdefault(channel, asyncio.Lock())
        async with build_lock:
            self._pending_timer.pop(channel, None)
            factory = self._pending_factory.pop(channel, None)
            reason = self._pending_reason.pop(channel, "unknown")
            if factory is None:
                return

            async with self._lock:
                has_subscribers = bool(self._connections.get(channel))
            if not has_subscribers:
                logger.debug(
                    "ws.broadcast.skipped channel=%s reason=no_subscribers_at_fire",
                    channel,
                )
                return

            t0 = time.perf_counter()
            try:
                dto = await factory()
            except Exception as exc:
                logger.exception(
                    "ws.broadcast.dto_build_failed channel=%s reason=%s error=%s",
                    channel,
                    reason,
                    exc,
                )
                return

            if dto is None:
                logger.info(
                    "ws.broadcast.skipped channel=%s reason=factory_none",
                    channel,
                )
                return

            if isinstance(dto, BaseModel):
                data_payload = dto.model_dump(mode="json", by_alias=True)
            elif isinstance(dto, dict):
                data_payload = dto
            else:
                logger.warning(
                    "ws.broadcast.skipped channel=%s reason=factory_bad_type type=%s",
                    channel,
                    type(dto).__name__,
                )
                return

            new_hash = _payload_hash(data_payload)
            if new_hash == self._last_hash.get(channel):
                logger.info(
                    "ws.broadcast.skipped channel=%s reason=same_hash",
                    channel,
                )
                return

            seq = self._last_seq.get(channel, 0) + 1
            envelope = WorkflowEvent(
                workflow_id=workflow_id or "",
                event_type="state_changed",
                vendor_thread_id=vendor_thread_id,
                author=None,
                data=data_payload,
                seq=seq,
            )
            envelope_payload = envelope.model_dump(mode="json")

            sent = await self._send_to_channel(channel, envelope_payload)

            self._last_seq[channel] = seq
            self._last_hash[channel] = new_hash
            self._last_payload[channel] = envelope_payload

            build_ms = int((time.perf_counter() - t0) * 1000)
            payload_bytes = len(json.dumps(envelope_payload, default=str))
            logger.info(
                "ws.broadcast.sent channel=%s seq=%d subscribers=%d bytes=%d build_ms=%d reason=%s",
                channel,
                seq,
                sent,
                payload_bytes,
                build_ms,
                reason,
            )


manager: Final[ConnectionManager] = ConnectionManager()

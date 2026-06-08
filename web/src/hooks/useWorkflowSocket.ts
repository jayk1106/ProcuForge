'use client'

import { useEffect, useRef } from 'react'
import { buildWsUrl } from '@/lib/wsUrl'
import { wsLog } from '@/lib/log'
import { getWsTicket, UnauthorizedError } from '@/lib/api-client'

const RECONNECT_DELAYS_MS = [1_000, 2_000, 4_000, 8_000, 15_000, 30_000]

// Mirrors api/routers/ws.py: close codes used to signal auth failure.
const WS_CLOSE_UNAUTHORIZED = 4401
const WS_CLOSE_FORBIDDEN = 4403

interface ServerEnvelope<T> {
  event_type: string
  workflow_id?: string
  vendor_thread_id?: string
  data?: T
  seq?: number
  timestamp?: string
}

export interface UseWorkflowSocketOpts<T> {
  /**
   * Invoked when a fresh ``state_changed`` frame is accepted. The hook owns
   * dedupe-by-seq; callers can simply replace local state.
   */
  onState: (next: T, seq: number) => void
  /**
   * Short label used in debug logs (e.g. 'flow' or 'vendor').
   */
  debugLabel: string
}

/**
 * Maintains a single WebSocket connection to the given path and surfaces
 * ``state_changed`` payloads via ``onState``.
 *
 * Features:
 * - Exponential reconnect (1s → 30s cap) on disconnect or error.
 * - Per-channel seq-based dedupe (drops stale frames).
 * - Heartbeat: replies to server ``ping`` frames with ``pong``.
 * - Debug logging via ``wsLog`` (gated on ``NEXT_PUBLIC_WS_DEBUG=1``).
 *
 * The first frame after a reconnect is always accepted, even if its ``seq``
 * is lower than the previous high-water mark (server seq resets on restart).
 */
export function useWorkflowSocket<T>(
  path: string,
  opts: UseWorkflowSocketOpts<T>,
): void {
  const { onState, debugLabel } = opts
  const onStateRef = useRef(onState)
  onStateRef.current = onState

  useEffect(() => {
    let cancelled = false
    let ws: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let openDeferTimer: ReturnType<typeof setTimeout> | null = null
    let reconnectAttempt = 0
    let lastSeq = 0
    let justReconnected = true

    const connect = () => {
      // Defer the actual `new WebSocket(...)` past React 18 Strict Mode's
      // synchronous mount → cleanup → mount cycle. The first cleanup clears
      // this timeout before the socket ever opens, so no "closed before
      // established" warnings are emitted on remount.
      openDeferTimer = setTimeout(() => {
        openDeferTimer = null
        if (cancelled) return
        void openSocket()
      }, 0)
    }

    const openSocket = async () => {
      let ticket: string
      try {
        const res = await getWsTicket()
        ticket = res.ticket
      } catch (err) {
        if (err instanceof UnauthorizedError) {
          // api-client already kicked us to /login; stop reconnect loop.
          return
        }
        wsLog(debugLabel, 'ticket-fetch-failed', err)
        scheduleReconnect()
        return
      }
      if (cancelled) return
      const base = buildWsUrl(path)
      const sep = base.includes('?') ? '&' : '?'
      const url = `${base}${sep}ticket=${encodeURIComponent(ticket)}`
      wsLog(debugLabel, `connecting attempt=${reconnectAttempt}`, { url: base })
      try {
        ws = new WebSocket(url)
      } catch (err) {
        wsLog(debugLabel, 'construct-failed', err)
        scheduleReconnect()
        return
      }
      bindHandlers(ws)
    }

    const bindHandlers = (sock: WebSocket) => {
      sock.onopen = () => {
        wsLog(debugLabel, 'open', { path })
        justReconnected = true
      }

      sock.onmessage = (ev) => {
        let parsed: ServerEnvelope<T> | { type?: string } | null = null
        try {
          parsed = JSON.parse(ev.data) as ServerEnvelope<T> | { type?: string }
        } catch {
          wsLog(debugLabel, 'parse-failed', { bytes: (ev.data as string)?.length })
          return
        }
        if (!parsed) return

        if ((parsed as { type?: string }).type === 'ping') {
          try {
            sock.send(JSON.stringify({ type: 'pong' }))
            wsLog(debugLabel, 'pong-sent')
          } catch (err) {
            wsLog(debugLabel, 'pong-send-failed', err)
          }
          return
        }

        const env = parsed as ServerEnvelope<T>
        if (env.event_type !== 'state_changed') {
          wsLog(debugLabel, 'dedupe-drop reason=unknown_event_type', {
            type: env.event_type,
          })
          return
        }

        const seq = typeof env.seq === 'number' ? env.seq : 0
        if (!justReconnected && seq <= lastSeq) {
          wsLog(debugLabel, 'dedupe-drop reason=stale_seq', {
            seq,
            lastSeq,
          })
          return
        }

        lastSeq = seq
        justReconnected = false
        reconnectAttempt = 0

        if (env.data !== undefined) {
          wsLog(debugLabel, 'state-applied', { seq, bytes: ev.data.length })
          try {
            onStateRef.current(env.data, seq)
          } catch (err) {
            wsLog(debugLabel, 'onstate-threw', err)
          }
        }
      }

      sock.onerror = (ev) => {
        wsLog(debugLabel, 'error', { readyState: sock.readyState, ev })
      }

      sock.onclose = (ev) => {
        wsLog(debugLabel, 'close', {
          code: ev.code,
          reason: ev.reason,
          wasClean: ev.wasClean,
        })
        ws = null
        if (cancelled) return
        if (ev.code === WS_CLOSE_UNAUTHORIZED || ev.code === WS_CLOSE_FORBIDDEN) {
          if (typeof window !== 'undefined') {
            const next = encodeURIComponent(
              window.location.pathname + window.location.search,
            )
            window.location.href = `/login?next=${next}`
          }
          return
        }
        scheduleReconnect()
      }
    }

    const scheduleReconnect = () => {
      if (cancelled) return
      const delay =
        RECONNECT_DELAYS_MS[
        Math.min(reconnectAttempt, RECONNECT_DELAYS_MS.length - 1)
        ]
      reconnectAttempt += 1
      wsLog(debugLabel, 'reconnect', { attempt: reconnectAttempt, delayMs: delay })
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null
        if (!cancelled) connect()
      }, delay)
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimer !== null) clearTimeout(reconnectTimer)
      if (openDeferTimer !== null) clearTimeout(openDeferTimer)
      if (ws) {
        try {
          ws.close()
        } catch {
          // ignore
        }
        ws = null
      }
    }
  }, [path, debugLabel])
}

'use client'
import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'
import {
  escalateVendorThread,
  getVendorThread,
  getVendorThreadState,
  walkAwayVendorThread,
} from '@/lib/api-client'
import type { VendorConvo } from '@/types'
import { AsciiRule } from '@/components/primitives/AsciiRule'
import { StateDebugPanel } from '@/components/primitives/StateDebugPanel'
import { Bracketed } from '@/components/primitives/Bracketed'
import { FilterChip } from '@/components/primitives/FilterChip'
import { StatusPill } from '@/components/primitives/StatusPill'

interface VendorDetailClientProps {
  rfqId: string
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

function buildWsUrl(path: string): string {
  const wsBase = API_URL.replace(/^http/, 'ws')
  return `${wsBase}${path}`
}

const TERMINAL_OUTCOMES = new Set([
  'WALKED_AWAY',
  'AWARDED',
  'REJECTED',
  'EXPIRED',
])

export function VendorDetailClient({ rfqId }: VendorDetailClientProps) {
  const router = useRouter()
  const [convo, setConvo] = useState<VendorConvo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showRaw, setShowRaw] = useState<Record<number, boolean>>({})
  const [acting, setActing] = useState<null | 'escalate' | 'walk-away'>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setConvo(await getVendorThread(rfqId))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load vendor thread')
    } finally {
      setLoading(false)
    }
  }, [rfqId])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    let cancelled = false
    let ws: WebSocket | null = null
    try {
      ws = new WebSocket(buildWsUrl(`/ws/vendor-threads/${rfqId}`))
      wsRef.current = ws
      ws.onmessage = () => {
        if (!cancelled) load()
      }
      ws.onerror = () => {
        // Swallow; the read path still works via refresh button.
      }
    } catch {
      // ignore
    }
    return () => {
      cancelled = true
      if (ws) {
        try {
          ws.close()
        } catch {
          // ignore
        }
      }
      wsRef.current = null
    }
  }, [rfqId, load])

  function toggle(i: number) {
    setShowRaw((s) => ({ ...s, [i]: !s[i] }))
  }

  async function onEscalate() {
    setActing('escalate')
    setActionError(null)
    try {
      await escalateVendorThread(rfqId)
      await load()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Escalate failed')
    } finally {
      setActing(null)
    }
  }

  async function onWalkAway() {
    if (!confirm('Walk away from this vendor thread? This cannot be undone.')) return
    setActing('walk-away')
    setActionError(null)
    try {
      await walkAwayVendorThread(rfqId)
      await load()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Walk-away failed')
    } finally {
      setActing(null)
    }
  }

  if (loading) {
    return (
      <div className="viewport">
        <div className="thinking" style={{ marginTop: 40 }}>
          loading vendor thread…
        </div>
      </div>
    )
  }

  if (error || !convo) {
    return (
      <div className="viewport">
        <div className="empty" style={{ marginTop: 40 }}>
          <pre className="ascii-mark">──── error ────</pre>
          <div>{error ?? 'Thread not found'}</div>
          <button className="btn" style={{ marginTop: 12 }} onClick={() => router.push('/vendors')}>
            [ back to vendors ]
          </button>
        </div>
      </div>
    )
  }

  const workflowLink = convo.workflowId || convo.pr
  const isTerminal = TERMINAL_OUTCOMES.has(convo.outcome)

  return (
    <div className="viewport">
      <div className="crumbs">
        <a onClick={() => router.push('/vendors')} style={{ cursor: 'pointer' }}>
          Vendors
        </a>
        <span className="sep">/</span>
        <span className="here">{convo.vendor.id}</span>
        <span className="sep">·</span>
        <a
          onClick={() => router.push(`/flows/${workflowLink}`)}
          style={{ cursor: 'pointer' }}
        >
          {convo.pr}
        </a>
      </div>

      <header className="page-head">
        <div className="row between" style={{ alignItems: 'flex-start' }}>
          <div>
            <div className="t-xs upper muted">Vendor conversation</div>
            <h1 className="page-title">
              <span className="tnum">{convo.vendor.id}</span>
              <span className="muted" style={{ fontWeight: 400 }}>
                {' '}
                ·{' '}
              </span>
              {convo.vendor.name}
            </h1>
            <div className="page-sub">
              {convo.vendor.country} · {convo.vendor.tier} · MSSA {convo.vendor.mssa} · for{' '}
              <a
                className="ink"
                onClick={() => router.push(`/flows/${workflowLink}`)}
                style={{
                  textDecoration: 'underline',
                  textDecorationColor: 'var(--rule-strong)',
                  cursor: 'pointer',
                }}
              >
                {convo.pr}
              </a>{' '}
              · outcome <span className="accent">{convo.outcome}</span>
            </div>
          </div>
          <div className="row" style={{ gap: 6 }}>
            <button
              className="btn"
              disabled={isTerminal || acting !== null}
              onClick={onEscalate}
            >
              [ {acting === 'escalate' ? 'escalating…' : 'escalate'} ]
            </button>
            <button
              className="btn"
              disabled={isTerminal || acting !== null}
              onClick={onWalkAway}
            >
              [ {acting === 'walk-away' ? 'walking…' : 'walk away'} ]
            </button>
            <button className="btn" onClick={load}>
              [ refresh ]
            </button>
          </div>
        </div>
        {actionError && (
          <div className="t-xs" style={{ marginTop: 8, color: 'var(--err, #c00)' }}>
            {actionError}
          </div>
        )}
      </header>

      <AsciiRule />

      <div className="row" style={{ gap: 14, padding: '14px 0', flexWrap: 'wrap' }}>
        <span className="t-xs upper muted">filter</span>
        <FilterChip active>ALL EVENTS</FilterChip>
        <div className="spacer" />
        {convo.rfqId && (
          <span className="t-xs muted">
            rfq <span className="tnum ink">{convo.rfqId.slice(0, 8)}…</span>
          </span>
        )}
      </div>

      <div className="col" style={{ gap: 0 }}>
        {convo.messages.length === 0 ? (
          <div className="empty" style={{ marginTop: 24 }}>
            <div>No messages in this thread yet.</div>
          </div>
        ) : (
          convo.messages.map((m, i) => (
            <div
              key={i}
              className="msg-row"
              style={{
                borderBottom: '1px solid var(--rule)',
                padding: '14px 0',
              }}
            >
              <div className="row between" style={{ marginBottom: 6 }}>
                <div className="row" style={{ gap: 8 }}>
                  <StatusPill kind={m.error ? 'err' : m.locked ? 'idle' : 'ok'}>
                    {m.type}
                  </StatusPill>
                  <span className="t-xs muted tnum">{m.ts}</span>
                </div>
                <button className="btn tiny" onClick={() => toggle(i)}>
                  [ {showRaw[i] ? 'hide' : 'raw'} json ]
                </button>
              </div>
              <div className="t-sm">
                <span className="muted">{m.from}</span>
                <span className="muted"> → </span>
                <span className="muted">{m.to}</span>
                <span className="muted"> · </span>
                <span>{m.phase}</span>
              </div>
              {showRaw[i] && (
                <pre className="t-xs" style={{ marginTop: 8, overflow: 'auto' }}>
                  {JSON.stringify(m.payload, null, 2)}
                </pre>
              )}
            </div>
          ))
        )}
      </div>

      <StateDebugPanel
        label="vendor session state"
        fetchState={async () => {
          const result = await getVendorThreadState(rfqId)
          return (result as Record<string, unknown>).vendor_session_state ?? result
        }}
      />

      <div style={{ height: 80 }} />
    </div>
  )
}

'use client'
import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'
import {
  escalateVendorThread,
  getVendorThread,
  getVendorThreadState,
  walkAwayVendorThread,
} from '@/lib/api-client'
import type { VendorConvo, VendorThreadSummary } from '@/types'
import { AsciiRule } from '@/components/primitives/AsciiRule'
import { StateDebugPanel } from '@/components/primitives/StateDebugPanel'
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

const NEGOTIATION_TYPES = new Set(['RFQ', 'QUOTE', 'COUNTER_OFFER', 'ACCEPT', 'WALKAWAY'])
const FULFILLMENT_TYPES = new Set([
  'PO',
  'PO_ACKNOWLEDGED',
  'GRN_CREATED',
  'INVOICE_SUBMITTED',
  'PROCESS_COMPLETE',
  'RFQ_CLOSED',
])

function fmtMoney(value: number | null | undefined, currency = 'USD'): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const symbol = currency === 'USD' ? '$' : `${currency} `
  return `${symbol}${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function pillKindForType(type: string, error?: boolean): 'ok' | 'warn' | 'err' | 'idle' {
  if (error || type === 'WALKAWAY') return 'err'
  if (type === 'COUNTER_OFFER') return 'warn'
  if (NEGOTIATION_TYPES.has(type) || FULFILLMENT_TYPES.has(type)) return 'ok'
  return 'idle'
}

function pillKindForStatus(status: string): 'ok' | 'warn' | 'err' | 'idle' {
  const s = status.toUpperCase()
  if (s === 'COMPLETE') return 'ok'
  if (s.includes('WALKED') || s.includes('REJECTED') || s.includes('ESCALATED')) return 'err'
  if (s.includes('PROGRESS') || s.includes('NEGOTIATION') || s.includes('PO_') || s.includes('GRN') || s.includes('INVOICE')) return 'warn'
  return 'idle'
}

interface SummaryCardProps {
  summary: VendorThreadSummary
}

function SummaryCard({ summary }: SummaryCardProps) {
  const c = summary.currency || 'USD'
  return (
    <div
      className="col"
      style={{
        gap: 12,
        padding: '14px 16px',
        border: '1px solid var(--rule)',
        borderRadius: 4,
        marginTop: 8,
        background: 'var(--bg-soft, transparent)',
      }}
    >
      <div className="row" style={{ gap: 10, alignItems: 'center' }}>
        <span className="t-xs upper muted">summary</span>
        {summary.status ? (
          <StatusPill kind={pillKindForStatus(summary.status)}>{summary.status}</StatusPill>
        ) : null}
      </div>

      <div className="row" style={{ gap: 24, flexWrap: 'wrap' }}>
        <SummaryStat label="Quoted" value={fmtMoney(summary.quotedPrice, c)} />
        <SummaryStat
          label="Accepted"
          value={fmtMoney(summary.acceptedPrice, c)}
          emphasis
        />
      </div>

      <div className="row" style={{ gap: 24, flexWrap: 'wrap' }}>
        <SummaryStat label="PO" value={summary.poNumber || '—'} mono />
        <SummaryStat label="GRN" value={summary.grnNumber || '—'} mono />
        <SummaryStat label="Invoice" value={summary.invoiceNumber || '—'} mono />
        <SummaryStat label="Expected delivery" value={summary.expectedDelivery || '—'} mono />
        {summary.deliveredOn && (
          <SummaryStat label="Delivered" value={summary.deliveredOn} mono />
        )}
      </div>
    </div>
  )
}

// ── per-message structured details ────────────────────────────────────────────

interface DetailField {
  label: string
  value: React.ReactNode
  mono?: boolean
}

function pickStr(payload: Record<string, unknown>, key: string): string | null {
  const v = payload[key]
  return typeof v === 'string' && v ? v : typeof v === 'number' ? String(v) : null
}

function pickNum(payload: Record<string, unknown>, key: string): number | null {
  const v = payload[key]
  if (typeof v === 'number' && !Number.isNaN(v)) return v
  if (typeof v === 'string') {
    const n = Number(v)
    return Number.isFinite(n) ? n : null
  }
  return null
}

function fieldsForType(
  type: string,
  payload: Record<string, unknown>,
  currency: string,
): DetailField[] {
  const c = currency || 'USD'
  const item = (payload.item && typeof payload.item === 'object' ? payload.item : {}) as Record<
    string,
    unknown
  >
  const fields: DetailField[] = []

  const push = (label: string, value: React.ReactNode, mono?: boolean) => {
    if (value === null || value === undefined || value === '') return
    fields.push({ label, value, mono })
  }

  switch (type) {
    case 'RFQ':
      push('Product', pickStr(item, 'product_id'), true)
      push('SKU', pickStr(item, 'sku'), true)
      push('Quantity', pickStr(item, 'quantity'))
      push('Unit', pickStr(item, 'unit'))
      push('Required by', pickStr(payload, 'required_by'))
      push('Response deadline', pickStr(payload, 'response_deadline'))
      break
    case 'QUOTE':
    case 'ACCEPT':
    case 'COUNTER_OFFER':
      push('Product', pickStr(item, 'product_id'), true)
      push('SKU', pickStr(item, 'sku'), true)
      push('Quantity', pickStr(item, 'quantity'))
      push('Unit price', fmtMoney(pickNum(payload, 'unit_price'), c))
      push('Total price', fmtMoney(pickNum(payload, 'total_price'), c))
      if (type === 'COUNTER_OFFER') {
        push('Final', payload.is_final ? 'yes' : 'no')
      }
      push('Required by', pickStr(payload, 'required_by'))
      push('Response deadline', pickStr(payload, 'response_deadline'))
      break
    case 'WALKAWAY':
      push('Reason', pickStr(payload, 'reason'))
      push('Last unit price', fmtMoney(pickNum(payload, 'last_unit_price'), c))
      push('Last total', fmtMoney(pickNum(payload, 'last_total_price'), c))
      break
    case 'RFQ_CLOSED':
      push('Outcome', pickStr(payload, 'outcome'))
      push('Reason', pickStr(payload, 'reason'))
      break
    case 'PO':
      push('PO number', pickStr(payload, 'po_number'), true)
      push('RFQ ref', pickStr(payload, 'rfq_reference'), true)
      push('Total amount', fmtMoney(pickNum(payload, 'total_amount'), c))
      push('Currency', pickStr(payload, 'currency'))
      push('Delivery date', pickStr(payload, 'delivery_date'))
      break
    case 'PO_ACKNOWLEDGED':
      push('PO number', pickStr(payload, 'po_number'), true)
      break
    case 'GRN_CREATED':
      push('GRN number', pickStr(payload, 'grn_number'), true)
      push('PO number', pickStr(payload, 'po_number'), true)
      push('Received at', pickStr(payload, 'received_at'))
      break
    case 'INVOICE_SUBMITTED':
      push('Invoice', pickStr(payload, 'invoice_number'), true)
      push('PO number', pickStr(payload, 'po_number'), true)
      push('GRN ref', pickStr(payload, 'grn_reference'), true)
      push('Invoice date', pickStr(payload, 'invoice_date'))
      push('Due date', pickStr(payload, 'due_date'))
      push('Total amount', fmtMoney(pickNum(payload, 'total_amount'), c))
      push('Currency', pickStr(payload, 'currency'))
      break
    case 'PROCESS_COMPLETE':
      push('PO number', pickStr(payload, 'po_number'), true)
      push('GRN number', pickStr(payload, 'grn_number'), true)
      push('Invoice', pickStr(payload, 'invoice_number'), true)
      break
    default:
      for (const [k, v] of Object.entries(payload)) {
        if (v === null || v === undefined) continue
        if (typeof v === 'object') continue
        push(k, String(v))
      }
  }

  return fields
}

function lineItemsFromPayload(payload: Record<string, unknown>): Record<string, unknown>[] {
  const raw = payload.line_items
  if (!Array.isArray(raw)) return []
  return raw.filter((x): x is Record<string, unknown> => !!x && typeof x === 'object') as Record<
    string,
    unknown
  >[]
}

function MessageDetails({
  type,
  payload,
  currency,
}: {
  type: string
  payload: Record<string, unknown>
  currency: string
}) {
  const fields = fieldsForType(type, payload, currency)
  const lineItems = lineItemsFromPayload(payload)
  const moneyKeys = new Set(['unit_price', 'total_price'])
  const lineItemKeys = lineItems[0] ? Object.keys(lineItems[0]) : []

  return (
    <div
      className="col"
      style={{
        gap: 12,
        marginTop: 10,
        padding: 12,
        border: '1px solid var(--rule)',
        borderRadius: 4,
      }}
    >
      {fields.length > 0 && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
            gap: 10,
          }}
        >
          {fields.map((f) => (
            <div key={f.label} className="col" style={{ gap: 2 }}>
              <span className="t-xs upper muted">{f.label}</span>
              <span className={f.mono ? 'tnum' : undefined}>{f.value}</span>
            </div>
          ))}
        </div>
      )}
      {lineItems.length > 0 && (
        <div className="col" style={{ gap: 6 }}>
          <span className="t-xs upper muted">Line items</span>
          <div style={{ overflowX: 'auto' }}>
            <table
              className="t-sm"
              style={{ width: '100%', borderCollapse: 'collapse' }}
            >
              <thead>
                <tr>
                  {lineItemKeys.map((k) => (
                    <th
                      key={k}
                      className="t-xs upper muted"
                      style={{
                        textAlign: 'left',
                        padding: '6px 8px',
                        borderBottom: '1px solid var(--rule)',
                      }}
                    >
                      {k.replace(/_/g, ' ')}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {lineItems.map((li, idx) => (
                  <tr key={idx}>
                    {lineItemKeys.map((k) => {
                      const v = li[k]
                      const isMoney = moneyKeys.has(k) && typeof v === 'number'
                      return (
                        <td
                          key={k}
                          className="tnum"
                          style={{
                            padding: '6px 8px',
                            borderBottom: '1px solid var(--rule)',
                          }}
                        >
                          {v === null || v === undefined
                            ? '—'
                            : isMoney
                            ? fmtMoney(v as number, currency)
                            : typeof v === 'object'
                            ? JSON.stringify(v)
                            : String(v)}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {fields.length === 0 && lineItems.length === 0 && (
        <span className="t-xs muted">No payload fields.</span>
      )}
    </div>
  )
}

function SummaryStat({
  label,
  value,
  emphasis,
  mono,
}: {
  label: string
  value: string
  emphasis?: boolean
  mono?: boolean
}) {
  return (
    <div className="col" style={{ gap: 2, minWidth: 120 }}>
      <span className="t-xs upper muted">{label}</span>
      <span
        className={mono ? 'tnum' : undefined}
        style={{
          fontWeight: emphasis ? 600 : 400,
          color: emphasis ? 'var(--accent, var(--ink))' : 'var(--ink)',
        }}
      >
        {value}
      </span>
    </div>
  )
}

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
            <h1 className="page-title">{convo.vendor.name}</h1>
            <div className="page-sub">
              {convo.vendor.country} · {convo.vendor.tier} · MSSA {convo.vendor.mssa}
              {convo.product?.name && (
                <>
                  {' · for '}
                  <a
                    className="ink"
                    onClick={() => router.push(`/flows/${workflowLink}`)}
                    style={{
                      textDecoration: 'underline',
                      textDecorationColor: 'var(--rule-strong)',
                      cursor: 'pointer',
                    }}
                  >
                    {convo.product.name}
                  </a>
                  {convo.product.brand ? (
                    <span className="muted"> · {convo.product.brand}</span>
                  ) : null}
                  {convo.product.sku && convo.product.sku !== convo.product.name ? (
                    <span className="muted tnum"> · {convo.product.sku}</span>
                  ) : null}
                </>
              )}
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

      {convo.summary && <SummaryCard summary={convo.summary} />}

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
              <div className="row between" style={{ marginBottom: 6, alignItems: 'center' }}>
                <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <StatusPill kind={pillKindForType(m.type, m.error)}>{m.type}</StatusPill>
                  {m.round !== null && m.round !== undefined && (
                    <span className="t-xs muted tnum">r{m.round}</span>
                  )}
                  <span className="t-xs muted tnum">{m.ts}</span>
                </div>
                <button className="btn tiny" onClick={() => toggle(i)}>
                  [ {showRaw[i] ? 'hide' : 'details'} ]
                </button>
              </div>
              <div className="t-sm" style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'baseline' }}>
                <span className="muted">{m.from}</span>
                <span className="muted">→</span>
                <span className="muted">{m.to}</span>
                {m.highlight && (
                  <>
                    <span className="muted">·</span>
                    <span className="tnum">{m.highlight}</span>
                  </>
                )}
              </div>
              {showRaw[i] && (
                <MessageDetails
                  type={m.type}
                  payload={m.payload as Record<string, unknown>}
                  currency={convo.summary?.currency ?? 'USD'}
                />
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

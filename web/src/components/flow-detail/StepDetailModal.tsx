'use client'
import React, { useEffect } from 'react'
import { StatusPill } from '@/components/primitives/StatusPill'
import type { ActiveVendor, VendorThread } from '@/types'

interface StepDetailModalProps {
  vendor: ActiveVendor
  turn: VendorThread
  onClose: () => void
}

interface Field {
  label: string
  value: React.ReactNode
  mono?: boolean
}

function pillKindForType(type: string): 'ok' | 'warn' | 'err' | 'idle' {
  if (type === 'WALKAWAY') return 'err'
  if (type === 'COUNTER_OFFER') return 'warn'
  return 'ok'
}

function fmtMoney(value: number | null | undefined, currency = 'USD'): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const symbol = currency === 'USD' ? '$' : `${currency} `
  return `${symbol}${value.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

function pickStr(p: Record<string, unknown>, key: string): string | null {
  const v = p[key]
  return typeof v === 'string' && v ? v : typeof v === 'number' ? String(v) : null
}

function pickNum(p: Record<string, unknown>, key: string): number | null {
  const v = p[key]
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
): Field[] {
  const c = currency || 'USD'
  const item =
    (payload.item && typeof payload.item === 'object'
      ? (payload.item as Record<string, unknown>)
      : {})
  const out: Field[] = []
  const push = (label: string, value: React.ReactNode, mono?: boolean) => {
    if (value === null || value === undefined || value === '') return
    out.push({ label, value, mono })
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
      if (type === 'COUNTER_OFFER') push('Final', payload.is_final ? 'yes' : 'no')
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
  return out
}

function lineItemsFromPayload(payload: Record<string, unknown>): Record<string, unknown>[] {
  const raw = payload.line_items
  if (!Array.isArray(raw)) return []
  return raw.filter((x): x is Record<string, unknown> => !!x && typeof x === 'object')
}

export function StepDetailModal({ vendor, turn, onClose }: StepDetailModalProps) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const type = turn.type ?? turn.what
  const payload = turn.payload ?? {}
  const currency = (pickStr(payload, 'currency') as string) || 'USD'
  const fields = fieldsForType(type, payload, currency)
  const lineItems = lineItemsFromPayload(payload)
  const moneyKeys = new Set(['unit_price', 'total_price'])
  const lineItemKeys = lineItems[0] ? Object.keys(lineItems[0]) : []

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <div className="t-xs upper muted">Communication detail</div>
            <div
              className="page-title"
              style={{ fontSize: 'var(--t-xl)', marginTop: 4 }}
            >
              <span style={{ marginRight: 10 }}>
                <StatusPill kind={pillKindForType(type)}>{type}</StatusPill>
              </span>
              {vendor.name}
            </div>
            <div className="t-sm muted" style={{ marginTop: 4 }}>
              {turn.who === 'them' ? '← from vendor' : '→ to vendor'}
              {turn.round !== null && turn.round !== undefined
                ? ` · round ${turn.round}`
                : ''}
              {turn.ts ? ` · ${turn.ts}` : ''}
            </div>
          </div>
          <button type="button" className="btn ghost" onClick={onClose}>
            [ × close ]
          </button>
        </div>

        <div className="modal-body">
          {fields.length === 0 && lineItems.length === 0 ? (
            <div className="t-sm muted">No payload fields for this step.</div>
          ) : (
            <div className="col" style={{ gap: 16 }}>
              {fields.length > 0 && (
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                    gap: 12,
                  }}
                >
                  {fields.map((f) => (
                    <div key={f.label} className="col" style={{ gap: 2 }}>
                      <span className="t-xs upper muted">{f.label}</span>
                      <span className={f.mono ? 'tnum' : undefined}>{f.value || '—'}</span>
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
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

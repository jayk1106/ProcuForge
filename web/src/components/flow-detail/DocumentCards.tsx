'use client'
import React from 'react'
import { fmtMoney } from '@/lib/format'

interface Field {
  label: string
  value: React.ReactNode
  mono?: boolean
}

interface LineItem {
  [key: string]: unknown
}

function pickStr(obj: Record<string, unknown> | null | undefined, ...keys: string[]): string {
  if (!obj) return ''
  for (const k of keys) {
    const v = obj[k]
    if (v != null && v !== '') return String(v)
  }
  return ''
}

function pickNum(
  obj: Record<string, unknown> | null | undefined,
  ...keys: string[]
): number | null {
  if (!obj) return null
  for (const k of keys) {
    const v = obj[k]
    if (typeof v === 'number') return v
    if (typeof v === 'string' && v.trim() !== '' && !Number.isNaN(Number(v))) return Number(v)
  }
  return null
}

function lineItems(obj: Record<string, unknown> | null | undefined): LineItem[] {
  const raw = obj?.line_items
  if (!Array.isArray(raw)) return []
  return raw.filter((x): x is LineItem => !!x && typeof x === 'object')
}

function fmtDate(value: string): string {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value.slice(0, 10)
  return d.toISOString().slice(0, 10)
}

function DocCard({
  fields,
  items,
  itemMoneyKeys,
}: {
  fields: Field[]
  items: LineItem[]
  itemMoneyKeys?: Set<string>
}) {
  const moneyKeys = itemMoneyKeys ?? new Set(['unit_price', 'total_price'])
  const itemKeys = items[0] ? Object.keys(items[0]) : []
  return (
    <div className="doc-card">
      {fields.length > 0 && (
        <div className="doc-grid">
          {fields.map((f) => (
            <div key={f.label} className="doc-field">
              <span className="t-xs upper muted">{f.label}</span>
              <span className={f.mono ? 'tnum' : undefined}>{f.value || '—'}</span>
            </div>
          ))}
        </div>
      )}
      {items.length > 0 && (
        <div className="doc-items">
          <div className="t-xs upper muted" style={{ marginBottom: 6 }}>
            Line items
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table className="doc-table t-sm">
              <thead>
                <tr>
                  {itemKeys.map((k) => (
                    <th key={k} className="t-xs upper muted">
                      {k.replace(/_/g, ' ')}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((li, idx) => (
                  <tr key={idx}>
                    {itemKeys.map((k) => {
                      const v = li[k]
                      const isMoney = moneyKeys.has(k) && typeof v === 'number'
                      return (
                        <td key={k} className="tnum">
                          {v === null || v === undefined
                            ? '—'
                            : isMoney
                            ? fmtMoney(v as number)
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
  )
}

export function PoCard({ po }: { po: Record<string, unknown> }) {
  const total = pickNum(po, 'total_amount', 'agreed_price')
  const agreed = pickNum(po, 'agreed_price')
  const fields: Field[] = [
    { label: 'PO number', value: pickStr(po, 'po_number'), mono: true },
    { label: 'RFQ ref', value: pickStr(po, 'rfq_reference'), mono: true },
    { label: 'Vendor', value: pickStr(po, 'vendor_id'), mono: true },
    { label: 'Total amount', value: total != null ? fmtMoney(total) : '', mono: true },
    {
      label: 'Agreed price',
      value: agreed != null ? fmtMoney(agreed) : '',
      mono: true,
    },
    { label: 'Delivery date', value: fmtDate(pickStr(po, 'delivery_date')) },
  ]
  return <DocCard fields={fields} items={lineItems(po)} />
}

export function GrnCard({ grn }: { grn: Record<string, unknown> }) {
  const fields: Field[] = [
    { label: 'GRN number', value: pickStr(grn, 'grn_number'), mono: true },
    { label: 'PO number', value: pickStr(grn, 'po_number'), mono: true },
    { label: 'Received at', value: fmtDate(pickStr(grn, 'received_at')) },
  ]
  return (
    <DocCard
      fields={fields}
      items={lineItems(grn)}
      itemMoneyKeys={new Set()}
    />
  )
}

export function InvoiceCard({ invoice }: { invoice: Record<string, unknown> }) {
  const currency = pickStr(invoice, 'currency') || 'USD'
  const total = pickNum(invoice, 'total_amount')
  const fields: Field[] = [
    { label: 'Invoice', value: pickStr(invoice, 'invoice_number'), mono: true },
    { label: 'PO number', value: pickStr(invoice, 'po_number'), mono: true },
    { label: 'GRN ref', value: pickStr(invoice, 'grn_reference'), mono: true },
    { label: 'Invoice date', value: fmtDate(pickStr(invoice, 'invoice_date')) },
    { label: 'Due date', value: fmtDate(pickStr(invoice, 'due_date')) },
    { label: 'Total amount', value: total != null ? fmtMoney(total) : '', mono: true },
    { label: 'Currency', value: currency },
  ]
  return <DocCard fields={fields} items={lineItems(invoice)} />
}

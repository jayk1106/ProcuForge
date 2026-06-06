'use client'
import React from 'react'
import { StatusPill } from '@/components/primitives/StatusPill'
import { fmtMoney } from '@/lib/format'
import type { DiscoveredVendor } from '@/types'

interface DiscoveredVendorsBoardProps {
  vendors: DiscoveredVendor[]
}

function availabilityPill(status: string) {
  const normalized = status.toLowerCase()
  if (normalized === 'in_stock' || normalized === 'available') {
    return <StatusPill kind="ok">in stock</StatusPill>
  }
  if (normalized === 'limited' || normalized === 'low_stock') {
    return <StatusPill kind="warn">limited</StatusPill>
  }
  if (normalized === 'out_of_stock' || normalized === 'unavailable') {
    return <StatusPill kind="err">out of stock</StatusPill>
  }
  if (normalized === 'on_request' || normalized === 'made_to_order') {
    return <StatusPill kind="idle">on request</StatusPill>
  }
  return <StatusPill kind="idle">{status || 'unknown'}</StatusPill>
}

export function DiscoveredVendorsBoard({ vendors }: DiscoveredVendorsBoardProps) {
  return (
    <div className="discovered-board">
      {vendors.map((v) => (
        <article key={v.offerId} className="discovered-col">
          <header>
            <div className="row between">
              <div>
                <div className="vname">{v.name}</div>
                <div className="vid">
                  {v.vendorId.slice(0, 8)} · {v.country}
                </div>
              </div>
              {availabilityPill(v.availabilityStatus)}
            </div>
          </header>
          <div className="discovered-summary">
            <div className="k">sku</div>
            <div className="v">{v.sku || '—'}</div>
            <div className="k">catalog price</div>
            <div className="v">
              {v.unitPrice != null ? fmtMoney(v.unitPrice) : '—'}
              {v.unit ? <span className="muted"> / {v.unit}</span> : null}
            </div>
            <div className="k">lead time</div>
            <div className="v">{v.leadTimeDays != null ? `${v.leadTimeDays}d` : '—'}</div>
            <div className="k">contract</div>
            <div className="v">
              {v.contracted ? (
                <StatusPill kind="ok">contracted</StatusPill>
              ) : (
                <StatusPill kind="idle">spot</StatusPill>
              )}
            </div>
          </div>
        </article>
      ))}
    </div>
  )
}

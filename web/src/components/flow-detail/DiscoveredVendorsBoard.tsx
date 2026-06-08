'use client'
import React from 'react'
import { StatusPill } from '@/components/primitives/StatusPill'
import { fmtMoney } from '@/lib/format'
import type { DiscoveredVendor, VendorRelationSummary } from '@/types'

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

function riskPill(level: string) {
  const normalized = level.toLowerCase()
  if (normalized === 'low') return <StatusPill kind="ok">low risk</StatusPill>
  if (normalized === 'medium' || normalized === 'moderate') {
    return <StatusPill kind="warn">{normalized} risk</StatusPill>
  }
  if (normalized === 'high' || normalized === 'critical') {
    return <StatusPill kind="err">{normalized} risk</StatusPill>
  }
  return <StatusPill kind="idle">{normalized} risk</StatusPill>
}

function strengthLabel(strength: number | null): string {
  if (strength == null) return '—'
  return strength.toFixed(1)
}

function relationBadges(relation: VendorRelationSummary | null | undefined) {
  if (!relation) return null
  const pills: React.ReactNode[] = []
  if (relation.preferredVendor) {
    pills.push(
      <StatusPill key="preferred" kind="ok">
        preferred
      </StatusPill>,
    )
  }
  if (relation.riskLevel) {
    pills.push(<React.Fragment key="risk">{riskPill(relation.riskLevel)}</React.Fragment>)
  }
  if (relation.usuallyOffersDiscount) {
    pills.push(
      <StatusPill key="discount" kind="go">
        usually discounts
      </StatusPill>,
    )
  }
  if (pills.length === 0) return null
  return (
    <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
      {pills}
    </div>
  )
}

export function DiscoveredVendorsBoard({ vendors }: DiscoveredVendorsBoardProps) {
  return (
    <div className="discovered-board">
      {vendors.map((v) => {
        const relation = v.vendorRelation ?? null
        const currencyMismatch = v.currencyMatchesRequest === false
        return (
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
              {relationBadges(relation)}
            </header>
            <div className="discovered-summary">
              <div className="k">sku</div>
              <div className="v">{v.sku || '—'}</div>
              <div className="k">catalog price</div>
              <div className="v">
                {v.unitPrice != null ? fmtMoney(v.unitPrice) : '—'}
                {v.unit ? <span className="muted"> / {v.unit}</span> : null}
                {currencyMismatch && (
                  <span className="muted" style={{ marginLeft: 6 }}>
                    ({v.currency} ≠ request)
                  </span>
                )}
              </div>
              <div className="k">lead time</div>
              <div className="v">{v.leadTimeDays != null ? `${v.leadTimeDays}d` : '—'}</div>
              <div className="k">min order</div>
              <div className="v">{v.minimumOrderQty && v.minimumOrderQty > 0 ? v.minimumOrderQty : '—'}</div>
              <div className="k">contract</div>
              <div className="v">
                {v.contracted ? (
                  <StatusPill kind="ok">contracted</StatusPill>
                ) : (
                  <StatusPill kind="idle">spot</StatusPill>
                )}
              </div>
              {relation && (
                <>
                  <div className="k">relationship</div>
                  <div className="v">
                    {relation.relationshipStatus || '—'}
                    {relation.relationshipStrength != null && (
                      <span className="muted"> · {strengthLabel(relation.relationshipStrength)}/10</span>
                    )}
                  </div>
                  {relation.qualityScore != null && (
                    <>
                      <div className="k">quality</div>
                      <div className="v">{relation.qualityScore.toFixed(1)}/5</div>
                    </>
                  )}
                  {relation.averageDeliveryDelayDays != null && (
                    <>
                      <div className="k">avg delay</div>
                      <div className="v">{relation.averageDeliveryDelayDays.toFixed(1)}d</div>
                    </>
                  )}
                  {relation.averageDiscountPercent != null && (
                    <>
                      <div className="k">avg discount</div>
                      <div className="v">{relation.averageDiscountPercent.toFixed(1)}%</div>
                    </>
                  )}
                </>
              )}
            </div>
          </article>
        )
      })}
    </div>
  )
}

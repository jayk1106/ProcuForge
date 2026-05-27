'use client'
import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import { ACTIVE_FLOW } from '@/lib/data'
import { fmtMoney } from '@/lib/format'
import { useChatContext } from '@/components/layout/ChatContext'
import { AsciiRule } from '@/components/primitives/AsciiRule'
import { StatusPill } from '@/components/primitives/StatusPill'
import { Section } from '@/components/primitives/Section'
import { Bracketed } from '@/components/primitives/Bracketed'
import { PfSelect } from '@/components/primitives/PfSelect'
import { Timeline } from './Timeline'
import { SidebarNav } from './SidebarNav'
import { ActivityRail } from './ActivityRail'
import { NegotiationBoard } from './NegotiationBoard'
import { ActionBanner } from './ActionBanner'

type Variant = 'action' | 'normal' | 'empty'

export function FlowDetailClient() {
  const flow = ACTIVE_FLOW
  const router = useRouter()
  const { openChat } = useChatContext()
  const [variant, setVariant] = useState<Variant>('action')
  const [activeSec, setActiveSec] = useState('neg')

  const showAction = variant === 'action'
  const isEmpty = variant === 'empty'

  return (
    <div className="viewport">
      <div className="crumbs">
        <a onClick={() => router.push('/flows')} style={{ cursor: 'pointer' }}>
          Flows
        </a>
        <span className="sep">/</span>
        <span className="here">{flow.id}</span>
        <div className="spacer" />
        <div className="row" style={{ gap: 6 }}>
          <span className="t-xs muted upper">view</span>
          <PfSelect value={variant} onChange={(e) => setVariant(e.target.value as Variant)}>
            <option value="action">action required (default)</option>
            <option value="normal">no action — agents working</option>
            <option value="empty">just opened (empty)</option>
          </PfSelect>
        </div>
      </div>

      <header className="page-head">
        <div className="row between" style={{ alignItems: 'flex-start' }}>
          <div>
            <div className="t-xs upper muted">Purchase Request</div>
            <h1 className="page-title tnum">
              {flow.id}{' '}
              <span className="muted" style={{ fontWeight: 400 }}>
                ·
              </span>{' '}
              {flow.title}
            </h1>
            <div className="page-sub">
              opened {flow.opened} · requester{' '}
              <span className="ink">{flow.requester}</span> · cost center {flow.costCenter} · need
              by {flow.needBy}
            </div>
          </div>
          <div className="row" style={{ gap: 6 }}>
            <button className="btn" onClick={openChat}>
              [ ask about this PR ]
            </button>
            <button className="btn">[ export audit log ]</button>
          </div>
        </div>
      </header>

      {showAction && !isEmpty && <ActionBanner />}

      <Timeline
        phase={isEmpty ? 'rfq' : flow.currentPhase}
        durations={flow.phaseDurations}
        empty={isEmpty}
      />

      <div className="flow-layout" style={{ marginTop: 20 }}>
        <SidebarNav active={activeSec} onPick={setActiveSec} isEmpty={isEmpty} />

        <main>
          {isEmpty ? (
            <EmptyFlowBody />
          ) : (
            <>
              <Section
                title="Specification & approval"
                num="1.0"
                defaultOpen={false}
                status={<StatusPill kind="ok">spec validated</StatusPill>}
              >
                <div className="kv">
                  <div className="k">SKU</div>
                  <div className="v tnum">CNC-SPINDLE-7K5-IP65</div>
                  <div className="k">Quantity</div>
                  <div className="v tnum">24 units</div>
                  <div className="k">Target total</div>
                  <div className="v tnum">
                    {fmtMoney(flow.target)} (≤ $7,766/unit)
                  </div>
                  <div className="k">Specification</div>
                  <div className="v">{flow.spec}</div>
                  <div className="k">Approver</div>
                  <div className="v">
                    e.lindberg (auto-approved, Class B ≤ $250k)
                  </div>
                </div>
              </Section>

              <Section
                title="RFQ"
                num="2.0"
                defaultOpen={false}
                status={<StatusPill kind="ok">closed · 4 of 7 responded</StatusPill>}
              >
                <div className="kv">
                  <div className="k">Sent to</div>
                  <div className="v">7 vendors (Tier-2 + Tier-3, region: NA + DE + JP)</div>
                  <div className="k">Window</div>
                  <div className="v">2026-05-02 → 2026-05-03 (24h)</div>
                  <div className="k">Responded</div>
                  <div className="v">V-0218, V-0421, V-0719, V-1102</div>
                  <div className="k">No response</div>
                  <div className="v faint">V-0312, V-0588, V-0904</div>
                </div>
              </Section>

              <Section
                title="Negotiation — parallel tracks"
                num="3.0"
                defaultOpen
                status={<StatusPill kind="go">in progress · 4 vendors</StatusPill>}
                right={
                  <span className="t-xs muted">
                    target {fmtMoney(flow.target)} · best so far{' '}
                    <span className="ink">$182,640</span>
                  </span>
                }
              >
                <NegotiationBoard vendors={flow.vendors} />
              </Section>

              <Section
                title="Purchase order"
                num="4.0"
                pending
                defaultOpen={false}
                status={<StatusPill kind="idle">pending — awaits selection</StatusPill>}
              >
                <PendingPlaceholder label="PO will be issued automatically once vendor is selected and approved." />
              </Section>

              <Section
                title="Goods receipt (GRN)"
                num="5.0"
                pending
                defaultOpen={false}
                status={<StatusPill kind="idle">pending</StatusPill>}
              >
                <PendingPlaceholder label="Once delivery occurs, GRN agent will reconcile against PO." />
              </Section>

              <Section
                title="Invoice 3-way match"
                num="6.0"
                pending
                defaultOpen={false}
                status={<StatusPill kind="idle">pending</StatusPill>}
              >
                <PendingPlaceholder label="Match invoice ↔ PO ↔ GRN. Discrepancies > $50 will be escalated." />
              </Section>

              <Section
                title="Final completion"
                num="7.0"
                pending
                defaultOpen={false}
                status={<StatusPill kind="idle">pending</StatusPill>}
              >
                <PendingPlaceholder label="Mark ready-for-payment. Archive immutable audit trail." />
              </Section>
            </>
          )}
        </main>

        <ActivityRail items={isEmpty ? flow.activity.slice(-2) : flow.activity} />
      </div>

      <div style={{ height: 80 }} />
    </div>
  )
}

function PendingPlaceholder({ label }: { label: string }) {
  return (
    <div className="row" style={{ gap: 12, color: 'var(--muted)', fontSize: 'var(--t-sm)' }}>
      <Bracketed>pending</Bracketed>
      <span>{label}</span>
    </div>
  )
}

function EmptyFlowBody() {
  return (
    <div>
      <div className="empty" style={{ padding: '40px 28px', marginTop: 0 }}>
        <pre className="ascii-mark">──── agents starting ────</pre>
        <div className="muted t-sm">
          IntakeAgent has accepted this request. SpecAgent is validating the SKU now.
          <br />
          RFQ broadcast will go out within ~5 minutes.
        </div>
        <div style={{ marginTop: 18 }} className="thinking">
          analyzing spec against catalog
        </div>
      </div>
    </div>
  )
}

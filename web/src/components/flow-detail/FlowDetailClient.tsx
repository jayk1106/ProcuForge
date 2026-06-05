'use client'
import React, { useState, useEffect, useCallback, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { approveWorkflow, getWorkflowDetail, getWorkflowState } from '@/lib/api-client'
import { fmtMoney } from '@/lib/format'
import type { ActiveFlow, PhaseStatus } from '@/types'
import { useChatContext } from '@/components/layout/ChatContext'
import { StatusPill } from '@/components/primitives/StatusPill'
import { Section } from '@/components/primitives/Section'
import { Bracketed } from '@/components/primitives/Bracketed'
import { Timeline } from './Timeline'
import { SidebarNav } from './SidebarNav'
import { ActivityRail } from './ActivityRail'
import { NegotiationBoard } from './NegotiationBoard'
import { DiscoveredVendorsBoard } from './DiscoveredVendorsBoard'
import { PoCard, GrnCard, InvoiceCard } from './DocumentCards'
import { ActionBanner } from './ActionBanner'
import { StateDebugPanel } from '@/components/primitives/StateDebugPanel'
import { useWorkflowSocket } from '@/hooks/useWorkflowSocket'

interface FlowDetailClientProps {
  workflowId: string
}

interface PhasePillSpec {
  kind: 'ok' | 'go' | 'warn' | 'err' | 'idle'
  text: string
}

function pillForStatus(
  status: PhaseStatus | undefined,
  labels: { done: string; inProgress: string; pending: string; walked?: string }
): PhasePillSpec {
  if (status === 'done') return { kind: 'ok', text: labels.done }
  if (status === 'in_progress') return { kind: 'go', text: labels.inProgress }
  if (status === 'walked') return { kind: 'err', text: labels.walked ?? 'walked away' }
  return { kind: 'idle', text: labels.pending }
}

function selectedVendorName(flow: ActiveFlow): string | null {
  const winner = flow.vendors.find((v) => v.status === 'WON')
  if (winner) return winner.name
  const sv = flow.selectedVendor
  if (sv && typeof sv === 'object' && typeof (sv as Record<string, unknown>).vendor === 'string') {
    return (sv as Record<string, string>).vendor
  }
  return null
}

export function FlowDetailClient({ workflowId }: FlowDetailClientProps) {
  const router = useRouter()
  const { openChat } = useChatContext()
  const [flow, setFlow] = useState<ActiveFlow | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [approving, setApproving] = useState(false)
  const [activeSec, setActiveSec] = useState('neg')

  // load() only mutates `flow`/`error`; no loading flag. The render below
  // shows a splash only while `flow` is null, so WS-driven updates and
  // refresh clicks update in place without an interstitial.
  const load = useCallback(async () => {
    try {
      const data = await getWorkflowDetail(workflowId)
      setFlow(data)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load workflow')
    }
  }, [workflowId])

  useEffect(() => {
    load()
  }, [load])

  useWorkflowSocket<ActiveFlow>(`/ws/workflow/${workflowId}`, {
    onState: (next) => {
      setFlow(next)
      setError(null)
    },
    debugLabel: 'flow',
  })

  async function handleApprove() {
    setApproving(true)
    try {
      await approveWorkflow(workflowId)
      // No explicit re-fetch: the buyer agent's next state_delta event will
      // push a fresh DTO over WS. If it doesn't arrive within ~2s, the user
      // can hit refresh.
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Approval failed')
    } finally {
      setApproving(false)
    }
  }

  const handlePickSection = useCallback((id: string) => {
    setActiveSec(id)
    if (typeof document !== 'undefined') {
      const el = document.getElementById(`sec-${id}`)
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [])

  const phaseStatus: Record<string, PhaseStatus> = useMemo(
    () =>
      flow?.phaseStatus ?? {
        rfq: 'pending',
        neg: 'pending',
        po: 'pending',
        grn: 'pending',
        inv: 'pending',
        done: 'pending',
      },
    [flow?.phaseStatus]
  )

  if (!flow) {
    if (error) {
      return (
        <div className="viewport">
          <div className="empty" style={{ marginTop: 40 }}>
            <pre className="ascii-mark">──── error ────</pre>
            <div>{error}</div>
            <button
              className="btn"
              style={{ marginTop: 12 }}
              onClick={() => router.push('/flows')}
            >
              [ back to flows ]
            </button>
          </div>
        </div>
      )
    }
    return (
      <div className="viewport">
        <div className="thinking" style={{ marginTop: 40 }}>
          loading workflow…
        </div>
      </div>
    )
  }

  const isEmpty = flow.vendors.length === 0 && flow.currentPhase === 'rfq'
  const showAction = flow.needsAction

  const vendorCount = flow.vendors.length
  const discoveredCount = flow.discoveredVendors?.length ?? 0
  const winner = selectedVendorName(flow)

  const negPill: PhasePillSpec = (() => {
    if (phaseStatus.neg === 'walked') {
      return { kind: 'err', text: 'no vendor available' }
    }
    if (phaseStatus.neg === 'done') {
      return { kind: 'ok', text: winner ? `awarded · ${winner}` : 'completed' }
    }
    if (vendorCount === 0) return { kind: 'idle', text: 'awaiting vendors' }
    return { kind: 'go', text: `in progress · ${vendorCount} vendors` }
  })()

  const poPill = pillForStatus(phaseStatus.po, {
    done: 'fulfilled',
    inProgress: 'issued',
    pending: 'pending',
    walked: 'rejected',
  })
  const grnPill = pillForStatus(phaseStatus.grn, {
    done: 'received',
    inProgress: 'in transit',
    pending: 'pending',
  })
  const invPill = pillForStatus(phaseStatus.inv, {
    done: 'matched',
    inProgress: 'verifying',
    pending: 'pending',
  })
  const donePill = pillForStatus(phaseStatus.done, {
    done: 'complete',
    inProgress: 'finalizing',
    pending: 'pending',
  })

  const grn = flow.grn as Record<string, unknown> | null | undefined
  const invoice = flow.invoice as Record<string, unknown> | null | undefined

  return (
    <div className="viewport">
      <div className="crumbs">
        <a onClick={() => router.push('/flows')} style={{ cursor: 'pointer' }}>
          Flows
        </a>
        <span className="sep">/</span>
        <span className="here">{flow.requestId ?? flow.id.slice(0, 8)}</span>
      </div>

      <header className="page-head">
        <div className="row between" style={{ alignItems: 'flex-start' }}>
          <div>
            <div className="t-xs upper muted">Purchase Request</div>
            <h1 className="page-title tnum">
              {flow.requestId ?? flow.id}{' '}
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
            <button className="btn" onClick={load}>
              [ refresh ]
            </button>
            <button className="btn" onClick={openChat}>
              [ ask about this PR ]
            </button>
          </div>
        </div>
      </header>

      {showAction && !isEmpty && (
        <ActionBanner
          actionLabel={flow.actionLabel}
          onApprove={handleApprove}
          approving={approving}
        />
      )}

      <Timeline
        phase={isEmpty ? 'rfq' : flow.currentPhase}
        durations={flow.phaseDurations}
        phaseStatus={phaseStatus}
        empty={isEmpty}
      />

      <div className="flow-layout" style={{ marginTop: 20 }}>
        <SidebarNav
          active={activeSec}
          onPick={handlePickSection}
          isEmpty={isEmpty}
          flow={flow}
        />

        <main>
          {isEmpty ? (
            <EmptyFlowBody />
          ) : (
            <>
              <div id="sec-spec">
                <Section
                  title="Specification & approval"
                  num="1.0"
                  defaultOpen={false}
                  status={
                    flow.specDone !== false ? (
                      <StatusPill kind="ok">spec validated</StatusPill>
                    ) : (
                      <StatusPill kind="go">validating</StatusPill>
                    )
                  }
                >
                  <div className="kv">
                    <div className="k">Target total</div>
                    <div className="v tnum">{fmtMoney(flow.target)}</div>
                    <div className="k">Specification</div>
                    <div className="v">{flow.spec || '—'}</div>
                    <div className="k">Status</div>
                    <div className="v">{flow.prStatus ?? '—'}</div>
                  </div>
                </Section>
              </div>

              <div id="sec-discovered">
                <Section
                  title="Vendors discovered"
                  num="2.0"
                  defaultOpen={discoveredCount > 0 && vendorCount === 0}
                  pending={discoveredCount === 0 && phaseStatus.rfq === 'pending'}
                  status={(() => {
                    if (discoveredCount === 0 && phaseStatus.rfq === 'walked') {
                      return <StatusPill kind="err">no vendors found</StatusPill>
                    }
                    if (discoveredCount === 0) {
                      return <StatusPill kind="idle">searching catalog</StatusPill>
                    }
                    const kind: 'ok' | 'go' = vendorCount > 0 ? 'ok' : 'go'
                    const text =
                      vendorCount > 0
                        ? `${discoveredCount} shortlisted`
                        : `${discoveredCount} ready to negotiate`
                    return <StatusPill kind={kind}>{text}</StatusPill>
                  })()}
                >
                  {discoveredCount > 0 ? (
                    <DiscoveredVendorsBoard vendors={flow.discoveredVendors ?? []} />
                  ) : (
                    <PendingPlaceholder label="Vendor search agent is scanning the catalog." />
                  )}
                </Section>
              </div>

              <div id="sec-neg">
                <Section
                  title="Negotiation — parallel tracks"
                  num="3.0"
                  defaultOpen
                  status={<StatusPill kind={negPill.kind}>{negPill.text}</StatusPill>}
                  right={
                    flow.target > 0 ? (
                      <span className="t-xs muted">target {fmtMoney(flow.target)}</span>
                    ) : undefined
                  }
                >
                  {flow.vendors.length > 0 ? (
                    <NegotiationBoard vendors={flow.vendors} />
                  ) : (
                    <PendingPlaceholder label="Vendor search and negotiation in progress." />
                  )}
                </Section>
              </div>

              <div id="sec-award">
                <SelectedVendorSection
                  flow={flow}
                  negPhase={phaseStatus.neg}
                />
              </div>

              <div id="sec-po">
                <Section
                  title="Purchase order"
                  num="4.0"
                  pending={!flow.po}
                  defaultOpen={!!flow.po && phaseStatus.po === 'in_progress'}
                  status={<StatusPill kind={poPill.kind}>{poPill.text}</StatusPill>}
                >
                  {flow.po ? (
                    <PoCard po={flow.po as Record<string, unknown>} />
                  ) : (
                    <PendingPlaceholder label="PO will be issued after approval." />
                  )}
                </Section>
              </div>

              <div id="sec-grn">
                <Section
                  title="Goods receipt"
                  num="5.0"
                  pending={!grn}
                  defaultOpen={!!grn && phaseStatus.grn === 'in_progress'}
                  status={<StatusPill kind={grnPill.kind}>{grnPill.text}</StatusPill>}
                >
                  {grn ? (
                    <GrnCard grn={grn as Record<string, unknown>} />
                  ) : (
                    <PendingPlaceholder label="Awaiting goods receipt from vendor." />
                  )}
                </Section>
              </div>

              <div id="sec-inv">
                <Section
                  title="Invoice match"
                  num="6.0"
                  pending={!invoice}
                  defaultOpen={!!invoice && phaseStatus.inv === 'in_progress'}
                  status={<StatusPill kind={invPill.kind}>{invPill.text}</StatusPill>}
                >
                  {invoice ? (
                    <InvoiceCard invoice={invoice as Record<string, unknown>} />
                  ) : (
                    <PendingPlaceholder label="Awaiting vendor invoice." />
                  )}
                </Section>
              </div>

              <div id="sec-done">
                <Section
                  title="Completion"
                  num="7.0"
                  pending={phaseStatus.done !== 'done'}
                  defaultOpen={phaseStatus.done === 'done'}
                  status={<StatusPill kind={donePill.kind}>{donePill.text}</StatusPill>}
                >
                  {phaseStatus.done === 'done' ? (
                    <div className="kv">
                      <div className="k">PO</div>
                      <div className="v tnum">
                        {(flow.po as { po_number?: string } | null)?.po_number ?? '—'}
                      </div>
                      <div className="k">GRN</div>
                      <div className="v tnum">
                        {(grn as { grn_number?: string } | null)?.grn_number ?? '—'}
                      </div>
                      <div className="k">Invoice</div>
                      <div className="v tnum">
                        {(invoice as { invoice_number?: string } | null)?.invoice_number ?? '—'}
                      </div>
                      <div className="k">Final price</div>
                      <div className="v tnum">
                        {fmtMoney(
                          ((flow.po as { agreed_price?: number } | null)?.agreed_price ??
                            (flow.selectedVendor as { final_price?: number } | null)?.final_price ??
                            0) as number
                        )}
                      </div>
                    </div>
                  ) : (
                    <PendingPlaceholder label="Workflow will close after payment is authorized." />
                  )}
                </Section>
              </div>
            </>
          )}
        </main>

        <ActivityRail items={flow.activity} />
      </div>

      <StateDebugPanel
        label="buyer session state"
        fetchState={() => getWorkflowState(workflowId)}
      />

      <div style={{ height: 80 }} />
    </div>
  )
}

interface SelectedVendorSectionProps {
  flow: ActiveFlow
  negPhase: PhaseStatus | undefined
}

function SelectedVendorSection({ flow, negPhase }: SelectedVendorSectionProps) {
  const winner = flow.vendors.find((v) => v.status === 'WON')
  const sv = (flow.selectedVendor ?? {}) as Record<string, unknown>
  const finalPrice =
    (typeof sv.final_price === 'number' ? sv.final_price : undefined) ??
    (typeof (flow.po as { agreed_price?: number } | null)?.agreed_price === 'number'
      ? (flow.po as { agreed_price?: number }).agreed_price
      : undefined) ??
    winner?.latest ??
    null
  const savings =
    finalPrice != null && flow.target > 0 ? flow.target - finalPrice : null
  const savingsPct =
    savings != null && flow.target > 0 ? (savings / flow.target) * 100 : null

  const pill = (() => {
    if (winner) return { kind: 'ok' as const, text: 'awarded' }
    if (negPhase === 'walked')
      return { kind: 'err' as const, text: 'no vendor available' }
    return { kind: 'idle' as const, text: 'pending' }
  })()

  return (
    <Section
      title="Selected vendor"
      num="3.5"
      pending={!winner}
      defaultOpen={!!winner}
      status={<StatusPill kind={pill.kind}>{pill.text}</StatusPill>}
    >
      {winner ? (
        <div className="award-card">
          <div className="award-head">
            <div>
              <div className="award-name">{winner.name}</div>
              <div className="award-meta">
                {winner.id} · {winner.country} · {winner.round}
              </div>
            </div>
            <span className="t-xs muted" style={{ letterSpacing: '0.08em', textTransform: 'uppercase' }}>
              [ ✓ awarded ]
            </span>
          </div>
          <div className="award-grid">
            <div className="k">Final price</div>
            <div className="v tnum">{finalPrice != null ? fmtMoney(finalPrice) : '—'}</div>
            <div className="k">vs target</div>
            <div
              className={`v ${
                savings != null && savings > 0
                  ? 'delta-down'
                  : savings != null && savings < 0
                  ? 'delta-up'
                  : ''
              }`}
            >
              {savings == null
                ? '—'
                : savings >= 0
                ? `−${fmtMoney(savings)}`
                : `+${fmtMoney(-savings)}`}
              {savingsPct != null && (
                <span className="muted" style={{ marginLeft: 6 }}>
                  ({savingsPct >= 0 ? '−' : '+'}
                  {Math.abs(savingsPct).toFixed(1)}%)
                </span>
              )}
            </div>
            <div className="k">Lead time</div>
            <div className="v">{winner.lead}</div>
            <div className="k">MOQ</div>
            <div className="v">{winner.moq}</div>
            <div className="k">Rounds</div>
            <div className="v">{winner.round}</div>
            <div className="k">Outcome</div>
            <div className="v">
              {typeof sv.outcome === 'string' ? String(sv.outcome) : 'ACCEPTED'}
            </div>
          </div>
        </div>
      ) : negPhase === 'walked' ? (
        <PendingPlaceholder label="No vendor could meet the requirements." />
      ) : (
        <PendingPlaceholder label="Awaiting negotiation outcome." />
      )}
    </Section>
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
          The buyer agent is processing this request. Vendor search and RFQ broadcast will follow.
        </div>
        <div style={{ marginTop: 18 }} className="thinking">
          analyzing spec against catalog
        </div>
      </div>
    </div>
  )
}

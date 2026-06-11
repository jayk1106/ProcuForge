'use client'
import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { approveWorkflow, getWorkflowDetail, getWorkflowState, resolveWorkflowEscalation } from '@/lib/api-client'
import { fmtMoney } from '@/lib/format'
import type { ActiveFlow, PhaseStatus } from '@/types'
import { StatusPill } from '@/components/primitives/StatusPill'
import { Section } from '@/components/primitives/Section'
import { Bracketed } from '@/components/primitives/Bracketed'
import { Timeline } from './Timeline'
import { SidebarNav } from './SidebarNav'
import { NegotiationBoard } from './NegotiationBoard'
import { DiscoveredVendorsBoard } from './DiscoveredVendorsBoard'
import { PoCard, GrnCard, InvoiceCard, ApprovalBanner } from './DocumentCards'
import { ActionBanner } from './ActionBanner'
import { StateDebugPanel } from '@/components/primitives/StateDebugPanel'
import { useWorkflowSocket } from '@/hooks/useWorkflowSocket'
import { mergeVendorsById } from './mergeVendors'

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

const ESCALATION_SOURCE_LABELS: Record<string, string> = {
  no_vendors_discovered: 'no vendors in catalog',
  vendors_all_filtered: 'all vendors filtered out',
  no_vendor_available: 'no vendor available',
  negotiator_stall: 'negotiation stalled',
  po_rejected: 'PO rejected by vendor',
  invoice_correction_pending: 'invoice correction pending',
}

function escalationSourceLabel(source: string): string {
  return ESCALATION_SOURCE_LABELS[source] ?? source.replace(/_/g, ' ')
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
  const [flow, setFlow] = useState<ActiveFlow | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [approving, setApproving] = useState(false)
  const [resolvingEscalation, setResolvingEscalation] = useState(false)
  const [activeSec, setActiveSec] = useState('spec')
  const viewportRef = useRef<HTMLDivElement>(null)
  const headRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const head = headRef.current
    const viewport = viewportRef.current
    if (!head || !viewport) return
    const ro = new ResizeObserver(() => {
      // 56px topnav offset + measured head height + a small gap
      viewport.style.setProperty('--flow-head-bottom', `${56 + head.offsetHeight + 12}px`)
    })
    ro.observe(head)
    return () => ro.disconnect()
  }, [flow])

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
      // Only vendors get merge-by-id protection — parallel negotiator tools
      // can broadcast snapshots that omit a sibling vendor mid-flight. All
      // other fields are replaced wholesale.
      setFlow((prev) =>
        prev ? { ...next, vendors: mergeVendorsById(prev.vendors, next.vendors) } : next,
      )
      setError(null)
    },
    debugLabel: 'flow',
  })

  async function handleResolveEscalation() {
    setResolvingEscalation(true)
    try {
      await resolveWorkflowEscalation(workflowId)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Resolve escalation failed')
    } finally {
      setResolvingEscalation(false)
    }
  }

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
        vendor: 'pending',
        po: 'pending',
        grn: 'pending',
        inv: 'pending',
        done: 'pending',
      },
    [flow?.phaseStatus]
  )

  // Track which workflow milestones the user has already seen, so we only
  // scroll on the *transition* into a new milestone (vendors discovered,
  // negotiation started, vendor awarded, PO/GRN/invoice arrived, completion).
  // The first render after the flow loads snapshots whatever milestones are
  // already true and does *not* scroll — that way reopening an in-progress
  // workflow leaves the user at the top, but live WS-driven progress
  // smooth-scrolls them to the section that just gained content.
  const milestonesRef = useRef<Set<string> | null>(null)
  useEffect(() => {
    if (!flow) return
    const winner = flow.vendors.find((v) => v.status === 'WON')
    const milestones: Record<string, boolean> = {
      discovered: (flow.discoveredVendors?.length ?? 0) > 0,
      neg: flow.vendors.length > 0,
      award: !!winner,
      po: !!flow.po,
      grn: !!flow.grn,
      inv: !!flow.invoice,
      done: phaseStatus.done === 'done',
    }

    if (milestonesRef.current === null) {
      milestonesRef.current = new Set(
        Object.entries(milestones)
          .filter(([, v]) => v)
          .map(([k]) => k)
      )
      return
    }

    const order = ['discovered', 'neg', 'award', 'po', 'grn', 'inv', 'done']
    let target: string | null = null
    for (const m of order) {
      if (milestones[m] && !milestonesRef.current.has(m)) {
        milestonesRef.current.add(m)
        target = m
      }
    }
    if (!target) return

    const id = target
    setActiveSec(id)
    requestAnimationFrame(() => {
      const el = document.getElementById(`sec-${id}`)
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }, [flow, phaseStatus])

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

  const isEmpty =
    flow.vendors.length === 0 &&
    (flow.discoveredVendors?.length ?? 0) === 0 &&
    flow.specDone === false &&
    flow.currentPhase === 'rfq'
  const pending = flow.pendingApproval ?? null
  // The HITL gates render per-section CTAs, so suppress the global ActionBanner
  // when one is active — otherwise the user sees two approve buttons.
  const showAction = flow.needsAction && !pending
  const escalation = flow.escalationContext ?? null
  const showEscalationBanner = Boolean(escalation)
  const canResolveEscalation =
    flow.prStatus === 'ESCALATED' && escalation?.tier === 'full'

  const approvalCta = (
    step: 'po' | 'grn' | 'completion',
    label: string,
  ) =>
    pending?.step === step
      ? {
          reason: pending.reason,
          buttonLabel: label,
          onApprove: handleApprove,
          busy: approving,
        }
      : undefined

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

  const actionRequiredPill: PhasePillSpec = { kind: 'warn', text: 'action required' }
  const poPill: PhasePillSpec = (() => {
    if (pending?.step === 'po') return actionRequiredPill
    if (phaseStatus.po === 'done') return { kind: 'ok', text: 'fulfilled' }
    if (phaseStatus.po === 'walked') return { kind: 'err', text: 'rejected' }
    if (phaseStatus.po === 'in_progress') {
      return flow.po
        ? { kind: 'go', text: 'issued' }
        : { kind: 'go', text: 'drafting' }
    }
    return { kind: 'idle', text: 'pending' }
  })()
  const grnPill: PhasePillSpec =
    pending?.step === 'grn'
      ? actionRequiredPill
      : pillForStatus(phaseStatus.grn, {
          done: 'sent',
          inProgress: 'in transit',
          pending: 'pending',
        })
  const invPill = pillForStatus(phaseStatus.inv, {
    done: 'matched',
    inProgress: 'verifying',
    pending: 'pending',
  })
  const donePill: PhasePillSpec =
    pending?.step === 'completion'
      ? actionRequiredPill
      : pillForStatus(phaseStatus.done, {
          done: 'complete',
          inProgress: 'finalizing',
          pending: 'pending',
        })

  const grn = flow.grn as Record<string, unknown> | null | undefined
  const invoice = flow.invoice as Record<string, unknown> | null | undefined

  return (
    <div className="viewport flow-detail-viewport" ref={viewportRef}>
      <div className="crumbs">
        <a onClick={() => router.push('/flows')} style={{ cursor: 'pointer' }}>
          Requests
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
              opened {flow.opened} · need by {flow.needBy}
            </div>
          </div>
          <div className="row" style={{ gap: 6 }}>
            <button className="btn" onClick={load}>
              [ refresh ]
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

      {showEscalationBanner && escalation && (
        <div
          className="action-banner"
          style={{
            marginTop: 12,
            padding: '12px 16px',
            border: '1px solid var(--warn, #c9a227)',
            background: 'var(--surface-2, rgba(201, 162, 39, 0.08))',
          }}
        >
          <div className="row between" style={{ alignItems: 'flex-start', gap: 12 }}>
            <div>
              <div className="t-sm upper muted">
                Escalation · {escalationSourceLabel(escalation.source)}
              </div>
              <div style={{ marginTop: 4 }}>{escalation.reason}</div>
              {escalation.recommendedAction && (
                <div className="t-xs muted" style={{ marginTop: 6 }}>
                  {escalation.recommendedAction}
                </div>
              )}
            </div>
            {canResolveEscalation && (
              <button
                className="btn accent"
                disabled={resolvingEscalation}
                onClick={handleResolveEscalation}
              >
                [ {resolvingEscalation ? 'resolving…' : 'resolve escalation'} ]
              </button>
            )}
          </div>
        </div>
      )}

      <div className="flow-timeline-sticky" ref={headRef}>
        <Timeline
          phase={isEmpty ? 'rfq' : flow.currentPhase}
          durations={flow.phaseDurations}
          phaseStatus={phaseStatus}
          empty={isEmpty}
        />
      </div>

      <div className="flow-layout no-rail" style={{ marginTop: 20 }}>
        <SidebarNav
          active={activeSec}
          onPick={handlePickSection}
          isEmpty={isEmpty}
          flow={flow}
        />

        <main>
          <div id="sec-spec">
                <Section
                  key={`spec-${flow.specDone !== false ? 'done' : 'validating'}`}
                  title="Specification & approval"
                  num="1.0"
                  defaultOpen
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
                  key={`discovered-${discoveredCount}-${vendorCount > 0 ? 'shortlisted' : 'pending'}`}
                  title="Vendors discovered"
                  num="2.0"
                  defaultOpen={discoveredCount > 0}
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
                >
                  {flow.vendors.length > 0 ? (
                    <NegotiationBoard
                      vendors={flow.vendors}
                      onResolveEscalation={
                        canResolveEscalation ? handleResolveEscalation : undefined
                      }
                      resolvingEscalation={resolvingEscalation}
                    />
                  ) : (
                    <PendingPlaceholder label="Vendor search and negotiation in progress." />
                  )}
                </Section>
              </div>

              <div id="sec-award">
                <SelectedVendorSection
                  key={flow.vendors.find((v) => v.status === 'WON') ? 'award-won' : 'award-pending'}
                  flow={flow}
                  negPhase={phaseStatus.neg}
                />
              </div>

              <div id="sec-po">
                <Section
                  key={
                    pending?.step === 'po'
                      ? 'po-gated'
                      : flow.po
                        ? 'po-issued'
                        : 'po-pending'
                  }
                  title="Purchase order"
                  num="4.0"
                  pending={!flow.po && pending?.step !== 'po'}
                  defaultOpen={
                    pending?.step === 'po' ||
                    !!flow.po ||
                    phaseStatus.po === 'in_progress'
                  }
                  status={<StatusPill kind={poPill.kind}>{poPill.text}</StatusPill>}
                >
                  {flow.po || pending?.step === 'po' ? (
                    <PoCard
                      po={(flow.po as Record<string, unknown> | null) ?? null}
                      approval={approvalCta('po', 'approve & send PO →')}
                    />
                  ) : (
                    <PendingPlaceholder
                      label={
                        phaseStatus.po === 'in_progress'
                          ? 'Drafting purchase order from negotiated terms.'
                          : 'PO will be issued after approval.'
                      }
                    />
                  )}
                </Section>
              </div>

              <div id="sec-grn">
                <Section
                  key={
                    pending?.step === 'grn'
                      ? 'grn-gated'
                      : grn
                        ? 'grn-received'
                        : 'grn-pending'
                  }
                  title="Goods receipt"
                  num="5.0"
                  pending={!grn && pending?.step !== 'grn'}
                  defaultOpen={
                    pending?.step === 'grn' ||
                    !!grn ||
                    phaseStatus.grn === 'in_progress'
                  }
                  status={<StatusPill kind={grnPill.kind}>{grnPill.text}</StatusPill>}
                >
                  {grn || pending?.step === 'grn' ? (
                    <GrnCard
                      grn={(grn as Record<string, unknown> | null) ?? null}
                      approval={approvalCta('grn', 'approve & send GRN →')}
                    />
                  ) : (
                    <PendingPlaceholder label="Awaiting goods receipt from vendor." />
                  )}
                </Section>
              </div>

              <div id="sec-inv">
                <Section
                  key={invoice ? 'inv-present' : 'inv-pending'}
                  title="Invoice match"
                  num="6.0"
                  pending={!invoice}
                  defaultOpen={!!invoice || phaseStatus.inv === 'in_progress'}
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
                  key={
                    pending?.step === 'completion'
                      ? 'done-gated'
                      : phaseStatus.done === 'done'
                        ? 'done-complete'
                        : 'done-pending'
                  }
                  title="Completion"
                  num="7.0"
                  pending={phaseStatus.done !== 'done' && pending?.step !== 'completion'}
                  defaultOpen={
                    phaseStatus.done === 'done' || pending?.step === 'completion'
                  }
                  status={<StatusPill kind={donePill.kind}>{donePill.text}</StatusPill>}
                >
                  {pending?.step === 'completion' && (
                    <ApprovalBanner
                      approval={{
                        reason: pending.reason,
                        buttonLabel: 'approve & close procurement →',
                        onApprove: handleApprove,
                        busy: approving,
                      }}
                    />
                  )}
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
                  ) : pending?.step === 'completion' ? null : (
                    <PendingPlaceholder label="Workflow will close after payment is authorized." />
                  )}
                </Section>
              </div>
        </main>
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

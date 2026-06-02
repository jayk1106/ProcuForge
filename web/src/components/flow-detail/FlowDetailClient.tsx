'use client'
import React, { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { approveWorkflow, getWorkflowDetail, getWorkflowState } from '@/lib/api-client'
import { fmtMoney } from '@/lib/format'
import type { ActiveFlow } from '@/types'
import { useChatContext } from '@/components/layout/ChatContext'
import { StatusPill } from '@/components/primitives/StatusPill'
import { Section } from '@/components/primitives/Section'
import { Bracketed } from '@/components/primitives/Bracketed'
import { Timeline } from './Timeline'
import { SidebarNav } from './SidebarNav'
import { ActivityRail } from './ActivityRail'
import { NegotiationBoard } from './NegotiationBoard'
import { ActionBanner } from './ActionBanner'
import { StateDebugPanel } from '@/components/primitives/StateDebugPanel'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

interface FlowDetailClientProps {
  workflowId: string
}

export function FlowDetailClient({ workflowId }: FlowDetailClientProps) {
  const router = useRouter()
  const { openChat } = useChatContext()
  const [flow, setFlow] = useState<ActiveFlow | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [approving, setApproving] = useState(false)
  const [activeSec, setActiveSec] = useState('neg')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getWorkflowDetail(workflowId)
      setFlow(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load workflow')
    } finally {
      setLoading(false)
    }
  }, [workflowId])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    let cancelled = false
    let ws: WebSocket | null = null
    try {
      const wsBase = API_URL.replace(/^http/, 'ws')
      ws = new WebSocket(`${wsBase}/ws/workflow/${workflowId}`)
      ws.onmessage = () => {
        if (!cancelled) load()
      }
      ws.onerror = () => {
        // ignore; refresh button still works
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
    }
  }, [workflowId, load])

  async function handleApprove() {
    setApproving(true)
    try {
      await approveWorkflow(workflowId)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Approval failed')
    } finally {
      setApproving(false)
    }
  }

  if (loading) {
    return (
      <div className="viewport">
        <div className="thinking" style={{ marginTop: 40 }}>
          loading workflow…
        </div>
      </div>
    )
  }

  if (error || !flow) {
    return (
      <div className="viewport">
        <div className="empty" style={{ marginTop: 40 }}>
          <pre className="ascii-mark">──── error ────</pre>
          <div>{error ?? 'Workflow not found'}</div>
          <button className="btn" style={{ marginTop: 12 }} onClick={() => router.push('/flows')}>
            [ back to flows ]
          </button>
        </div>
      </div>
    )
  }

  const isEmpty = flow.vendors.length === 0 && flow.currentPhase === 'rfq'
  const showAction = flow.needsAction

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
                  <div className="k">Target total</div>
                  <div className="v tnum">{fmtMoney(flow.target)}</div>
                  <div className="k">Specification</div>
                  <div className="v">{flow.spec || '—'}</div>
                  <div className="k">Status</div>
                  <div className="v">{flow.prStatus ?? '—'}</div>
                </div>
              </Section>

              <Section
                title="Negotiation — parallel tracks"
                num="3.0"
                defaultOpen
                status={
                  <StatusPill kind="go">
                    {flow.vendors.length > 0
                      ? `in progress · ${flow.vendors.length} vendors`
                      : 'awaiting vendors'}
                  </StatusPill>
                }
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

              <Section
                title="Purchase order"
                num="4.0"
                pending={!flow.po}
                defaultOpen={!!flow.po}
                status={
                  flow.po ? (
                    <StatusPill kind="ok">issued</StatusPill>
                  ) : (
                    <StatusPill kind="idle">pending</StatusPill>
                  )
                }
              >
                {flow.po ? (
                  <pre className="t-xs">{JSON.stringify(flow.po, null, 2)}</pre>
                ) : (
                  <PendingPlaceholder label="PO will be issued after approval." />
                )}
              </Section>
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

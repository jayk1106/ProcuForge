'use client'
import React, { forwardRef, useCallback, useImperativeHandle } from 'react'
import { useRouter } from 'next/navigation'
import { getWorkflows } from '@/lib/api-client'
import type { WorkflowRow } from '@/types/workflow'
import { useInfinitePagedList } from '@/hooks/useInfinitePagedList'
import { InfiniteScrollSentinel } from '@/components/primitives/InfiniteScrollSentinel'
import { PhaseDots } from './PhaseDots'
import { StatusPill } from '@/components/primitives/StatusPill'

const PAGE_SIZE = 25

export interface FlowsTableHandle {
  refresh: () => void
}

interface FlowsTableProps {
  onNewRequest: () => void
}

export const FlowsTable = forwardRef<FlowsTableHandle, FlowsTableProps>(
  function FlowsTable({ onNewRequest }, ref) {
    const router = useRouter()

    const fetcher = useCallback(
      ({ cursor }: { cursor?: string | null; filter: Record<string, never> }) =>
        getWorkflows({ cursor: cursor ?? undefined, limit: PAGE_SIZE }),
      [],
    )

    const { items, loading, loadingMore, error, hasMore, loadMore, refresh } =
      useInfinitePagedList<WorkflowRow, Record<string, never>>(fetcher, {})

    useImperativeHandle(ref, () => ({ refresh }), [refresh])

    function openFlow(id: string) {
      router.push(`/flows/${id}`)
    }

    function displayId(f: WorkflowRow) {
      return f.requestId ?? f.id.slice(0, 8)
    }

    if (loading) {
      return (
        <div className="empty" style={{ marginTop: 24 }}>
          <div className="thinking">loading workflows…</div>
        </div>
      )
    }

    if (error && items.length === 0) {
      return (
        <div className="empty" style={{ marginTop: 24 }}>
          <pre className="ascii-mark">──── error ────</pre>
          <div>{error}</div>
          <button className="btn" style={{ marginTop: 12 }} onClick={refresh}>
            [ retry ]
          </button>
        </div>
      )
    }

    if (items.length === 0) {
      return <EmptyState onNewRequest={onNewRequest} />
    }

    return (
      <>
        <table className="table" style={{ marginTop: 4 }}>
          <thead>
            <tr>
              <th style={{ width: 130 }}>PR ID</th>
              <th>Product</th>
              <th style={{ width: 220 }}>Phase</th>
              <th style={{ width: 200 }}>Current state</th>
              <th style={{ width: 80, textAlign: 'right' }}>Vendors</th>
              <th style={{ width: 80, textAlign: 'right' }}>Days</th>
              <th style={{ width: 220 }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {items.map((f) => (
              <tr
                key={f.id}
                className={f.needsAction ? 'action-row' : ''}
                onClick={() => openFlow(f.id)}
              >
                <td className="tnum">
                  <span className="ink">{displayId(f)}</span>
                </td>
                <td>
                  <div>{f.product}</div>
                  <div className="t-xs faint">
                    requested by {f.requestedBy} · {f.requestedAt}
                  </div>
                </td>
                <td>
                  <PhaseDots phase={f.phase} />
                </td>
                <td className="t-xs muted">{f.currentState}</td>
                <td className="tnum" style={{ textAlign: 'right' }}>
                  {f.vendors}
                </td>
                <td className="tnum" style={{ textAlign: 'right' }}>
                  {f.days}d
                </td>
                <td>
                  {f.needsAction ? (
                    <div
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 4,
                        alignItems: 'flex-start',
                      }}
                    >
                      <span className="t-xs accent" style={{ fontWeight: 600 }}>
                        {f.actionLabel}
                      </span>
                      <button
                        className="btn tiny accent"
                        onClick={(e) => {
                          e.stopPropagation()
                          openFlow(f.id)
                        }}
                      >
                        [ resolve → ]
                      </button>
                    </div>
                  ) : f.walked ? (
                    <StatusPill kind="err">walked away</StatusPill>
                  ) : f.phase === 'DONE' ? (
                    <StatusPill kind="ok">complete</StatusPill>
                  ) : (
                    <span className="t-sm muted">— agents working —</span>
                  )}
                </td>
              </tr>
            ))}
            {hasMore && (
              <tr>
                <td colSpan={7} style={{ padding: 0, border: 'none' }}>
                  <InfiniteScrollSentinel
                    onVisible={loadMore}
                    disabled={loadingMore || !hasMore}
                  />
                </td>
              </tr>
            )}
            {loadingMore && (
              <tr>
                <td colSpan={7} className="t-xs muted" style={{ textAlign: 'center', padding: 12 }}>
                  loading more…
                </td>
              </tr>
            )}
          </tbody>
        </table>

        <div style={{ height: 60 }} />
      </>
    )
  },
)

function EmptyState({ onNewRequest }: { onNewRequest: () => void }) {
  return (
    <div className="empty" style={{ marginTop: 32, padding: '64px 32px' }}>
      <pre className="ascii-mark">{`     ┌─────────────────────────┐
     │   no flows yet.         │
     │   start a new request   │
     └─────────────────────────┘`}</pre>
      <div style={{ marginTop: 22 }}>
        <button className="btn accent" onClick={onNewRequest}>
          [ start a new request ]
        </button>
      </div>
    </div>
  )
}

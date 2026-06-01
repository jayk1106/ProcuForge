'use client'
import React, { useState, useMemo, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { getWorkflows } from '@/lib/api-client'
import type { WorkflowRow } from '@/types/workflow'
import { FilterChip } from '@/components/primitives/FilterChip'
import { PhaseDots } from './PhaseDots'
import { StatusPill } from '@/components/primitives/StatusPill'
import { PfSelect } from '@/components/primitives/PfSelect'

type FilterKey = 'all' | 'progress' | 'action' | 'completed' | 'walked'
type SortKey = 'recent' | 'action' | 'longest'

interface FlowsTableProps {
  onNewRequest: () => void
  onLoaded?: (rows: WorkflowRow[]) => void
}

export function FlowsTable({ onNewRequest, onLoaded }: FlowsTableProps) {
  const router = useRouter()
  const [filter, setFilter] = useState<FilterKey>('all')
  const [sort, setSort] = useState<SortKey>('recent')
  const [query, setQuery] = useState('')
  const [rows, setRows] = useState<WorkflowRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getWorkflows()
      setRows(data)
      onLoaded?.(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load workflows')
    } finally {
      setLoading(false)
    }
  }, [onLoaded])

  useEffect(() => {
    load()
  }, [load])

  const counts = {
    all: rows.length,
    progress: rows.filter((f) => !f.walked && f.phase !== 'DONE').length,
    action: rows.filter((f) => f.needsAction).length,
    completed: rows.filter((f) => f.phase === 'DONE').length,
    walked: rows.filter((f) => f.walked).length,
  }

  const filtered = useMemo(() => {
    let list = rows.slice()
    if (filter === 'progress') list = list.filter((f) => !f.walked && f.phase !== 'DONE')
    if (filter === 'action') list = list.filter((f) => f.needsAction)
    if (filter === 'completed') list = list.filter((f) => f.phase === 'DONE')
    if (filter === 'walked') list = list.filter((f) => f.walked)
    if (query) {
      const q = query.toLowerCase()
      list = list.filter((f) =>
        (f.id + ' ' + (f.requestId ?? '') + ' ' + f.product + ' ' + f.requestedBy)
          .toLowerCase()
          .includes(q)
      )
    }
    if (sort === 'action') list.sort((a, b) => (b.needsAction ? 1 : 0) - (a.needsAction ? 1 : 0))
    if (sort === 'longest') list.sort((a, b) => b.days - a.days)
    return list
  }, [rows, filter, sort, query])

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

  if (error) {
    return (
      <div className="empty" style={{ marginTop: 24 }}>
        <pre className="ascii-mark">──── error ────</pre>
        <div>{error}</div>
        <button className="btn" style={{ marginTop: 12 }} onClick={load}>
          [ retry ]
        </button>
      </div>
    )
  }

  return (
    <>
      <div className="toolbar">
        <div className="toolbar-inner">
          <div className="chips">
            <FilterChip active={filter === 'all'} onClick={() => setFilter('all')} count={counts.all}>
              ALL
            </FilterChip>
            <FilterChip
              active={filter === 'progress'}
              onClick={() => setFilter('progress')}
              count={counts.progress}
            >
              IN PROGRESS
            </FilterChip>
            <FilterChip
              active={filter === 'action'}
              onClick={() => setFilter('action')}
              count={counts.action}
            >
              NEEDS YOUR ACTION
            </FilterChip>
            <FilterChip
              active={filter === 'completed'}
              onClick={() => setFilter('completed')}
              count={counts.completed}
            >
              COMPLETED
            </FilterChip>
            <FilterChip
              active={filter === 'walked'}
              onClick={() => setFilter('walked')}
              count={counts.walked}
            >
              WALKED AWAY
            </FilterChip>
          </div>
          <div className="spacer" />
          <div className="search">
            <span className="br">/</span>
            <input
              placeholder="search id, product, requester…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="row" style={{ gap: 6 }}>
            <span className="t-xs muted upper">sort</span>
            <PfSelect value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
              <option value="recent">most recent</option>
              <option value="action">action needed first</option>
              <option value="longest">longest pending</option>
            </PfSelect>
          </div>
          <div className="row" style={{ gap: 6 }}>
            <button className="btn" onClick={load}>
              [ refresh ]
            </button>
            <button className="btn accent" onClick={onNewRequest}>
              [ + new request ]
            </button>
          </div>
        </div>
      </div>

      {filtered.length === 0 ? (
        rows.length === 0 ? (
          <EmptyState onNewRequest={onNewRequest} />
        ) : (
          <div className="empty" style={{ marginTop: 24 }}>
            <div className="ascii-mark">──── no matches ────</div>
            <div>No flows match this filter.</div>
          </div>
        )
      ) : (
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
            {filtered.map((f) => (
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
          </tbody>
        </table>
      )}

      <div style={{ height: 60 }} />
    </>
  )
}

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

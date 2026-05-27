'use client'
import React, { useState, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { FLOWS, PHASES } from '@/lib/data'
import { FilterChip } from '@/components/primitives/FilterChip'
import { PhaseDots } from '@/components/primitives/PhaseDots'
import { StatusPill } from '@/components/primitives/StatusPill'
import { PfSelect } from '@/components/primitives/PfSelect'

type FilterKey = 'all' | 'progress' | 'action' | 'completed' | 'walked'
type SortKey = 'recent' | 'action' | 'longest'

interface FlowsTableProps {
  onNewRequest: () => void
}

export function FlowsTable({ onNewRequest }: FlowsTableProps) {
  const router = useRouter()
  const [filter, setFilter] = useState<FilterKey>('all')
  const [sort, setSort] = useState<SortKey>('recent')
  const [query, setQuery] = useState('')
  const [empty, setEmpty] = useState(false)

  const counts = {
    all: FLOWS.length,
    progress: FLOWS.filter((f) => !f.walked && f.phase !== 'done').length,
    action: FLOWS.filter((f) => f.needsAction).length,
    completed: FLOWS.filter((f) => f.phase === 'done').length,
    walked: FLOWS.filter((f) => f.walked).length,
  }

  const filtered = useMemo(() => {
    let rows = FLOWS.slice()
    if (filter === 'progress') rows = rows.filter((f) => !f.walked && f.phase !== 'done')
    if (filter === 'action') rows = rows.filter((f) => f.needsAction)
    if (filter === 'completed') rows = rows.filter((f) => f.phase === 'done')
    if (filter === 'walked') rows = rows.filter((f) => !!f.walked)
    if (query) {
      const q = query.toLowerCase()
      rows = rows.filter((f) =>
        (f.id + ' ' + f.summary + ' ' + f.requester).toLowerCase().includes(q)
      )
    }
    if (sort === 'action') rows.sort((a, b) => (b.needsAction ? 1 : 0) - (a.needsAction ? 1 : 0))
    if (sort === 'longest') rows.sort((a, b) => b.days - a.days)
    return rows
  }, [filter, sort, query])

  function openFlow(id: string) {
    router.push(`/flows/${id}`)
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
            <span className="kbd">⌘K</span>
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
            <button className="btn" onClick={() => setEmpty((e) => !e)}>
              [ {empty ? 'show data' : 'preview empty'} ]
            </button>
            <button className="btn accent" onClick={onNewRequest}>
              [ + new request ]
            </button>
          </div>
        </div>
      </div>

      {empty ? (
        <EmptyState onNewRequest={onNewRequest} />
      ) : filtered.length === 0 ? (
        <div className="empty" style={{ marginTop: 24 }}>
          <div className="ascii-mark">──── no matches ────</div>
          <div>No flows match this filter.</div>
          <div style={{ marginTop: 12 }}>
            <button
              className="btn"
              onClick={() => {
                setFilter('all')
                setQuery('')
              }}
            >
              [ clear filters ]
            </button>
          </div>
        </div>
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
                  <span className="ink">{f.id}</span>
                </td>
                <td>
                  <div>{f.summary}</div>
                  <div className="t-xs faint">
                    requested by {f.requester} · {f.opened}
                  </div>
                </td>
                <td>
                  <div className="row" style={{ gap: 10 }}>
                    <PhaseDots
                      phase={f.phase === 'walked' ? 'neg' : f.phase}
                      walked={f.walked}
                    />
                    <span className="t-xs muted upper">
                      {f.walked ? 'walked' : PHASES.find((p) => p.id === f.phase)?.label}
                    </span>
                  </div>
                </td>
                <td className="t-xs muted">{f.state}</td>
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
                  ) : f.phase === 'done' ? (
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
     │                         │
     │   no flows yet.         │
     │                         │
     │   start a new request   │
     │   and the agents take   │
     │   it from there.        │
     │                         │
     └─────────────────────────┘`}</pre>
      <div style={{ marginTop: 18 }} className="muted t-sm">
        Once you open a request, the RFQ agent collects vendor quotes, the negotiation agent counters in
        parallel,
        <br />
        and the platform escalates only what needs your judgment.
      </div>
      <div style={{ marginTop: 22 }}>
        <button className="btn accent" onClick={onNewRequest}>
          [ start a new request ]
        </button>
        <span style={{ marginLeft: 12 }} className="t-xs faint">
          or import from CSV · paste from email
        </span>
      </div>
    </div>
  )
}

'use client'
import React, { useState, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { VENDORS } from '@/lib/data'
import { FilterChip } from '@/components/primitives/FilterChip'
import { StatusPill } from '@/components/primitives/StatusPill'
import { PfSelect } from '@/components/primitives/PfSelect'
import { StateLabel } from './StateLabel'

type FilterKey = 'all' | 'unread' | 'escalated' | 'closed'

export function VendorsTable() {
  const router = useRouter()
  const [filter, setFilter] = useState<FilterKey>('all')
  const [query, setQuery] = useState('')
  const [groupBy, setGroupBy] = useState('state')

  const counts = {
    all: VENDORS.length,
    unread: VENDORS.filter((v) => v.unread > 0).length,
    escalated: VENDORS.filter(
      (v) => v.state === 'ESCALATED' || v.state.includes('DISPUTE')
    ).length,
    closed: VENDORS.filter(
      (v) => v.state === 'CLOSED' || v.state === 'WALKED_AWAY'
    ).length,
  }

  const rows = useMemo(() => {
    let r = VENDORS.slice()
    if (filter === 'unread') r = r.filter((v) => v.unread > 0)
    if (filter === 'escalated')
      r = r.filter((v) => v.state === 'ESCALATED' || v.state.includes('DISPUTE'))
    if (filter === 'closed')
      r = r.filter((v) => v.state === 'CLOSED' || v.state === 'WALKED_AWAY')
    if (query) {
      const q = query.toLowerCase()
      r = r.filter((v) => (v.id + v.name + v.pr).toLowerCase().includes(q))
    }
    return r
  }, [filter, query])

  return (
    <>
      <div className="toolbar">
        <div className="toolbar-inner">
          <div className="chips">
            <FilterChip active={filter === 'all'} onClick={() => setFilter('all')} count={counts.all}>
              ALL
            </FilterChip>
            <FilterChip
              active={filter === 'unread'}
              onClick={() => setFilter('unread')}
              count={counts.unread}
            >
              UNREAD
            </FilterChip>
            <FilterChip
              active={filter === 'escalated'}
              onClick={() => setFilter('escalated')}
              count={counts.escalated}
            >
              ESCALATED / DISPUTE
            </FilterChip>
            <FilterChip
              active={filter === 'closed'}
              onClick={() => setFilter('closed')}
              count={counts.closed}
            >
              CLOSED
            </FilterChip>
          </div>
          <div className="spacer" />
          <div className="search">
            <span className="br">/</span>
            <input
              placeholder="search vendor, id, PR…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <PfSelect value={groupBy} onChange={(e) => setGroupBy(e.target.value)}>
            <option value="state">group: state</option>
            <option value="vendor">group: vendor</option>
            <option value="date">group: date</option>
          </PfSelect>
        </div>
      </div>

      {rows.length === 0 ? (
        <div className="empty" style={{ marginTop: 24 }}>
          <pre className="ascii-mark">──── no vendor threads ────</pre>
          <div>
            Nothing matches that filter. Vendor threads are created when an RFQ goes out.
          </div>
        </div>
      ) : (
        <table className="table" style={{ marginTop: 4 }}>
          <thead>
            <tr>
              <th style={{ width: 110 }}>Vendor ID</th>
              <th>Vendor</th>
              <th style={{ width: 150 }}>Related PR</th>
              <th style={{ width: 200 }}>State</th>
              <th style={{ width: 90, textAlign: 'right' }}>Messages</th>
              <th style={{ width: 130 }}>Last activity</th>
              <th style={{ width: 80 }}></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((v) => (
              <tr
                key={v.id}
                className={v.unread > 0 ? 'action-row' : ''}
                onClick={() => router.push(`/vendors/${v.id}`)}
              >
                <td className="tnum">{v.id}</td>
                <td>
                  <div>{v.name}</div>
                  <div className="t-xs faint">
                    {v.country} · {v.tier}
                  </div>
                </td>
                <td className="tnum">
                  <a
                    onClick={(e) => {
                      e.stopPropagation()
                      router.push(`/flows/${v.pr}`)
                    }}
                  >
                    {v.pr}
                  </a>
                </td>
                <td>
                  <StateLabel s={v.state} />
                </td>
                <td className="tnum" style={{ textAlign: 'right' }}>
                  {v.msgs}
                </td>
                <td className="t-xs muted">{v.last}</td>
                <td>
                  {v.unread > 0 ? (
                    <StatusPill kind="go">{v.unread} new</StatusPill>
                  ) : (
                    <span className="t-xs faint">read</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div style={{ height: 80 }} />
    </>
  )
}

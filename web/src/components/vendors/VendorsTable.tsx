'use client'
import React, { forwardRef, useCallback, useImperativeHandle } from 'react'
import { useRouter } from 'next/navigation'
import { getVendorThreads } from '@/lib/api-client'
import type { Vendor } from '@/types'
import { useInfinitePagedList } from '@/hooks/useInfinitePagedList'
import { InfiniteScrollSentinel } from '@/components/primitives/InfiniteScrollSentinel'
import { StateLabel } from './StateLabel'

const PAGE_SIZE = 25

export interface VendorsTableHandle {
  refresh: () => void
}

export const VendorsTable = forwardRef<VendorsTableHandle>(function VendorsTable(
  _props,
  ref,
) {
  const router = useRouter()

  const fetcher = useCallback(
    ({ cursor }: { cursor?: string | null; filter: Record<string, never> }) =>
      getVendorThreads({ cursor: cursor ?? undefined, limit: PAGE_SIZE }),
    [],
  )

  const { items, loading, loadingMore, error, hasMore, loadMore, refresh } =
    useInfinitePagedList<Vendor, Record<string, never>>(fetcher, {})

  useImperativeHandle(ref, () => ({ refresh }), [refresh])

  if (loading) {
    return (
      <div className="empty" style={{ marginTop: 24 }}>
        <div className="thinking">loading vendor threads…</div>
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
    return (
      <div className="empty" style={{ marginTop: 24 }}>
        <pre className="ascii-mark">──── no vendor threads ────</pre>
        <div>No vendor threads yet. Threads appear when negotiation starts.</div>
      </div>
    )
  }

  return (
    <>
      <table className="table" style={{ marginTop: 4, tableLayout: 'fixed' }}>
        <colgroup>
          <col style={{ width: '12%' }} />
          <col style={{ width: '32%' }} />
          <col style={{ width: '20%' }} />
          <col style={{ width: '22%' }} />
          <col style={{ width: '14%' }} />
        </colgroup>
        <thead>
          <tr>
            <th>Vendor ID</th>
            <th>Vendor</th>
            <th>Related PR</th>
            <th>Status</th>
            <th>Last activity</th>
          </tr>
        </thead>
        <tbody>
          {items.map((v) => (
            <tr
              key={v.id}
              className={v.unread > 0 ? 'action-row' : ''}
              onClick={() => router.push(`/vendors/${v.id}`)}
            >
              <td
                className="tnum"
                title={v.vendorId ?? v.id}
                style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
              >
                {(v.vendorId ?? v.id).slice(0, 8)}
              </td>
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
                    router.push(`/flows/${v.workflowId ?? v.pr}`)
                  }}
                >
                  {v.pr}
                </a>
              </td>
              <td>
                <StateLabel s={v.state} />
              </td>
              <td className="t-xs muted">{v.last}</td>
            </tr>
          ))}
          {hasMore && (
            <tr>
              <td colSpan={5} style={{ padding: 0, border: 'none' }}>
                <InfiniteScrollSentinel
                  onVisible={loadMore}
                  disabled={loadingMore || !hasMore}
                />
              </td>
            </tr>
          )}
          {loadingMore && (
            <tr>
              <td colSpan={5} className="t-xs muted" style={{ textAlign: 'center', padding: 12 }}>
                loading more…
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <div style={{ height: 80 }} />
    </>
  )
})

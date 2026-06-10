'use client'
import React, { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { getVendorThreads } from '@/lib/api-client'
import type { Vendor } from '@/types'
import { StateLabel } from './StateLabel'

export function VendorsTable() {
  const router = useRouter()
  const [rows, setRows] = useState<Vendor[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setRows(await getVendorThreads())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load vendor threads')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (loading) {
    return (
      <div className="empty" style={{ marginTop: 24 }}>
        <div className="thinking">loading vendor threads…</div>
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
          <div className="spacer" />
          <button className="btn" onClick={load}>
            [ refresh ]
          </button>
        </div>
      </div>

      {rows.length === 0 ? (
        <div className="empty" style={{ marginTop: 24 }}>
          <pre className="ascii-mark">──── no vendor threads ────</pre>
          <div>No vendor threads yet. Threads appear when negotiation starts.</div>
        </div>
      ) : (
        <table className="table" style={{ marginTop: 4 }}>
          <thead>
            <tr>
              <th style={{ width: 110 }}>Vendor ID</th>
              <th>Vendor</th>
              <th style={{ width: 150 }}>Related PR</th>
              <th style={{ width: 200 }}>State</th>
              <th style={{ width: 130 }}>Last activity</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((v) => (
              <tr
                key={v.id}
                className={v.unread > 0 ? 'action-row' : ''}
                onClick={() => router.push(`/vendors/${v.id}`)}
              >
                <td className="tnum">{v.vendorId ?? v.id.slice(0, 8)}</td>
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
          </tbody>
        </table>
      )}

      <div style={{ height: 80 }} />
    </>
  )
}

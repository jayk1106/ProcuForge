'use client'
import React, { useCallback, useState } from 'react'
import { FlowsTableWrapper } from './FlowsTableWrapper'
import type { WorkflowRow } from '@/types/workflow'
import { AsciiRule } from '@/components/primitives/AsciiRule'

export default function FlowsPage() {
  const [summary, setSummary] = useState({ total: 0, needsAction: 0 })

  const handleLoaded = useCallback((rows: WorkflowRow[]) => {
    setSummary({
      total: rows.length,
      needsAction: rows.filter((f) => f.needsAction).length,
    })
  }, [])

  return (
    <div className="viewport">
      <div className="crumbs">
        <span className="here">Requests</span>
      </div>

      <header className="page-head">
        <div>
          <h1 className="page-title">Requests</h1>
          <div className="page-sub">
            All purchase requests across your org · {summary.total} total · {summary.needsAction}{' '}
            need action
          </div>
        </div>
      </header>

      <AsciiRule />

      <FlowsTableWrapper onLoaded={handleLoaded} />
    </div>
  )
}

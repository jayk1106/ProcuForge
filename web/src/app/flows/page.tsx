import React from 'react'
import { FLOWS } from '@/lib/data'
import { AsciiRule } from '@/components/primitives/AsciiRule'
import { FlowsTableWrapper } from './FlowsTableWrapper'

export default function FlowsPage() {
  const total = FLOWS.length
  const needsAction = FLOWS.filter((f) => f.needsAction).length

  return (
    <div className="viewport">
      <div className="crumbs">
        <span className="here">Flows</span>
      </div>

      <header className="page-head">
        <div>
          <h1 className="page-title">Flows</h1>
          <div className="page-sub">
            All purchase requests across your org · {total} total · {needsAction} need action
          </div>
        </div>
      </header>

      <AsciiRule />

      <FlowsTableWrapper />
    </div>
  )
}

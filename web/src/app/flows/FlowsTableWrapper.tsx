'use client'
import React, { useRef } from 'react'
import { FlowsTable, type FlowsTableHandle } from '@/components/flows/FlowsTable'
import { AsciiRule } from '@/components/primitives/AsciiRule'
import { usePRModalContext } from '@/components/layout/PRModalContext'

export function FlowsTableWrapper() {
  const { openPRModal } = usePRModalContext()
  const tableRef = useRef<FlowsTableHandle>(null)

  return (
    <>
      <header className="page-head row between">
        <div>
          <h1 className="page-title">Requests</h1>
          <div className="page-sub">All purchase requests across your org</div>
        </div>
        <button className="btn" onClick={() => tableRef.current?.refresh()}>
          [ refresh ]
        </button>
      </header>
      <AsciiRule />
      <FlowsTable ref={tableRef} onNewRequest={openPRModal} />
    </>
  )
}

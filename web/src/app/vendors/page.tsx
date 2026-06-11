'use client'
import React, { useRef } from 'react'
import { AsciiRule } from '@/components/primitives/AsciiRule'
import { VendorsTable, type VendorsTableHandle } from '@/components/vendors/VendorsTable'

export default function VendorsPage() {
  const tableRef = useRef<VendorsTableHandle>(null)

  return (
    <div className="viewport">
      <div className="crumbs">
        <span className="here">Vendors</span>
      </div>
      <header className="page-head row between">
        <div>
          <h1 className="page-title">Vendor conversations</h1>
          <div className="page-sub">
            All agent ↔ vendor communication, grouped by vendor entity
          </div>
        </div>
        <button className="btn" onClick={() => tableRef.current?.refresh()}>
          [ refresh ]
        </button>
      </header>
      <AsciiRule />
      <VendorsTable ref={tableRef} />
    </div>
  )
}

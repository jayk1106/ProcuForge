'use client'
import React from 'react'
import { AsciiRule } from '@/components/primitives/AsciiRule'
import { VendorsTable } from '@/components/vendors/VendorsTable'

export default function VendorsPage() {
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
      </header>
      <AsciiRule />
      <VendorsTable />
    </div>
  )
}

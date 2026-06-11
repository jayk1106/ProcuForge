'use client'
import React from 'react'
import { FlowsTableWrapper } from './FlowsTableWrapper'

export default function FlowsPage() {
  return (
    <div className="viewport">
      <div className="crumbs">
        <span className="here">Requests</span>
      </div>

      <FlowsTableWrapper />
    </div>
  )
}

'use client'

import { useState, useMemo } from 'react'
import type { WorkflowRow, WorkflowSummary, FilterTab } from '@/types/workflow'
import { FilterTabs } from './FilterTabs'
import { FlowRow } from './FlowRow'

interface FlowsTableProps {
  workflows: WorkflowRow[]
  summary: WorkflowSummary
}

const TABLE_HEADERS = [
  'PR ID',
  'PRODUCT',
  'PHASE',
  'CURRENT STATE',
  'VENDORS',
  'DAYS',
  'ACTION',
]

export function FlowsTable({ workflows, summary }: FlowsTableProps) {
  const [activeTab, setActiveTab] = useState<FilterTab>('ALL')
  const [search, setSearch] = useState('')

  const filtered = useMemo(() => {
    let rows = workflows

    if (activeTab === 'IN_PROGRESS') {
      rows = rows.filter(
        (r) => r.phase !== 'DONE' && r.currentState !== 'WALKED_AWAY'
      )
    } else if (activeTab === 'NEEDS_ACTION') {
      rows = rows.filter((r) => r.needsAction)
    } else if (activeTab === 'COMPLETED') {
      rows = rows.filter((r) => r.phase === 'DONE')
    } else if (activeTab === 'WALKED_AWAY') {
      rows = rows.filter((r) => r.currentState === 'WALKED_AWAY')
    }

    if (search.trim()) {
      const q = search.trim().toLowerCase()
      rows = rows.filter(
        (r) =>
          r.id.toLowerCase().includes(q) ||
          r.product.toLowerCase().includes(q) ||
          r.requestedBy.toLowerCase().includes(q)
      )
    }

    return rows
  }, [workflows, activeTab, search])

  return (
    <div className="flex flex-col gap-4">
      <FilterTabs
        activeTab={activeTab}
        summary={summary}
        onTabChange={setActiveTab}
      />

      {/* Search + sort bar */}
      <div className="flex items-center justify-between gap-4">
        <div
          className="flex items-center gap-2 border px-3 py-1.5 text-xs"
          style={{ borderColor: '#CBBF9F', minWidth: 280 }}
        >
          <span style={{ color: '#7A6E5C' }}>/</span>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="search id, product, r..."
            className="flex-1 bg-transparent text-xs outline-none placeholder:text-[#7A6E5C]"
            style={{ color: '#1C1816', fontFamily: 'inherit' }}
          />
          <span style={{ color: '#7A6E5C' }}>⌘K</span>
        </div>
        <button
          className="cursor-pointer border px-3 py-1.5 text-xs"
          style={{
            borderColor: '#CBBF9F',
            color: '#1C1816',
            background: 'transparent',
          }}
        >
          [ most recent ▼ ]
        </button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr
              className="border-b"
              style={{ borderBottomColor: '#CBBF9F' }}
            >
              {TABLE_HEADERS.map((header) => (
                <th
                  key={header}
                  className="pb-2 pl-4 pr-4 text-[10px] font-bold tracking-widest"
                  style={{ color: '#7A6E5C' }}
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td
                  colSpan={TABLE_HEADERS.length}
                  className="py-12 text-center text-xs"
                  style={{ color: '#7A6E5C' }}
                >
                  No requests found.
                </td>
              </tr>
            ) : (
              filtered.map((row) => <FlowRow key={row.id} row={row} />)
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

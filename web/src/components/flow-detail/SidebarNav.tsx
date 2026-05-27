'use client'
import React from 'react'

interface SidebarNavProps {
  active: string
  onPick: (id: string) => void
  isEmpty?: boolean
}

interface NavSection {
  id: string
  n: string
  label: string
  sub: string
  pending?: boolean
}

const sections: NavSection[] = [
  { id: 'spec', n: '1.0', label: 'Specification',  sub: 'validated' },
  { id: 'rfq',  n: '2.0', label: 'RFQ',            sub: '4 of 7 responded' },
  { id: 'neg',  n: '3.0', label: 'Negotiation',    sub: '4 vendors · round 2' },
  { id: 'po',   n: '4.0', label: 'Purchase order', sub: 'pending', pending: true },
  { id: 'grn',  n: '5.0', label: 'Goods receipt',  sub: 'pending', pending: true },
  { id: 'inv',  n: '6.0', label: 'Invoice match',  sub: 'pending', pending: true },
  { id: 'done', n: '7.0', label: 'Completion',     sub: 'pending', pending: true },
]

export function SidebarNav({ active, onPick, isEmpty }: SidebarNavProps) {
  return (
    <aside className="side">
      <h4>Phases</h4>
      {sections.map((s) => {
        const isDone = !isEmpty && !s.pending
        return (
          <a
            key={s.id}
            className={`${active === s.id ? 'active' : ''} ${isDone ? 'done' : ''}`}
            onClick={() => onPick(s.id)}
          >
            <span>
              <span className="faint">{s.n}</span>&nbsp; {s.label}
            </span>
            <span className="sm">{s.sub}</span>
          </a>
        )
      })}
      <h4 style={{ marginTop: 28 }}>Documents</h4>
      <a>
        <span>Original request</span>
        <span className="sm">PDF</span>
      </a>
      <a>
        <span>Spec validation</span>
        <span className="sm">md</span>
      </a>
      <a>
        <span>RFQ broadcast</span>
        <span className="sm">log</span>
      </a>
      <a>
        <span>Audit trail</span>
        <span className="sm">json</span>
      </a>
    </aside>
  )
}

'use client'
import React, { useState } from 'react'
import { PfSelect } from '@/components/primitives/PfSelect'
import type { ActivityItem } from '@/types'

interface ActivityRailProps {
  items: ActivityItem[]
}

const AGENTS = [
  'all',
  'NegotiationAgent',
  'EscalationAgent',
  'RFQAgent',
  'SpecAgent',
  'IntakeAgent',
]

export function ActivityRail({ items }: ActivityRailProps) {
  const [filter, setFilter] = useState('all')
  const filtered = filter === 'all' ? items : items.filter((i) => i.ag === filter)

  return (
    <aside className="activity">
      <h4>Activity log</h4>
      <PfSelect value={filter} onChange={(e) => setFilter(e.target.value)}>
        {AGENTS.map((a) => (
          <option key={a} value={a}>
            {a}
          </option>
        ))}
      </PfSelect>
      <div style={{ marginTop: 14 }}>
        {filtered.map((it, i) => (
          <div key={i} className="act-item">
            <div className="row between">
              <span className="ts">today · {it.ts}</span>
              <span className="ag">{it.ag}</span>
            </div>
            <div className="det">{it.det}</div>
          </div>
        ))}
        {filtered.length === 0 && (
          <div className="muted t-sm" style={{ paddingTop: 8 }}>
            No events for this agent.
          </div>
        )}
      </div>
    </aside>
  )
}

import React from 'react'
import { PHASES } from '@/lib/data'

interface TimelineProps {
  phase: string
  durations: Record<string, string | null>
  empty?: boolean
}

export function Timeline({ phase, durations, empty }: TimelineProps) {
  const curIdx = PHASES.findIndex((p) => p.id === phase)
  return (
    <div className="timeline">
      {PHASES.map((p, i) => {
        let cls = 'step'
        if (empty) {
          if (i === 0) cls += ' active'
        } else {
          if (i < curIdx) cls += ' done'
          else if (i === curIdx) cls += ' active'
        }
        const dur = durations[p.id]
        return (
          <div key={p.id} className={cls}>
            <div className="row" style={{ gap: 6 }}>
              <span className="marker" />
              <span className="label">
                {i + 1} · {p.label}
              </span>
            </div>
            <div className="dur">
              {empty && i === 0
                ? 'starting…'
                : dur
                ? `· ${dur}`
                : i === curIdx && !empty
                ? 'in progress'
                : '— pending'}
            </div>
          </div>
        )
      })}
    </div>
  )
}

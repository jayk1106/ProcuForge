import React from 'react'
import { PHASES } from '@/lib/data'
import type { PhaseStatus } from '@/types'

interface TimelineProps {
  phase: string
  durations: Record<string, string | null>
  phaseStatus?: Record<string, PhaseStatus>
  empty?: boolean
}

function statusToClass(status: PhaseStatus | undefined): string {
  if (status === 'done') return 'done'
  if (status === 'in_progress') return 'active'
  if (status === 'walked') return 'fail'
  return ''
}

function statusToLabel(status: PhaseStatus | undefined, duration: string | null | undefined): string {
  if (duration) return `· ${duration}`
  if (status === 'done') return '· done'
  if (status === 'in_progress') return 'in progress'
  if (status === 'walked') return 'walked away'
  return '— pending'
}

export function Timeline({ phase, durations, phaseStatus, empty }: TimelineProps) {
  const curIdx = PHASES.findIndex((p) => p.id === phase)
  const allDone = !!phaseStatus && PHASES.every((p) => phaseStatus[p.id] === 'done')
  return (
    <div className={`timeline${allDone ? ' complete' : ''}`}>
      {PHASES.map((p, i) => {
        let cls = 'step'
        let status: PhaseStatus | undefined
        if (empty) {
          if (i === 0) cls += ' active'
          status = i === 0 ? 'in_progress' : 'pending'
        } else if (phaseStatus && phaseStatus[p.id]) {
          status = phaseStatus[p.id]
          const extra = statusToClass(status)
          if (extra) cls += ` ${extra}`
        } else {
          if (i < curIdx) {
            cls += ' done'
            status = 'done'
          } else if (i === curIdx) {
            cls += ' active'
            status = 'in_progress'
          } else {
            status = 'pending'
          }
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
              {empty && i === 0 ? 'starting…' : statusToLabel(status, dur)}
            </div>
          </div>
        )
      })}
    </div>
  )
}

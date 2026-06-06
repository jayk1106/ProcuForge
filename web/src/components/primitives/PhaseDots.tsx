import React from 'react'
import { PHASES } from '@/lib/data'

interface PhaseDotsProps {
  phase: string
  walked?: boolean
}

export function PhaseDots({ phase, walked }: PhaseDotsProps) {
  const phaseIds = PHASES.map((p) => p.id)
  const cur = phaseIds.indexOf(phase)
  return (
    <span className="phase-dots" aria-label={`phase ${phase}`}>
      {phaseIds.map((p, i) => {
        let cls = 'dot'
        if (walked && i >= cur) cls += ' fail'
        else if (i < cur) cls += ' done'
        else if (i === cur) cls += ' active'
        return <span key={p} className={cls} title={p.toUpperCase()} />
      })}
    </span>
  )
}

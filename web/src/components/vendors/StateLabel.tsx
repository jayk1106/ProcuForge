import React from 'react'
import { StatusPill } from '@/components/primitives/StatusPill'

function pillKindForStatus(status: string): 'ok' | 'warn' | 'err' | 'idle' {
  const s = status.toUpperCase()
  if (s === 'COMPLETE') return 'ok'
  if (s.includes('WALKED') || s.includes('REJECTED') || s.includes('ESCALATED')) return 'err'
  if (
    s.includes('PROGRESS') ||
    s.includes('NEGOTIATION') ||
    s.includes('PO_') ||
    s.includes('GRN') ||
    s.includes('INVOICE')
  )
    return 'warn'
  return 'idle'
}

interface StateLabelProps {
  s: string
}

export function StateLabel({ s }: StateLabelProps) {
  return <StatusPill kind={pillKindForStatus(s)}>{s}</StatusPill>
}

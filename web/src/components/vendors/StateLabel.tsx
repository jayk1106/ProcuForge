import React from 'react'
import { StatusPill } from '@/components/primitives/StatusPill'

const stateMap: Record<string, 'ok' | 'warn' | 'err' | 'go' | 'idle'> = {
  NEGOTIATING: 'go',
  QUOTING: 'go',
  AWAITING_PO_ACK: 'go',
  ESCALATED: 'warn',
  DELIVERY_DISPUTE: 'warn',
  INVOICE_DISPUTE: 'warn',
  OFFER_LOCKED: 'ok',
  CLOSED: 'idle',
  COMPLETE: 'idle',
  COMPLETED: 'idle',
  PROCESS_COMPLETE: 'idle',
  WALKED_AWAY: 'err',
}

const CLOSED_STATES = new Set([
  'CLOSED',
  'COMPLETE',
  'COMPLETED',
  'PROCESS_COMPLETE',
])

interface StateLabelProps {
  s: string
}

export function StateLabel({ s }: StateLabelProps) {
  const kind = stateMap[s] || 'idle'
  const label = CLOSED_STATES.has(s) ? 'closed' : s.replace(/_/g, ' ').toLowerCase()
  return <StatusPill kind={kind}>{label}</StatusPill>
}

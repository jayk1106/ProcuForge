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
  WALKED_AWAY: 'err',
}

interface StateLabelProps {
  s: string
}

export function StateLabel({ s }: StateLabelProps) {
  const kind = stateMap[s] || 'idle'
  return (
    <StatusPill kind={kind}>
      {s.replace(/_/g, ' ').toLowerCase()}
    </StatusPill>
  )
}

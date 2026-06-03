'use client'
import React from 'react'
import type { ActiveFlow, PhaseStatus } from '@/types'

interface SidebarNavProps {
  active: string
  onPick: (id: string) => void
  isEmpty?: boolean
  flow?: ActiveFlow | null
}

interface NavSection {
  id: string
  n: string
  label: string
  sub: string
  status: PhaseStatus
}

function statusLabel(status: PhaseStatus): string {
  if (status === 'done') return 'done'
  if (status === 'in_progress') return 'in progress'
  if (status === 'walked') return 'walked away'
  return 'pending'
}

function buildSections(flow: ActiveFlow | null | undefined, isEmpty: boolean): NavSection[] {
  const ps: Record<string, PhaseStatus> = flow?.phaseStatus ?? {
    rfq: 'pending',
    neg: 'pending',
    po: 'pending',
    grn: 'pending',
    inv: 'pending',
    done: 'pending',
  }

  const specSub =
    flow?.specDone === false || isEmpty ? 'pending' : 'validated'

  const vendorCount = flow?.vendors.length ?? 0
  let rfqSub = statusLabel(ps.rfq)
  if (vendorCount > 0 && ps.rfq !== 'walked') {
    rfqSub = `${vendorCount} vendor${vendorCount === 1 ? '' : 's'} responded`
  }

  let negSub = statusLabel(ps.neg)
  if (vendorCount > 0) {
    const rounds = flow?.vendors
      .map((v) => parseInt(v.round.replace(/[^0-9]/g, ''), 10))
      .filter((n) => !Number.isNaN(n))
    const maxRound = rounds && rounds.length ? Math.max(...rounds) : null
    if (ps.neg === 'in_progress') {
      negSub = maxRound != null
        ? `${vendorCount} vendors · round ${maxRound}`
        : `${vendorCount} vendors`
    } else if (ps.neg === 'done') {
      negSub = 'completed'
    } else if (ps.neg === 'walked') {
      negSub = 'no vendor available'
    }
  }

  const winner = flow?.vendors.find((v) => v.status === 'WON')
  const awardSub = winner ? winner.name : ps.neg === 'walked' ? 'none' : 'pending'
  const awardStatus: PhaseStatus = winner ? 'done' : ps.neg === 'walked' ? 'walked' : 'pending'

  const poSub = flow?.po ? statusLabel(ps.po === 'pending' ? 'in_progress' : ps.po) : statusLabel(ps.po)
  const poFinal = flow?.po ? (ps.po === 'pending' ? 'issued' : statusLabel(ps.po)) : poSub

  const grnSub = flow?.grn ? statusLabel(ps.grn === 'pending' ? 'done' : ps.grn) : statusLabel(ps.grn)
  const grnFinal = flow?.grn ? (ps.grn === 'pending' ? 'received' : grnSub) : grnSub

  const invSub = flow?.invoice ? statusLabel(ps.inv === 'pending' ? 'done' : ps.inv) : statusLabel(ps.inv)
  const invFinal = flow?.invoice ? (ps.inv === 'pending' ? 'matched' : invSub) : invSub

  const doneSub = ps.done === 'done' ? 'complete' : statusLabel(ps.done)

  return [
    { id: 'spec', n: '1.0', label: 'Specification', sub: specSub, status: specSub === 'validated' ? 'done' : 'pending' },
    { id: 'rfq', n: '2.0', label: 'RFQ', sub: rfqSub, status: ps.rfq },
    { id: 'neg', n: '3.0', label: 'Negotiation', sub: negSub, status: ps.neg },
    { id: 'award', n: '3.5', label: 'Selected vendor', sub: awardSub, status: awardStatus },
    { id: 'po', n: '4.0', label: 'Purchase order', sub: poFinal, status: ps.po },
    { id: 'grn', n: '5.0', label: 'Goods receipt', sub: grnFinal, status: ps.grn },
    { id: 'inv', n: '6.0', label: 'Invoice match', sub: invFinal, status: ps.inv },
    { id: 'done', n: '7.0', label: 'Completion', sub: doneSub, status: ps.done },
  ]
}

export function SidebarNav({ active, onPick, isEmpty, flow }: SidebarNavProps) {
  const sections = buildSections(flow, !!isEmpty)
  return (
    <aside className="side">
      <h4>Phases</h4>
      {sections.map((s) => {
        const isDone = s.status === 'done'
        const isActive = active === s.id
        const isWalked = s.status === 'walked'
        const cls = [
          isActive ? 'active' : '',
          isDone ? 'done' : '',
          isWalked ? 'walked' : '',
        ]
          .filter(Boolean)
          .join(' ')
        return (
          <a key={s.id} className={cls} onClick={() => onPick(s.id)}>
            <span>
              <span className="faint">{s.n}</span>&nbsp; {s.label}
            </span>
            <span className="sm">{s.sub}</span>
          </a>
        )
      })}
    </aside>
  )
}

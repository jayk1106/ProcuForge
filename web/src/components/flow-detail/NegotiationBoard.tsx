'use client'
import React from 'react'
import { useRouter } from 'next/navigation'
import { StatusPill } from '@/components/primitives/StatusPill'
import { fmtMoney, fmtDelta } from '@/lib/format'
import type { ActiveVendor } from '@/types'

interface NegotiationBoardProps {
  vendors: ActiveVendor[]
  onResolveEscalation?: () => void
  resolvingEscalation?: boolean
}

function NegotiationStatus({ v }: { v: ActiveVendor }) {
  if (v.status === 'WON') return <StatusPill kind="ok">won</StatusPill>
  if (v.status === 'LOST') return <StatusPill kind="idle">lost</StatusPill>
  if (v.status === 'WALKED_AWAY') return <StatusPill kind="err">walked away</StatusPill>
  if (v.escalated) return <StatusPill kind="warn">escalated</StatusPill>
  return <StatusPill kind="go">negotiating</StatusPill>
}

export function NegotiationBoard({
  vendors,
  onResolveEscalation,
  resolvingEscalation = false,
}: NegotiationBoardProps) {
  const router = useRouter()

  function openConvo(v: ActiveVendor) {
    const target = v.rfqId ?? v.id
    router.push(`/vendors/${target}`)
  }

  return (
    <div className="neg-board">
      {vendors.map((v) => (
        <article
          key={v.id}
          className={`neg-col ${v.status === 'WON' ? 'won' : ''} ${
            v.status === 'WALKED_AWAY' ? 'walked' : ''
          } ${v.status === 'LOST' ? 'lost' : ''}`}
        >
          <header>
            <div className="row between">
              <div>
                <div className="vname">{v.name}</div>
                <div className="vid">
                  {v.id} · {v.country}
                </div>
              </div>
              <NegotiationStatus v={v} />
            </div>
          </header>
          <div className="neg-summary">
            <div className="k">round</div>
            <div className="v">{v.round}</div>
            <div className="k">latest offer</div>
            <div className="v">{v.latest != null ? fmtMoney(v.latest) : '—'}</div>
            <div className="k">vs target</div>
            <div
              className={`v ${v.delta != null && v.delta > 0 ? 'delta-up' : v.delta != null && v.delta < 0 ? 'delta-down' : ''}`}
            >
              {fmtDelta(v.delta)}
            </div>
            <div className="k">lead time</div>
            <div className="v">{v.lead}</div>
            <div className="k">moq</div>
            <div className="v">{v.moq}</div>
          </div>
          <div className="neg-thread">
            <div className="t-xs upper muted" style={{ marginBottom: 4 }}>
              Thread
            </div>
            {v.thread.map((t, i) => (
              <div key={i} className="turn">
                <div>
                  <div className={`who ${t.who === 'them' ? 'them' : ''}`}>
                    {t.who === 'them' ? '← them' : '→ us'}
                  </div>
                </div>
                <div>
                  <div className="what">{t.what}</div>
                  <div className="meta">{t.meta}</div>
                </div>
              </div>
            ))}
          </div>
          <div
            style={{
              padding: '10px 14px',
              borderTop: '1px solid var(--rule)',
              display: 'flex',
              gap: 6,
            }}
          >
            <button className="btn tiny" onClick={() => openConvo(v)}>
              [ open convo ]
            </button>
            {v.status === 'NEGOTIATING' && !v.escalated && (
              <button className="btn tiny">[ accept ]</button>
            )}
            {v.escalated && onResolveEscalation && (
              <button
                className="btn tiny accent"
                disabled={resolvingEscalation}
                onClick={onResolveEscalation}
              >
                [ {resolvingEscalation ? 'resolving…' : 'resolve escalation'} ]
              </button>
            )}
          </div>
        </article>
      ))}
    </div>
  )
}

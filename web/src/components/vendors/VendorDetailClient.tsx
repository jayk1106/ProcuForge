'use client'
import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import { VENDOR_CONVO } from '@/lib/data'
import { AsciiRule } from '@/components/primitives/AsciiRule'
import { Bracketed } from '@/components/primitives/Bracketed'
import { FilterChip } from '@/components/primitives/FilterChip'
import { StatusPill } from '@/components/primitives/StatusPill'

export function VendorDetailClient() {
  const router = useRouter()
  const convo = VENDOR_CONVO
  const [showRaw, setShowRaw] = useState<Record<number, boolean>>({})

  function toggle(i: number) {
    setShowRaw((s) => ({ ...s, [i]: !s[i] }))
  }

  return (
    <div className="viewport">
      <div className="crumbs">
        <a onClick={() => router.push('/vendors')} style={{ cursor: 'pointer' }}>
          Vendors
        </a>
        <span className="sep">/</span>
        <span className="here">{convo.vendor.id}</span>
        <span className="sep">·</span>
        <a
          onClick={() => router.push(`/flows/${convo.pr}`)}
          style={{ cursor: 'pointer' }}
        >
          {convo.pr}
        </a>
      </div>

      <header className="page-head">
        <div className="row between" style={{ alignItems: 'flex-start' }}>
          <div>
            <div className="t-xs upper muted">Vendor conversation</div>
            <h1 className="page-title">
              <span className="tnum">{convo.vendor.id}</span>
              <span className="muted" style={{ fontWeight: 400 }}>
                {' '}
                ·{' '}
              </span>
              {convo.vendor.name}
            </h1>
            <div className="page-sub">
              {convo.vendor.country} · {convo.vendor.tier} · MSSA {convo.vendor.mssa} · for{' '}
              <a
                className="ink"
                onClick={() => router.push(`/flows/${convo.pr}`)}
                style={{
                  textDecoration: 'underline',
                  textDecorationColor: 'var(--rule-strong)',
                  cursor: 'pointer',
                }}
              >
                {convo.pr}
              </a>{' '}
              · outcome <span className="accent">{convo.outcome}</span>
            </div>
          </div>
          <div className="row" style={{ gap: 6 }}>
            <button className="btn">[ download .json ]</button>
            <button className="btn">[ replay timeline ]</button>
          </div>
        </div>
      </header>

      <AsciiRule />

      <div className="row" style={{ gap: 14, padding: '14px 0', flexWrap: 'wrap' }}>
        <span className="t-xs upper muted">filter</span>
        <FilterChip active>ALL EVENTS</FilterChip>
        <FilterChip>OFFERS ONLY</FilterChip>
        <FilterChip>STATE TRANSITIONS</FilterChip>
        <FilterChip>ERRORS · 1</FilterChip>
        <div className="spacer" />
        <span className="t-xs muted">
          {convo.messages.length} messages · 1 STATE_MISMATCH_ERROR · 1 escalation
        </span>
      </div>

      <div style={{ marginTop: 6 }}>
        {convo.messages.map((m, i) => (
          <article
            key={i}
            className={`msg-card${m.locked ? ' locked' : ''}${m.error ? ' error' : ''}`}
          >
            <div className="head">
              <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
                <span className="from">{m.from}</span>
                <span className="arrow">→</span>
                <span className="to">{m.to}</span>
                <span className="tag">{m.type.replace(/_/g, ' ')}</span>
                <span className="tag upper">{m.phase}</span>
                {m.locked && <span className="locked-tag">⌾ LOCKED TERMS</span>}
                {m.error && <StatusPill kind="err">state mismatch</StatusPill>}
              </div>
              <span className="ts">{m.ts}</span>
            </div>
            <div className="payload">
              {Object.entries(m.payload).map(([k, v]) => (
                <React.Fragment key={k}>
                  <div className="k">{k}</div>
                  <div className="v">
                    {typeof v === 'number' ? v.toLocaleString() : String(v)}
                  </div>
                </React.Fragment>
              ))}
            </div>
            <div className="raw" onClick={() => toggle(i)}>
              <Bracketed>{showRaw[i] ? 'hide raw' : 'view raw'}</Bracketed>
            </div>
            {showRaw[i] && (
              <pre className="raw-block">
                {JSON.stringify(
                  {
                    ts: m.ts,
                    from: m.from,
                    to: m.to,
                    type: m.type,
                    phase: m.phase,
                    ...(m.locked ? { locked: true } : {}),
                    ...(m.error ? { error: true } : {}),
                    payload: m.payload,
                  },
                  null,
                  2
                )}
              </pre>
            )}
          </article>
        ))}
      </div>

      <div className="box box-pad" style={{ marginTop: 24, background: 'var(--bg-tint)' }}>
        <div className="t-xs upper muted">Conversation summary</div>
        <div className="t-sm" style={{ marginTop: 6 }}>
          Vendor responded within SLA, conceded $13,448 across two rounds, but countered with
          NET-15 terms outside our policy floor of NET-30.{' '}
          <strong>Awaiting buyer decision</strong> — accept terms, reject and walk, or renegotiate.
          Timeout in 18h 42m.
        </div>
      </div>

      <div style={{ height: 80 }} />
    </div>
  )
}

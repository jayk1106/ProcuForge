'use client'
import React, { useState, useRef, useEffect } from 'react'
import { SUGGESTED } from '@/lib/data'

interface ChatMessage {
  who: 'user' | 'assistant'
  body: React.ReactNode
}

interface ChatPanelProps {
  open: boolean
  onClose: () => void
}

function assistantReply(q: string): React.ReactNode {
  const lower = q.toLowerCase()
  if (lower.includes('v-0421') || lower.includes('apex') || lower.includes('holding')) {
    return (
      <>
        <strong>V-0421 (Apex Servo)</strong> isn&apos;t holding price — they&apos;re holding <em>terms</em>.
        Their last counter at <span className="tnum">$184,960</span> is{' '}
        <span className="accent">$1,440 below target</span>,
        but they&apos;re requesting <span className="tnum">NET-15</span> instead of our{' '}
        <span className="tnum">NET-30</span> floor.
        <br /><br />
        PolicyAgent flagged this as a <span className="tnum">STATE_MISMATCH_ERROR</span>{' '}
        <span className="chat-cite">[see Round 2 with V-0421]</span> and routed it to you for decision.
        <br /><br />
        Recommended path: counter at NET-30 with a <span className="tnum">1.5%</span> early-pay discount as concession.
        Historical accept rate for this vendor on similar swaps: <span className="tnum">73%</span>.
      </>
    )
  }
  if (lower.includes('block') || lower.includes('what')) {
    return (
      <>
        Two things are blocking completion of this PR:
        <br /><br />
        <strong>1.</strong> <span className="tnum">V-0421</span> escalation — buyer decision needed on NET-15 terms{' '}
        <span className="chat-cite">[see escalation #ESC-1138]</span>.
        <br />
        <strong>2.</strong> <span className="tnum">V-0218</span> still in round 3 negotiation —{' '}
        <span className="tnum">$188,220</span> is <span className="tnum">+$1,820</span> over target.
        <br /><br />
        <span className="tnum">V-0719</span> has already locked at <span className="tnum">$182,640</span> and is your
        current best option. You can approve them now and let the others time out at 18h 42m, or wait for V-0218&apos;s
        final.
      </>
    )
  }
  if (lower.includes('strategy')) {
    return (
      <>
        Current strategy: <strong>parallel best-of-N with target anchoring</strong>.
        <br /><br />
        — Anchor: <span className="tnum">$186,400</span> (catalog target, -10% from baseline)
        <br />— Concession ladder: 4% → 2% → 1% across rounds
        <br />— Walk-away: any vendor &gt; +5% over target after R3
        <br />— Tie-break: lead time &lt; 18d, then warranty
        <br /><br />
        Resulting in 1 walked, 1 locked, 2 still active.{' '}
        <span className="chat-cite">[see RFQ § 2.0]</span>
      </>
    )
  }
  if (lower.includes('summar')) {
    return (
      <>
        <strong>PR-2026-0418</strong> · 24 × CNC spindle motors · target{' '}
        <span className="tnum">$186,400</span>
        <br /><br />
        7 vendors invited → 4 quoted → 1 disqualified (MOQ) → 3 negotiated. Best confirmed price:{' '}
        <span className="tnum">$182,640</span> from V-0719 (Yamashita), 16d lead, 24m warranty included.
        Total savings vs anchor: <span className="tnum">$3,760 (2.0%)</span>.
        <br /><br />
        <strong>Open items:</strong> 1 buyer decision (V-0421 terms), 1 vendor still negotiating (V-0218).
        Need-by date <span className="tnum">2026-05-22</span> — currently{' '}
        <span className="accent">on track</span>.
      </>
    )
  }
  return (
    <>
      I can answer that based on the audit log. The most recent agent action was{' '}
      <span className="chat-cite">[NegotiationAgent · 14:32]</span> sending a counter to V-0218.
      <br /><br />
      Could you narrow your question — vendor, round, or phase?
    </>
  )
}

export function ChatPanel({ open, onClose }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      who: 'assistant',
      body: (
        <>
          Hi — I have full context on <span className="tnum">PR-2026-0418</span>. Ask anything about the
          negotiation, escalations, or vendor history. I can cite specific events.
        </>
      ),
    },
  ])
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const bodyRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight
    }
  }, [messages, thinking])

  if (!open) return null

  function ask(q: string) {
    setMessages((m) => [...m, { who: 'user', body: q }])
    setInput('')
    setThinking(true)
    setTimeout(() => {
      setThinking(false)
      setMessages((m) => [...m, { who: 'assistant', body: assistantReply(q) }])
    }, 1100)
  }

  return (
    <div className="chat-overlay" onClick={onClose}>
      <aside className="chat-panel" onClick={(e) => e.stopPropagation()}>
        <div className="chat-head">
          <div>
            <div className="t-xs upper muted">Assistant · scoped to current PR</div>
            <div style={{ fontSize: 'var(--t-base)', fontWeight: 600, marginTop: 2 }}>
              <span className="tnum">PR-2026-0418</span>
              <span className="muted"> · </span>
              <span style={{ fontWeight: 400 }}>CNC spindle motors × 24</span>
            </div>
          </div>
          <button className="btn ghost" onClick={onClose}>
            [ × close ]
          </button>
        </div>

        <div className="chat-body" ref={bodyRef}>
          {messages.length === 1 && (
            <div>
              <div className="t-xs upper muted" style={{ marginBottom: 8 }}>
                Try asking
              </div>
              {SUGGESTED.map((s) => (
                <button key={s} className="chat-suggestion" onClick={() => ask(s)}>
                  › {s}
                </button>
              ))}
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={`chat-msg ${m.who}`}>
              <div className="who">{m.who === 'user' ? 'm.okafor' : 'procuforge assistant'}</div>
              <div className="body">{m.body}</div>
            </div>
          ))}

          {thinking && (
            <div className="chat-msg assistant">
              <div className="who">procuforge assistant</div>
              <div className="body">
                <span className="thinking">analyzing negotiation history</span>
              </div>
            </div>
          )}
        </div>

        <div className="chat-input">
          <div className="ctl">
            <span className="br">[</span>
            <input
              placeholder="Ask about this request…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && input.trim()) ask(input.trim())
              }}
              autoFocus
            />
            <span className="br">]</span>
          </div>
          <button
            className="btn primary"
            disabled={!input.trim()}
            onClick={() => input.trim() && ask(input.trim())}
          >
            [ send ]
          </button>
        </div>
      </aside>
    </div>
  )
}

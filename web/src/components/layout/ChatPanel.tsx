'use client'
import React, { useEffect, useMemo, useRef, useState } from 'react'
import { SUGGESTED } from '@/lib/data'
import { askWorkflow, type ChatTurn, UnauthorizedError } from '@/lib/api-client'

interface ChatMessage {
  who: 'user' | 'assistant'
  body: string
  error?: boolean
}

interface ChatPanelProps {
  open: boolean
  onClose: () => void
  workflowId: string | null
}

const HISTORY_TURNS_SENT = 6

function greeting(workflowId: string | null): ChatMessage {
  if (!workflowId) {
    return {
      who: 'assistant',
      body:
        'Open a purchase request from the Flows page and click "ask about this PR" to start a scoped chat.',
    }
  }
  const short = workflowId.length > 12 ? workflowId.slice(0, 8) : workflowId
  return {
    who: 'assistant',
    body: `Hi — I have context on workflow ${short}. Ask about vendors, status, approvals, or documents.`,
  }
}

export function ChatPanel({ open, onClose, workflowId }: ChatPanelProps) {
  const initial = useMemo(() => [greeting(workflowId)], [workflowId])
  const [messages, setMessages] = useState<ChatMessage[]>(initial)
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const bodyRef = useRef<HTMLDivElement>(null)

  // Reset history each time the panel is reopened or the scoped workflow changes,
  // so a previous PR's chat doesn't leak into the next one.
  useEffect(() => {
    if (open) {
      setMessages([greeting(workflowId)])
      setInput('')
      setThinking(false)
    }
  }, [open, workflowId])

  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight
    }
  }, [messages, thinking])

  if (!open) return null

  const canSend = !!workflowId && !thinking

  async function ask(q: string) {
    if (!workflowId) return
    const userMsg: ChatMessage = { who: 'user', body: q }
    // Snapshot the in-panel transcript BEFORE appending the new question so
    // we only send prior turns to the server.
    const history: ChatTurn[] = messages
      .filter((m) => !m.error)
      .slice(-HISTORY_TURNS_SENT)
      .map((m) => ({ role: m.who, text: m.body }))

    setMessages((m) => [...m, userMsg])
    setInput('')
    setThinking(true)

    try {
      const { answer } = await askWorkflow(workflowId, q, history)
      setMessages((m) => [...m, { who: 'assistant', body: answer }])
    } catch (err) {
      if (err instanceof UnauthorizedError) return // apiFetch already redirected
      const detail = err instanceof Error ? err.message : 'request failed'
      setMessages((m) => [
        ...m,
        { who: 'assistant', body: `[ error · ${detail} ]`, error: true },
      ])
    } finally {
      setThinking(false)
    }
  }

  const headerLabel = workflowId
    ? workflowId.length > 16
      ? `${workflowId.slice(0, 8)}…${workflowId.slice(-4)}`
      : workflowId
    : 'no PR scoped'

  return (
    <div className="chat-overlay" onClick={onClose}>
      <aside className="chat-panel" onClick={(e) => e.stopPropagation()}>
        <div className="chat-head">
          <div>
            <div className="t-xs upper muted">Assistant · scoped to current PR</div>
            <div style={{ fontSize: 'var(--t-base)', fontWeight: 600, marginTop: 2 }}>
              <span className="tnum">{headerLabel}</span>
            </div>
          </div>
          <button className="btn ghost" onClick={onClose}>
            [ × close ]
          </button>
        </div>

        <div className="chat-body" ref={bodyRef}>
          {workflowId && messages.length === 1 && (
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
              <div className="who">
                {m.who === 'user' ? 'you' : 'procuforge assistant'}
              </div>
              <div className="body" style={{ whiteSpace: 'pre-wrap' }}>
                {m.body}
              </div>
            </div>
          ))}

          {thinking && (
            <div className="chat-msg assistant">
              <div className="who">procuforge assistant</div>
              <div className="body">
                <span className="thinking">reading workflow snapshot</span>
              </div>
            </div>
          )}
        </div>

        <div className="chat-input">
          <div className="ctl">
            <span className="br">[</span>
            <input
              placeholder={
                workflowId ? 'Ask about this request…' : 'Open a PR to enable chat'
              }
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && input.trim() && canSend) ask(input.trim())
              }}
              disabled={!workflowId}
              autoFocus
            />
            <span className="br">]</span>
          </div>
          <button
            className="btn primary"
            disabled={!input.trim() || !canSend}
            onClick={() => input.trim() && canSend && ask(input.trim())}
          >
            [ send ]
          </button>
        </div>
      </aside>
    </div>
  )
}

'use client'
import React, { useState, useCallback, useEffect } from 'react'

interface StateDebugPanelProps {
  label: string
  fetchState: () => Promise<unknown>
}

function syntaxHighlight(json: string): string {
  const escaped = json
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  return escaped.replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
    (match) => {
      if (/^"/.test(match)) {
        if (/:$/.test(match)) {
          return `<span style="color:var(--muted)">${match}</span>`
        }
        return `<span style="color:var(--ink-2)">${match}</span>`
      }
      if (/true|false/.test(match)) {
        return `<span style="color:var(--ok)">${match}</span>`
      }
      if (/null/.test(match)) {
        return `<span style="color:var(--warn)">${match}</span>`
      }
      return `<span style="color:var(--accent-ink)">${match}</span>`
    },
  )
}

export function StateDebugPanel({ label, fetchState }: StateDebugPanelProps) {
  const [open, setOpen] = useState(false)
  const [state, setState] = useState<unknown>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fetchedAt, setFetchedAt] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchState()
      setState(data)
      setFetchedAt(new Date().toISOString())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch state')
    } finally {
      setLoading(false)
    }
  }, [fetchState])

  function openModal() {
    setOpen(true)
    if (state === null && !loading) refresh()
  }

  function closeModal() {
    setOpen(false)
  }

  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') closeModal()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  function copy() {
    if (state === null) return
    navigator.clipboard.writeText(JSON.stringify(state, null, 2)).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    })
  }

  const jsonText = state !== null ? JSON.stringify(state, null, 2) : ''
  const highlighted = jsonText ? syntaxHighlight(jsonText) : ''

  return (
    <>
      {/* Fixed tab button on right edge */}
      <button
        onClick={openModal}
        style={{
          position: 'fixed',
          right: 0,
          top: '42%',
          transform: 'translateY(-50%)',
          writingMode: 'vertical-rl',
          textOrientation: 'mixed',
          background: 'var(--bg-sunk)',
          border: '1px solid var(--rule-strong)',
          borderRight: 'none',
          borderRadius: '3px 0 0 3px',
          padding: '14px 7px',
          fontSize: 'var(--t-xs)',
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          color: 'var(--muted)',
          cursor: 'pointer',
          zIndex: 45,
          fontFamily: 'var(--mono)',
          lineHeight: 1,
          whiteSpace: 'nowrap',
        }}
        onMouseEnter={(e) => {
          ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--ink)'
          ;(e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-tint)'
        }}
        onMouseLeave={(e) => {
          ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--muted)'
          ;(e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-sunk)'
        }}
      >
        dbg · state
      </button>

      {/* Slide-in modal from right */}
      {open && (
        <>
          {/* backdrop */}
          <div
            onClick={closeModal}
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(20,20,20,0.22)',
              zIndex: 60,
            }}
          />

          {/* panel */}
          <div
            style={{
              position: 'fixed',
              top: 0,
              right: 0,
              bottom: 0,
              width: 700,
              maxWidth: '96vw',
              background: 'var(--bg)',
              borderLeft: '1px solid var(--rule-strong)',
              display: 'flex',
              flexDirection: 'column',
              zIndex: 61,
              animation: 'slideIn 200ms ease-out',
              fontFamily: 'var(--mono)',
            }}
          >
            {/* header */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '11px 16px',
                borderBottom: '1px solid var(--rule)',
                background: 'var(--bg-sunk)',
                flexShrink: 0,
              }}
            >
              <span
                style={{
                  flex: 1,
                  fontSize: 'var(--t-xs)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  color: 'var(--muted)',
                  fontWeight: 500,
                }}
              >
                {label}
              </span>

              {fetchedAt && (
                <span
                  style={{
                    fontSize: 'var(--t-xs)',
                    color: 'var(--faint)',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {fetchedAt.replace('T', ' ').slice(0, 19)} UTC
                </span>
              )}

              <button
                className="btn tiny"
                onClick={refresh}
                disabled={loading}
              >
                {loading ? 'loading…' : '[ refresh ]'}
              </button>

              <button
                className="btn tiny"
                onClick={copy}
                disabled={state === null}
              >
                {copied ? '[ copied! ]' : '[ copy json ]'}
              </button>

              <button className="btn tiny" onClick={closeModal}>
                [ × ]
              </button>
            </div>

            {/* meta bar */}
            {!loading && state !== null && (
              <div
                style={{
                  display: 'flex',
                  gap: 20,
                  padding: '5px 16px',
                  borderBottom: '1px solid var(--rule)',
                  fontSize: 'var(--t-xs)',
                  color: 'var(--faint)',
                  flexShrink: 0,
                  background: 'var(--bg)',
                }}
              >
                {typeof state === 'object' && state !== null && (
                  <span>{Object.keys(state as object).length} top-level keys</span>
                )}
                <span>{(jsonText.length / 1024).toFixed(1)} KB</span>
              </div>
            )}

            {/* scrollable body */}
            <div style={{ flex: 1, overflow: 'auto', padding: '14px 16px' }}>
              {loading && !state && (
                <div className="thinking" style={{ fontSize: 'var(--t-sm)' }}>
                  fetching state…
                </div>
              )}

              {error && (
                <div style={{ color: 'var(--err)', fontSize: 'var(--t-xs)' }}>
                  {error}
                </div>
              )}

              {!error && state !== null && (
                <pre
                  style={{
                    margin: 0,
                    fontSize: 'var(--t-xs)',
                    lineHeight: 1.6,
                    whiteSpace: 'pre',
                    color: 'var(--ink)',
                    background: 'transparent',
                  }}
                  dangerouslySetInnerHTML={{ __html: highlighted }}
                />
              )}
            </div>
          </div>
        </>
      )}
    </>
  )
}

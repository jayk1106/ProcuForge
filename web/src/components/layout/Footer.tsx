import React from 'react'

export function Footer() {
  return (
    <footer
      className="viewport"
      style={{
        padding: '24px 32px 32px',
        color: 'var(--faint)',
        fontSize: 'var(--t-xs)',
        borderTop: '1px solid var(--rule)',
        marginTop: 32,
      }}
    >
      <div className="row between">
        <div>
          procuforge<span className="accent">~</span> · build 2026.05.09 · all agent actions are logged immutably.
        </div>
        <div className="row" style={{ gap: 12 }}>
          <a>docs</a>
          <span className="sep-dot">·</span>
          <a>policy</a>
          <span className="sep-dot">·</span>
          <a>status</a>
        </div>
      </div>
    </footer>
  )
}

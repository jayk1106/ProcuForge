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
      <div>
        procuforge<span className="accent">~</span>
      </div>
    </footer>
  )
}

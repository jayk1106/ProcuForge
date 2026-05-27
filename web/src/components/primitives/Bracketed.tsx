import React from 'react'

interface BracketedProps {
  children: React.ReactNode
}

export function Bracketed({ children }: BracketedProps) {
  return (
    <span>
      <span className="faint">[</span>
      <span style={{ padding: '0 6px' }}>{children}</span>
      <span className="faint">]</span>
    </span>
  )
}

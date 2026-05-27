import React from 'react'

interface StatusPillProps {
  kind?: 'ok' | 'warn' | 'err' | 'go' | 'idle'
  bare?: boolean
  children: React.ReactNode
}

export function StatusPill({ kind = 'idle', bare, children }: StatusPillProps) {
  return (
    <span className={`pill ${kind}${bare ? ' bare' : ''}`}>
      {children}
    </span>
  )
}

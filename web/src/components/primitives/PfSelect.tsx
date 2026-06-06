'use client'
import React from 'react'

interface PfSelectProps {
  value: string
  onChange: (e: React.ChangeEvent<HTMLSelectElement>) => void
  children: React.ReactNode
}

export function PfSelect({ value, onChange, children }: PfSelectProps) {
  return (
    <div className="ctl" style={{ height: 36, paddingRight: 8 }}>
      <span className="br">[</span>
      <select
        value={value}
        onChange={onChange}
        style={{
          flex: 1,
          border: 0,
          outline: 0,
          background: 'transparent',
          appearance: 'none',
          padding: '6px 0',
          fontFamily: 'inherit',
          fontSize: 'inherit',
          color: 'inherit',
        }}
      >
        {children}
      </select>
      <span className="br">▼</span>
    </div>
  )
}

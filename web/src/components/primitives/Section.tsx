'use client'
import React, { useState } from 'react'

interface SectionProps {
  title: string
  num?: string | number
  status?: React.ReactNode
  defaultOpen?: boolean
  pending?: boolean
  right?: React.ReactNode
  children: React.ReactNode
}

export function Section({
  title,
  num,
  status,
  defaultOpen = true,
  pending = false,
  right,
  children,
}: SectionProps) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section className={`sec${pending ? ' pending' : ''}`}>
      <header onClick={() => setOpen((o) => !o)} className={open ? '' : 'no-border'}>
        <h3>
          {num != null && <span className="num">§ {num}</span>}
          <span>{title}</span>
          {status}
        </h3>
        <div className="right">
          {right}
          <span className="muted t-xs">{open ? '[ − ]' : '[ + ]'}</span>
        </div>
      </header>
      {open && <div className="body">{children}</div>}
    </section>
  )
}

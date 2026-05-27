import React from 'react'

interface FilterChipProps {
  active?: boolean
  onClick?: () => void
  count?: number
  children: React.ReactNode
}

export function FilterChip({ active, onClick, count, children }: FilterChipProps) {
  return (
    <button className={`chip${active ? ' active' : ''}`} onClick={onClick}>
      {children}
      {count != null && <span className="count">· {count}</span>}
    </button>
  )
}

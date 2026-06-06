import React from 'react'

interface AsciiRuleProps {
  char?: string
  dotted?: boolean
}

export function AsciiRule({ char = '─', dotted = false }: AsciiRuleProps) {
  return (
    <div className="rule-ascii" aria-hidden="true">
      {Array(200).fill(dotted ? '·' : char).join('')}
    </div>
  )
}

import React from 'react'

interface FieldProps {
  label: React.ReactNode
  required?: boolean
  optional?: boolean
  hint?: string
  prefix?: string
  suffix?: string
  children: React.ReactNode
}

export function Field({
  label,
  required,
  optional,
  hint,
  prefix = '[',
  suffix = ']',
  children,
}: FieldProps) {
  return (
    <div className="field">
      <label>
        {label}
        {required && <span className="req"> *</span>}
        {optional && <span className="opt">&nbsp;&nbsp;(optional)</span>}
      </label>
      <div className="ctl">
        <span className="br">{prefix}</span>
        {children}
        <span className="br">{suffix}</span>
      </div>
      {hint && <span className="hint">{hint}</span>}
    </div>
  )
}

import React from 'react'
import { AsciiRule } from '@/components/primitives/AsciiRule'

export default function SettingsPage() {
  return (
    <div className="viewport">
      <div className="crumbs">
        <span className="here">Settings</span>
      </div>
      <header className="page-head">
        <h1 className="page-title">Settings</h1>
        <div className="page-sub">Agent policies, approval thresholds, integrations.</div>
      </header>
      <AsciiRule />
      <div className="empty" style={{ marginTop: 24 }}>
        <pre className="ascii-mark">──── settings ────</pre>
        <div>Agent policies, integrations, and team access live here.</div>
        <div className="t-xs faint" style={{ marginTop: 8 }}>
          (out of scope for this design pass)
        </div>
      </div>
    </div>
  )
}

import React from 'react'

export function ActionBanner() {
  return (
    <div className="banner" role="alert">
      <div className="bar" />
      <div className="body">
        <span className="lbl">action required</span>
        <div>
          <div className="what">
            Approve final selection — V-0719 (Yamashita Precision Co.) at $182,640, 16d lead.
          </div>
          <div className="ctx">
            2 vendors still open · 1 escalation pending policy review · timeout in 18h 42m
          </div>
        </div>
        <div className="acts">
          <button className="btn ghost">[ review vendors ]</button>
          <button className="btn accent lg">[ approve &amp; issue PO → ]</button>
        </div>
      </div>
    </div>
  )
}

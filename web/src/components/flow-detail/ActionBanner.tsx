import React from 'react'

interface ActionBannerProps {
  actionLabel?: string | null
  onApprove?: () => void
  approving?: boolean
}

export function ActionBanner({ actionLabel, onApprove, approving }: ActionBannerProps) {
  return (
    <div className="banner" role="alert">
      <div className="bar" />
      <div className="body">
        <span className="lbl">action required</span>
        <div>
          <div className="what">{actionLabel ?? 'Your approval is required to continue.'}</div>
        </div>
        <div className="acts">
          <button className="btn accent lg" onClick={onApprove} disabled={approving}>
            [ {approving ? 'approving…' : 'approve & issue PO →'} ]
          </button>
        </div>
      </div>
    </div>
  )
}

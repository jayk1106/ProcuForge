import type { WorkflowRow } from '@/types/workflow'
import { PhaseDots } from './PhaseDots'

interface FlowRowProps {
  row: WorkflowRow
}

function ActionCell({ row }: { row: WorkflowRow }) {
  if (row.needsAction && row.actionLabel) {
    return (
      <div className="flex flex-col gap-1.5">
        <span className="text-xs font-bold" style={{ color: '#8B3A0F' }}>
          {row.actionLabel}
        </span>
        <button
          className="cursor-pointer border px-2.5 py-1 text-xs font-bold text-white transition-colors"
          style={{
            backgroundColor: '#8B3A0F',
            borderColor: '#8B3A0F',
          }}
          onMouseEnter={(e) => {
            ;(e.currentTarget as HTMLButtonElement).style.backgroundColor = '#5F240C'
          }}
          onMouseLeave={(e) => {
            ;(e.currentTarget as HTMLButtonElement).style.backgroundColor = '#8B3A0F'
          }}
        >
          [ resolve → ]
        </button>
      </div>
    )
  }

  if (row.phase === 'DONE') {
    return (
      <span className="text-xs font-bold" style={{ color: '#1A5C30' }}>
        • COMPLETE
      </span>
    )
  }

  return (
    <span className="text-xs" style={{ color: '#7A6E5C' }}>
      — agents working —
    </span>
  )
}

export function FlowRow({ row }: FlowRowProps) {
  return (
    <tr
      className="border-b"
      style={{
        borderBottomColor: '#CBBF9F',
        borderLeftWidth: row.needsAction ? '3px' : '3px',
        borderLeftStyle: 'solid',
        borderLeftColor: row.needsAction ? '#8B3A0F' : 'transparent',
      }}
    >
      {/* PR ID */}
      <td className="py-3 pl-4 pr-4 text-xs font-bold" style={{ color: '#1C1816' }}>
        {row.id}
      </td>

      {/* Product */}
      <td className="py-3 pr-6" style={{ maxWidth: 260 }}>
        <div className="text-xs font-bold leading-snug" style={{ color: '#1C1816' }}>
          {row.product}
        </div>
        <div className="mt-0.5 text-[10px]" style={{ color: '#7A6E5C' }}>
          requested by {row.requestedBy} · {row.requestedAt}
        </div>
      </td>

      {/* Phase dots */}
      <td className="py-3 pr-6">
        <PhaseDots phase={row.phase} />
      </td>

      {/* Current state */}
      <td className="py-3 pr-6">
        <span
          className="text-[10px] font-bold tracking-widest"
          style={{ color: '#7A6E5C' }}
        >
          {row.currentState}
        </span>
      </td>

      {/* Vendors */}
      <td className="py-3 pr-6 text-center">
        <span className="text-xs font-bold" style={{ color: '#1C1816' }}>
          {row.vendors}
        </span>
      </td>

      {/* Days */}
      <td className="py-3 pr-6 text-center">
        <span className="text-xs font-bold" style={{ color: '#1C1816' }}>
          {row.days}d
        </span>
      </td>

      {/* Action */}
      <td className="py-3 pr-4">
        <ActionCell row={row} />
      </td>
    </tr>
  )
}

import { mockWorkflows, mockSummary } from '@/lib/mock-data'
import { FlowsTable } from '@/components/flows/FlowsTable'

export default function FlowsPage() {
  return (
    <div className="mx-auto max-w-[1400px] px-6 py-8">
      {/* Breadcrumb */}
      <div className="mb-2 text-xs" style={{ color: '#7A6E5C' }}>
        Flows
      </div>

      {/* Header row */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-4xl font-bold" style={{ color: '#1C1816' }}>
            Flows
          </h1>
          <p className="mt-1 text-xs" style={{ color: '#7A6E5C' }}>
            All purchase requests across your org · {mockSummary.total} total ·{' '}
            {mockSummary.needsAction} need action
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            className="cursor-pointer border px-3 py-1.5 text-xs"
            style={{
              borderColor: '#CBBF9F',
              color: '#1C1816',
              background: 'transparent',
            }}
          >
            [ preview empty ]
          </button>
          <button
            className="cursor-pointer border px-3 py-1.5 text-xs font-bold text-white transition-colors"
            style={{
              backgroundColor: '#7C3010',
              borderColor: '#7C3010',
            }}
            onMouseEnter={undefined}
          >
            [ + new request ]
          </button>
        </div>
      </div>

      {/* Table */}
      <FlowsTable workflows={mockWorkflows} summary={mockSummary} />
    </div>
  )
}

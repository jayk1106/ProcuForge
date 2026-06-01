export type PhaseLabel = 'RFQ' | 'NEG' | 'PO' | 'GRN' | 'INV' | 'DONE'
export type FilterTab = 'ALL' | 'IN_PROGRESS' | 'NEEDS_ACTION' | 'COMPLETED' | 'WALKED_AWAY'

export interface WorkflowRow {
  id: string
  requestId?: string
  product: string
  requestedBy: string
  requestedAt: string
  phase: PhaseLabel
  currentState: string
  vendors: number
  days: number
  needsAction: boolean
  actionLabel: string | null
  walked?: boolean
}

export interface WorkflowSummary {
  total: number
  inProgress: number
  needsAction: number
  completed: number
  walkedAway: number
}

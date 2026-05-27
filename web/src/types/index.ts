export interface Phase {
  id: string
  label: string
  long: string
}

export type PhaseId = 'rfq' | 'neg' | 'po' | 'grn' | 'inv' | 'done' | 'walked'

export interface Flow {
  id: string
  summary: string
  requester: string
  opened: string
  days: number
  phase: PhaseId
  state: string
  vendors: number
  target: number
  needsAction: boolean
  actionLabel?: string
  note?: string
  walked?: boolean
}

export interface VendorThread {
  who: 'them' | 'us'
  what: string
  meta: string
}

export interface ActiveVendor {
  id: string
  name: string
  country: string
  round: string
  state: string
  status: 'NEGOTIATING' | 'WON' | 'LOST' | 'WALKED_AWAY'
  latest: number | null
  delta: number | null
  moq: number
  lead: string
  escalated?: boolean
  thread: VendorThread[]
}

export interface ActivityItem {
  ts: string
  ag: string
  det: string
}

export interface ActiveFlow {
  id: string
  title: string
  requester: string
  costCenter: string
  opened: string
  target: number
  needBy: string
  spec: string
  phaseDurations: Record<string, string | null>
  currentPhase: PhaseId
  vendors: ActiveVendor[]
  activity: ActivityItem[]
}

export interface VendorConvoMessage {
  ts: string
  from: string
  to: string
  type: string
  phase: string
  locked?: boolean
  error?: boolean
  payload: Record<string, string | number>
}

export interface VendorConvo {
  vendor: {
    id: string
    name: string
    country: string
    tier: string
    mssa: string
  }
  pr: string
  outcome: string
  messages: VendorConvoMessage[]
}

export interface Vendor {
  id: string
  name: string
  country: string
  tier: string
  pr: string
  last: string
  state: string
  unread: number
  msgs: number
}

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
  rfqId?: string
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

export type PhaseStatus = 'pending' | 'in_progress' | 'done' | 'walked'

export interface VendorRelationSummary {
  preferredVendor: boolean
  relationshipStatus: string
  relationshipStrength: number | null
  averageDeliveryDelayDays: number | null
  qualityScore: number | null
  riskLevel: string | null
  usuallyOffersDiscount: boolean | null
  averageDiscountPercent: number | null
}

export interface DiscoveredVendor {
  offerId: string
  vendorId: string
  name: string
  country: string
  sku: string
  unit: string
  unitPrice: number | null
  currency: string
  leadTimeDays: number | null
  contracted: boolean
  availabilityStatus: string
  minimumOrderQty?: number
  currencyMatchesRequest?: boolean
  vendorRelation?: VendorRelationSummary | null
}

export interface ActiveFlow {
  id: string
  requestId?: string
  title: string
  requester: string
  costCenter: string
  opened: string
  target: number
  needBy: string
  spec: string
  prStatus?: string
  phaseDurations: Record<string, string | null>
  phaseStatus?: Record<string, PhaseStatus>
  specDone?: boolean
  currentPhase: PhaseId
  needsAction?: boolean
  actionLabel?: string | null
  discoveredVendors?: DiscoveredVendor[]
  vendors: ActiveVendor[]
  activity: ActivityItem[]
  po?: Record<string, unknown> | null
  grn?: Record<string, unknown> | null
  invoice?: Record<string, unknown> | null
  selectedVendor?: Record<string, unknown> | null
  approvalRequired?: boolean
  approvedSteps?: ApprovalStep[]
  pendingApproval?: PendingApproval | null
  escalationContext?: EscalationContext | null
}

export interface EscalationContext {
  tier: 'notify_only' | 'full'
  source: string
  reason: string
  triggerStatus?: string
  phase?: string
  vendorId?: string | null
  rfqId?: string | null
  triggeredAt?: string
  recommendedAction?: string | null
}

export type ApprovalStep = 'po' | 'grn' | 'completion'

export interface PendingApproval {
  step: ApprovalStep
  reason: string
  requested_at?: string
}

export interface VendorConvoMessage {
  ts: string
  from: string
  to: string
  type: string
  phase: string
  locked?: boolean
  error?: boolean
  payload: Record<string, unknown>
  highlight?: string
  round?: number | null
}

export interface VendorThreadSummary {
  status: string
  quotedPrice?: number | null
  acceptedPrice?: number | null
  latestOfferPrice?: number | null
  lastSellingPrice?: number | null
  currency: string
  poNumber?: string | null
  grnNumber?: string | null
  invoiceNumber?: string | null
  expectedDelivery?: string | null
  deliveredOn?: string | null
}

export interface VendorConvo {
  vendor: {
    id: string
    name: string
    country: string
    tier: string
    mssa: string
  }
  product?: {
    id?: string
    name?: string
    sku?: string
    brand?: string
    type?: string
  }
  pr: string
  workflowId?: string
  rfqId?: string
  outcome: string
  summary?: VendorThreadSummary
  messages: VendorConvoMessage[]
}

export interface Vendor {
  id: string
  vendorId?: string
  workflowId?: string
  name: string
  country: string
  tier: string
  pr: string
  last: string
  state: string
  unread: number
  msgs: number
}

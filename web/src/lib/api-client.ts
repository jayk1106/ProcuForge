import type { ProductOption } from '@/types/product'
import type { WorkflowRow } from '@/types/workflow'
import type { ActiveFlow, Vendor, VendorConvo } from '@/types'
import type {
  LoginPayload,
  LoginResponse,
  MeResponse,
  WsTicketResponse,
} from '@/types/auth'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export class UnauthorizedError extends Error {
  constructor(message = 'unauthenticated') {
    super(message)
    this.name = 'UnauthorizedError'
  }
}

interface FetchOptions {
  // When false, a 401 will not redirect to /login (used by the login page
  // itself so it can render an inline error instead of looping).
  redirectOn401?: boolean
}

async function apiFetch<T>(
  path: string,
  init?: RequestInit,
  opts: FetchOptions = {},
): Promise<T> {
  const { redirectOn401 = true } = opts
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  })

  if (res.status === 401) {
    if (redirectOn401 && typeof window !== 'undefined') {
      const next = encodeURIComponent(
        window.location.pathname + window.location.search,
      )
      window.location.href = `/login?next=${next}`
    }
    throw new UnauthorizedError()
  }

  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`API error ${res.status}: ${body || res.statusText}`)
  }

  if (res.status === 204) {
    return undefined as T
  }
  return res.json() as Promise<T>
}

export async function searchProducts(q = '', limit = 20): Promise<ProductOption[]> {
  const params = new URLSearchParams()
  if (q.trim()) params.set('q', q.trim())
  params.set('limit', String(limit))
  const query = params.toString()
  return apiFetch<ProductOption[]>(`/api/v1/products${query ? `?${query}` : ''}`)
}

export async function getWorkflows(): Promise<WorkflowRow[]> {
  return apiFetch<WorkflowRow[]>('/api/v1/workflow/list')
}

export async function getWorkflowDetail(id: string): Promise<ActiveFlow> {
  return apiFetch<ActiveFlow>(`/api/v1/workflow/${id}`)
}

export interface StartWorkflowPayload {
  product_id: string
  quantity: number
  required_by: string
  delivery_location: {
    address: string
    city: string
    state: string
    country: string
    pincode: string
  }
  urgency: 'low' | 'normal' | 'high' | 'emergency'
  budget_ceiling: number
  currency: string
  purpose?: string
  requester_id?: string
  organization_id?: string
  buyer_notes?: string[]
}

export interface StartWorkflowResult {
  workflow_id: string
  session_id: string
  status: string
  started_at: string
}

export async function startWorkflow(
  payload: StartWorkflowPayload
): Promise<StartWorkflowResult> {
  return apiFetch<StartWorkflowResult>('/api/v1/workflow/start', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function approveWorkflow(id: string): Promise<{ workflow_id: string; status: string }> {
  return apiFetch<{ workflow_id: string; status: string }>(
    `/api/v1/workflow/${id}/approve`,
    { method: 'POST' }
  )
}

export async function getWorkflowState(id: string): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>(`/api/v1/workflow/${id}/state`)
}

export async function getVendorThreads(): Promise<Vendor[]> {
  return apiFetch<Vendor[]>('/api/v1/vendor-threads')
}

export async function getVendorThread(rfqId: string): Promise<VendorConvo> {
  return apiFetch<VendorConvo>(`/api/v1/vendor-threads/${rfqId}`)
}

export interface ThreadActionResponse {
  rfq_id: string
  workflow_id: string
  vendor_id: string
  status: string
  applied_at: string
}

export async function getVendorThreadState(rfqId: string): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>(`/api/v1/vendor-threads/${rfqId}/state`)
}

export async function escalateVendorThread(
  rfqId: string,
  reason?: string
): Promise<ThreadActionResponse> {
  return apiFetch<ThreadActionResponse>(
    `/api/v1/vendor-threads/${rfqId}/escalate`,
    {
      method: 'POST',
      body: JSON.stringify({ reason: reason ?? null }),
    }
  )
}

export async function walkAwayVendorThread(
  rfqId: string,
  reason?: string
): Promise<ThreadActionResponse> {
  return apiFetch<ThreadActionResponse>(
    `/api/v1/vendor-threads/${rfqId}/walk-away`,
    {
      method: 'POST',
      body: JSON.stringify({ reason: reason ?? null }),
    }
  )
}

export async function login(payload: LoginPayload): Promise<LoginResponse> {
  return apiFetch<LoginResponse>(
    '/api/v1/auth/login',
    { method: 'POST', body: JSON.stringify(payload) },
    { redirectOn401: false },
  )
}

export async function logout(): Promise<void> {
  return apiFetch<void>(
    '/api/v1/auth/logout',
    { method: 'POST' },
    { redirectOn401: false },
  )
}

export async function getMe(): Promise<MeResponse> {
  return apiFetch<MeResponse>(
    '/api/v1/auth/me',
    undefined,
    { redirectOn401: false },
  )
}

export async function getWsTicket(): Promise<WsTicketResponse> {
  return apiFetch<WsTicketResponse>(
    '/api/v1/auth/ws-ticket',
    { method: 'POST' },
  )
}

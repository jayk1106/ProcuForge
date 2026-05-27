import type { WorkflowRow, WorkflowSummary } from '@/types/workflow'
import { mockWorkflows, mockSummary } from './mock-data'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  })
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export async function getWorkflows(): Promise<WorkflowRow[]> {
  try {
    return await apiFetch<WorkflowRow[]>('/api/workflows')
  } catch {
    return mockWorkflows
  }
}

export async function getWorkflow(id: string): Promise<WorkflowRow> {
  try {
    return await apiFetch<WorkflowRow>(`/api/workflows/${id}`)
  } catch {
    const found = mockWorkflows.find((w) => w.id === id)
    if (!found) throw new Error(`Workflow ${id} not found`)
    return found
  }
}

export interface StartWorkflowPayload {
  productId: string
  quantity: number
  requestedBy: string
}

export interface StartWorkflowResult {
  sessionId: string
  status: string
}

export async function startWorkflow(
  payload: StartWorkflowPayload
): Promise<StartWorkflowResult> {
  try {
    return await apiFetch<StartWorkflowResult>('/api/workflows', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  } catch {
    return {
      sessionId: `mock-${Date.now()}`,
      status: 'INITIATED',
    }
  }
}

export async function approveWorkflow(id: string): Promise<{ ok: boolean }> {
  try {
    return await apiFetch<{ ok: boolean }>(`/api/workflows/${id}/approve`, {
      method: 'POST',
    })
  } catch {
    return { ok: true }
  }
}

export { mockSummary }
export type { WorkflowSummary }

import { api } from './http'

export function fetchAgentRunStatus(runId: string) {
  return api<{ status?: string }>(`/api/v1/agent/runs/${encodeURIComponent(runId)}`)
}

export function fetchAgentSessionSummary(sessionId: string) {
  return api<{ question_count: number; summary: string; recent_questions: string[] }>(`/api/v1/agent/sessions/${encodeURIComponent(sessionId)}/summary`)
}

export function fetchAgentStations<T>() { return api<T[]>('/api/v1/stations') }
export function fetchWorkOrders<T>() { return api<T[]>('/api/v1/work-orders') }
export function createWorkOrderDraft<T>(body: unknown) { return api<T>('/api/v1/work-orders/draft', { method: 'POST', body: JSON.stringify(body) }) }
export function submitAgentReview<T>(body: unknown) { return api<T>('/api/v1/reviews', { method: 'POST', body: JSON.stringify(body) }) }
export function updateWorkOrderStatus<T>(id: string, status: string) { return api<T>(`/api/v1/work-orders/${encodeURIComponent(id)}/status`, { method: 'PATCH', body: JSON.stringify({ status }) }) }
export function updateWorkOrder<T>(id: string, body: unknown) { return api<T>(`/api/v1/work-orders/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body) }) }

export function decideAgentRun(runId: string, decision: 'approve' | 'reject', reason: string) {
  return api<{ status?: string }>(`/api/v1/agent/runs/${encodeURIComponent(runId)}/decision`, {
    method: 'POST',
    body: JSON.stringify({ decision, reason }),
  })
}

export function openAgentResumeStream(runId: string) {
  const headers = new Headers()
  const token = localStorage.getItem('access_token')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  return fetch(`/api/v1/agent/runs/${encodeURIComponent(runId)}/resume-stream`, { method: 'POST', headers })
}

export function openAgentStream(body: { message: string; station_id: string | null; session_id: string; require_approval?: boolean }, signal: AbortSignal) {
  const headers = new Headers({ 'Content-Type': 'application/json' })
  const token = localStorage.getItem('access_token')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  return fetch('/api/v1/chat/stream', { method: 'POST', headers, body: JSON.stringify(body), signal })
}

export function cancelAgentRun(runId: string) {
  return fetch(`/api/v1/agent/runs/${encodeURIComponent(runId)}/cancel`, { method: 'POST' })
}

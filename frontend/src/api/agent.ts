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

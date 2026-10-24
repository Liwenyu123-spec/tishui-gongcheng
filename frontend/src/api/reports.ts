import { api } from './http'

export function fetchReports<T>() { return api<T[]>('/api/v1/reports') }
export function fetchReport<T>(id: string) { return api<T>(`/api/v1/reports/${encodeURIComponent(id)}`) }
export function generateReport<T>(body: unknown) { return api<T>('/api/v1/reports/generate', { method: 'POST', body: JSON.stringify(body) }) }
export function saveReport<T>(id: string, body: unknown) { return api<T>(`/api/v1/reports/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body) }) }
export function updateReportStatus<T>(id: string, status: string) { return api<T>(`/api/v1/reports/${encodeURIComponent(id)}/status`, { method: 'PATCH', body: JSON.stringify({ status }) }) }

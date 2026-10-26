import { api } from './http'
export function fetchRagStatus<T>() { return api<T>('/api/v1/knowledge/rag/status') }
export function diagnoseRag<T>(body: unknown) { return api<T>('/api/v1/knowledge/rag/debug', { method: 'POST', body: JSON.stringify(body) }) }
export function askRag<T>(body: unknown) { return api<T>('/api/v1/knowledge/rag/ask', { method: 'POST', body: JSON.stringify(body) }) }

import { api } from './http'

export interface KnowledgeAuditEvent {
  action?: string
  detail?: string
  created_at?: string
  actor?: string
}

export function fetchKnowledgeHistory(documentId: string) {
  return api<KnowledgeAuditEvent[]>(`/api/v1/knowledge/${encodeURIComponent(documentId)}/history`)
}

export function updateKnowledgeStatus(documentId: string, status: string) {
  return api<{ status: string }>(`/api/v1/knowledge/${encodeURIComponent(documentId)}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  })
}

export function deleteKnowledgeDocument(documentId: string) {
  return api<{ success: boolean }>(`/api/v1/knowledge/${encodeURIComponent(documentId)}`, { method: 'DELETE' })
}

export function fetchKnowledgeDocuments<T>() {
  return api<T[]>('/api/v1/knowledge')
}

export function searchKnowledgeDocuments<T>(keyword: string) {
  return api<T>(`/api/v1/knowledge/search?q=${encodeURIComponent(keyword)}`)
}

export function importKnowledgeDocument<T>(body: unknown) {
  return api<T>('/api/v1/knowledge/import', { method: 'POST', body: JSON.stringify(body) })
}

export function compareKnowledgeDocument<T>(documentId: string) {
  return api<T>(`/api/v1/knowledge/${encodeURIComponent(documentId)}/compare`)
}

export function fetchKnowledgeExcerpt<T>(sourceId: string, chunkIndex: number) {
  return api<T>(`/api/v1/knowledge/${encodeURIComponent(sourceId)}/excerpt?chunk_index=${chunkIndex}`)
}

export async function extractKnowledgeFile<T>(file: File) {
  const body = new FormData()
  body.append('file', file)
  const headers = new Headers()
  const token = localStorage.getItem('access_token')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch('/api/v1/knowledge/extract', { method: 'POST', headers, body })
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const message = data && typeof data.detail === 'string' ? data.detail : `解析失败（${response.status}）`
    throw new Error(message)
  }
  return data as T
}

export function validateTelemetryCsv<T>(filename: string, content: string) {
  return api<T>('/api/v1/imports/telemetry-csv', {
    method: 'POST',
    headers: { 'Content-Type': 'text/csv', 'X-Filename': filename },
    body: content,
  })
}

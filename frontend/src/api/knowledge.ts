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

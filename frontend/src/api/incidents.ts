import { api } from './http'

export function resolveIncident(incidentId: string) {
  return api(`/api/v1/incidents/${encodeURIComponent(incidentId)}/resolve`, { method: 'POST' })
}

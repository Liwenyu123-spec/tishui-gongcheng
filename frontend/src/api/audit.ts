import { api } from './http'
export function fetchAuditEvents<T>() { return api<T[]>('/api/v1/audit-events') }

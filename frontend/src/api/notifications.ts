import { api } from './http'

export function fetchNotifications<T>() {
  return api<T[]>('/api/v1/notifications')
}

export function acknowledgeNotification<T>(id: string) {
  return api<T>(`/api/v1/notifications/${encodeURIComponent(id)}/ack`, { method: 'POST' })
}

export function escalateNotification<T>(id: string) {
  return api<T>(`/api/v1/notifications/${encodeURIComponent(id)}/escalate`, { method: 'POST' })
}

export function retryNotification<T>(id: string) {
  return api<T>(`/api/v1/notifications/${encodeURIComponent(id)}/retry`, { method: 'POST' })
}

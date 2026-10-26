import { api } from './http'

export function fetchAlarms<T>() { return api<T[]>('/api/v1/alarms') }
export function acknowledgeAlarm<T>(id: string) { return api<T>(`/api/v1/alarms/${encodeURIComponent(id)}/ack`, { method: 'POST' }) }
export function fetchAlarmDetail<T>(id: string) { return api<T>(`/api/v1/alarms/${encodeURIComponent(id)}`) }

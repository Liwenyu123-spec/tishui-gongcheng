import { api } from './http'

export function fetchStations<T>() { return api<T[]>('/api/v1/stations') }
export function fetchStation<T>(id: string) { return api<T>(`/api/v1/stations/${encodeURIComponent(id)}`) }
export function fetchTelemetry<T>(id: string) { return api<T[]>(`/api/v1/stations/${encodeURIComponent(id)}/telemetry`) }
export function fetchContacts<T>(id: string) { return api<T[]>(`/api/v1/stations/${encodeURIComponent(id)}/contacts`) }
export function sendHeartbeat<T>(id: string) { return api<T>(`/api/v1/stations/${encodeURIComponent(id)}/heartbeat`, { method: 'POST' }) }
export function reportIncident<T>(id: string, body: unknown) { return api<T>(`/api/v1/stations/${encodeURIComponent(id)}/incidents`, { method: 'POST', body: JSON.stringify(body) }) }

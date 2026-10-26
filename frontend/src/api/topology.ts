import { api } from './http'
export function fetchTopology<T>() { return api<T>('/api/v1/topology') }
export function fetchStationDetail<T>(id: string) { return api<T>(`/api/v1/stations/${encodeURIComponent(id)}`) }
export function fetchStationTelemetry<T>(id: string) { return api<T[]>(`/api/v1/stations/${encodeURIComponent(id)}/telemetry`) }

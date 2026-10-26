import { api } from './http'
export function fetchHealth<T>() { return api<T>('/api/v1/health') }
export function fetchDashboardStations<T>() { return api<T[]>('/api/v1/stations') }
export function fetchUnconfirmedAlarms<T>() { return api<T[]>('/api/v1/alarms?status=unconfirmed') }
export function fetchDashboardSupply<T>() { return api<T>('/api/v1/supply/balance') }
export function fetchPressureTelemetry<T>(stationId = 'pump-02') { return api<T[]>(`/api/v1/stations/${encodeURIComponent(stationId)}/telemetry?metric=pressure`) }

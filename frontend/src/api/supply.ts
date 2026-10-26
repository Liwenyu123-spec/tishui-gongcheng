import { api } from './http'

export function fetchSupplyBalance<T>() { return api<T>('/api/v1/supply/balance') }

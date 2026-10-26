import { api } from './http'
export function compareSchemes<T>(body: unknown) { return api<T>('/api/v1/schemes/compare', { method: 'POST', body: JSON.stringify(body) }) }
export function submitSchemeReview<T>(body: unknown) { return api<T>('/api/v1/reviews', { method: 'POST', body: JSON.stringify(body) }) }

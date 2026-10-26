import { api } from './http'
export function fetchReviews<T>() { return api<T[]>('/api/v1/reviews') }
export function updateReview<T>(id: string, body: unknown) { return api<T>(`/api/v1/reviews/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body) }) }
export function fetchReviewDetail<T>(id: string) { return api<T>(`/api/v1/reviews/${encodeURIComponent(id)}`) }

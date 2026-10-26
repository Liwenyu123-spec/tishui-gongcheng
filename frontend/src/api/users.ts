import { api } from './http'
export function fetchUsers<T>() { return api<T[]>('/api/v1/users') }
export function createUser<T>(body: unknown) { return api<T>('/api/v1/users', { method: 'POST', body: JSON.stringify(body) }) }
export function updateUser<T>(id: string, body: unknown) { return api<T>(`/api/v1/users/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body) }) }
export function deleteUser(id: string) { return api<{ deleted: string }>(`/api/v1/users/${encodeURIComponent(id)}`, { method: 'DELETE' }) }

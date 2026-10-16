import { api } from './http'

export interface User {
  id: string
  username: string
  display_name: string
  role: string
  permissions: string[]
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: User
}

export function login(username: string, password: string) {
  return api<LoginResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export function currentUser() {
  return api<User>('/api/v1/auth/me')
}

export function logout() {
  return api<{ success: boolean; message: string }>('/api/v1/auth/logout', { method: 'POST' })
}

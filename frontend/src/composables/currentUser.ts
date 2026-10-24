export interface CurrentUser {
  id?: string
  username?: string
  display_name?: string
  role?: string
  permissions?: string[]
}

export function readCurrentUser(): CurrentUser {
  try {
    return JSON.parse(localStorage.getItem('current_user') || '{}') as CurrentUser
  } catch {
    return {}
  }
}

export function currentUserRole(): string {
  return readCurrentUser().role || ''
}

export function hasPermission(permission: string): boolean {
  const user = readCurrentUser()
  return user.role === 'admin' || Boolean(user.permissions?.includes(permission))
}

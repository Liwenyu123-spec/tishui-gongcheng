export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  const token = localStorage.getItem('access_token')

  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(path, { ...options, headers })
  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = data && typeof data.detail === 'string' ? data.detail : `请求失败（${response.status}）`
    throw new Error(message)
  }

  return data as T
}

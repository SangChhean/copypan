export const TOKEN_KEY = 'cn_token'
export const USERNAME_KEY = 'cn_username'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token || '')
}

export function getUsername() {
  return localStorage.getItem(USERNAME_KEY) || ''
}

export function setUsername(username) {
  localStorage.setItem(USERNAME_KEY, username || '')
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USERNAME_KEY)
}

export function authHeaders() {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

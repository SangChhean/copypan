import { message } from 'ant-design-vue'

const TOKEN_KEY = 'qa_token'
const USERNAME_KEY = 'qa_username'
const EXPIRY_SKEW_MS = 30 * 1000

let router = null
let authRedirecting = false

export class AuthExpiredError extends Error {
  constructor() {
    super('AuthExpired')
    this.name = 'AuthExpiredError'
  }
}

export function bindRouter(r) {
  router = r
  router.afterEach((to) => {
    if (to.path === '/login') {
      window.setTimeout(() => {
        authRedirecting = false
      }, 400)
    }
  })
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function isTokenExpired(token) {
  try {
    if (!token || typeof token !== 'string') return true
    const parts = token.split('.')
    if (parts.length !== 3 || !parts[1]) return true
    const payload = JSON.parse(decodeBase64Url(parts[1]))
    const exp = Number(payload?.exp)
    if (!Number.isFinite(exp)) return true
    return exp * 1000 <= Date.now() + EXPIRY_SKEW_MS
  } catch {
    return true
  }
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USERNAME_KEY)
}

/** 多个 401 同时发生时只提示一次。返回 false 表示这次已被合并掉。 */
export function notifyAuthExpired() {
  if (authRedirecting) return false
  authRedirecting = true
  message.warning('登录已过期，请重新登录')
  return true
}

export function handleUnauthorized() {
  const route = router?.currentRoute?.value
  clearAuth()
  if (!route || route.path === '/login') return
  if (!notifyAuthExpired()) return
  router.replace({
    path: '/login',
    query: { redirect: route.fullPath },
  })
}

export async function authFetch(url, options = {}) {
  const token = getToken()
  if (!token || isTokenExpired(token)) {
    handleUnauthorized()
    throw new AuthExpiredError()
  }
  const headers = new Headers(options.headers || {})
  headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(url, { ...options, headers })
  if (response.status === 401) {
    handleUnauthorized()
    throw new AuthExpiredError()
  }
  return response
}

export function safeInternalPath(raw) {
  const value = Array.isArray(raw) ? raw[0] : raw
  if (typeof value !== 'string' || !value.startsWith('/')) return '/'
  let decoded = value
  try {
    decoded = decodeURIComponent(value)
  } catch {
    return '/'
  }
  if (!decoded.startsWith('/') || decoded.startsWith('//') || decoded.startsWith('/\\')) return '/'
  if (decoded.includes('://') || decoded.includes('\\')) return '/'
  return value
}

function decodeBase64Url(input) {
  const base64 = input.replace(/-/g, '+').replace(/_/g, '/')
  const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4)
  const binary = atob(padded)
  const bytes = Uint8Array.from(binary, (ch) => ch.charCodeAt(0))
  return new TextDecoder().decode(bytes)
}

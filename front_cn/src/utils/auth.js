import { message } from 'ant-design-vue'

export const TOKEN_KEY = 'cn_token'
export const USERNAME_KEY = 'cn_username'
export const IS_ADMIN_KEY = 'cn_is_admin'

let router = null
let authRedirecting = false

/** 由 router/index.js 注入，避免 auth.js ↔ router 循环引用 */
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
  localStorage.removeItem(IS_ADMIN_KEY)
}

export function authHeaders() {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export function setIsAdmin(val) {
  localStorage.setItem(IS_ADMIN_KEY, val ? '1' : '0')
}

export function isAdmin() {
  return localStorage.getItem(IS_ADMIN_KEY) === '1'
}

/** 提前 30 秒视为过期，避免"刚放行就过期"的请求 */
const EXPIRY_SKEW_MS = 30 * 1000

/**
 * 本地判断 JWT 是否已过期：只解码 payload 读取 exp，不验签。
 * 只是路由层的提前拦截；签名密钥变更等本地无法判断的失效，仍由请求层的 401 兜底。
 * 任何解析失败（格式损坏、非标准 JWT、缺少 exp）一律按已过期处理。
 */
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

function decodeBase64Url(input) {
  const base64 = input.replace(/-/g, '+').replace(/_/g, '/')
  const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4)
  const binary = atob(padded)
  const bytes = Uint8Array.from(binary, (ch) => ch.charCodeAt(0))
  return new TextDecoder().decode(bytes)
}

/** 多个 401 同时发生时只提示一次。返回 false 表示这次已被合并掉。 */
export function notifyAuthExpired() {
  if (authRedirecting) return false
  authRedirecting = true
  message.warning('登录已过期，请重新登录')
  return true
}

/** 全项目唯一的登录失效处理入口：清理本地登录状态并跳转登录页（带 redirect）。 */
export function handleUnauthorized() {
  clearAuth()
  const route = router?.currentRoute?.value
  if (!router || !route || route.path === '/login') return
  if (!notifyAuthExpired()) return
  router.replace({
    path: '/login',
    query: { redirect: route.fullPath },
  })
}

/** 这两个接口的 401 表示"用户名/密码错误"，不是登录失效，由页面自行提示 */
const UNAUTHORIZED_EXCLUDED_PATHS = ['/api/cn/auth/login', '/api/cn/auth/change_password']

export function isUnauthorizedExcluded(url) {
  if (!url) return false
  const path = new URL(url, window.location.origin).pathname.replace(/\/+$/, '')
  return UNAUTHORIZED_EXCLUDED_PATHS.includes(path)
}

/**
 * 请求层收到"登录失效"的 401 时调用（http 拦截器与 authFetch 共用）：
 * 触发统一的登录失效处理，并返回一个永不完成的 promise 交还给调用方。
 *
 * 【有意为之，不是漏写 reject】
 * - 登录失效时页面马上会被带去登录页；如果 reject，各组件自己的 catch 会再弹一遍
 *   "加载XX失败（401）"之类的提示，叠在登录页上，这正是本次要消除的现象。
 * - 副作用：调用方的 then/catch/finally 都不会执行（loading 不会被关掉）。这没关系：
 *   发起请求的页面组件随跳转一起卸载，loading 状态随实例丢弃；后退回该页时，路由守卫
 *   因 token 已清除会再次拦到登录页；重新登录后进入是全新实例，状态从头初始化。
 * - 内存：没有任何对象持有这个 promise 的 resolve/reject，它和等待它的调用链一起变成
 *   不可达对象，会被 GC 正常回收，不会随多次 401 累积。
 * 注意：不要改成 reject，也不要在需要"失败后一定收尾"的场景（例如非页面级的全局状态）
 * 依赖 finally —— 登录失效时它不会执行。这类场景请用 authFetch 的 throwOnUnauthorized。
 */
export function abortOnUnauthorized() {
  handleUnauthorized()
  return new Promise(() => {})
}

/** authFetch 在 throwOnUnauthorized 模式下遇到登录失效时抛出，调用方据此静默退出 */
export class AuthExpiredError extends Error {
  constructor() {
    super('AuthExpired')
    this.name = 'AuthExpiredError'
  }
}

/**
 * 原生 fetch 的鉴权封装：自动带 Bearer token，401 走与 http 实例相同的登录失效处理。
 * 返回原始 Response（不读取 body），流式读取、blob 下载等用法与原生 fetch 完全一致。
 * 只用于本站 /api 接口；外部地址（如 Polly）和静态文件请继续用原生 fetch，避免把 token 发出去。
 *
 * 默认 401 时挂起（见 abortOnUnauthorized）。若调用处于需要善后清理的全局上下文中
 * （例如 navigator.locks.request 的回调：挂起会让锁永不释放，重新登录后再次请求会永久卡住），
 * 传 throwOnUnauthorized: true：同样先统一处理登录失效，再抛出 AuthExpiredError，
 * 调用方在 catch 中识别该错误并静默返回（不要再弹错误提示）。
 */
export async function authFetch(url, { throwOnUnauthorized = false, ...options } = {}) {
  const headers = new Headers(options.headers || {})
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(url, { ...options, headers })
  if (response.status === 401 && !isUnauthorizedExcluded(url)) {
    if (throwOnUnauthorized) {
      handleUnauthorized()
      throw new AuthExpiredError()
    }
    return abortOnUnauthorized()
  }
  return response
}

/** 只允许站内相对路径作为 redirect，防止开放重定向。 */
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
  if (decoded === '/login' || decoded.startsWith('/login?')) return '/'
  return value
}

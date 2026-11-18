import { truncateHistory } from './streamState.js'

const TOKEN_KEY = 'qa4_token'
const USERNAME_KEY = 'qa4_username'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(t) {
  if (t) localStorage.setItem(TOKEN_KEY, t)
  else localStorage.removeItem(TOKEN_KEY)
}

export function getUsername() {
  return localStorage.getItem(USERNAME_KEY) || ''
}

export function setUsername(name) {
  if (name) localStorage.setItem(USERNAME_KEY, name)
  else localStorage.removeItem(USERNAME_KEY)
}

export function clearAuth() {
  setToken('')
  setUsername('')
}

/** 解析 FastAPI / 自研 JSON 错误体。 */
export function extractApiError(data, fallback = '请求失败') {
  if (!data || typeof data !== 'object') return fallback
  const d = data.detail
  if (typeof d === 'string' && d.trim()) return d
  if (d && typeof d === 'object' && d.message) return String(d.message)
  if (Array.isArray(d) && d[0]) {
    const first = d[0]
    if (typeof first === 'string') return first
    if (first && first.msg) return String(first.msg)
  }
  if (data.message) return String(data.message)
  return fallback
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

export function formatDailyUsageText(used, limit) {
  const u = Number(used) || 0
  const lim = Number(limit) || 0
  if (lim <= 0) return ''
  return `今日 ${u}/${lim}`
}

export function dailyUsageLevelClass(used, limit) {
  const u = Number(used) || 0
  const lim = Number(limit) || 0
  if (lim > 0 && u >= lim) return 'qa-daily-usage--danger'
  if (lim > 0 && u >= lim * 0.8) return 'qa-daily-usage--warn'
  return ''
}

export async function login(username, password) {
  const r = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(extractApiError(data, '登录失败'))
  setToken(data.token)
  setUsername(data.username || username)
  return data
}

export async function register(invite, username, password) {
  const r = await fetch('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ invite_code: invite, username, password }),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(extractApiError(data, '注册失败'))
  return data
}

export async function fetchDailyUsage() {
  const r = await fetch('/api/auth/usage', {
    headers: { Authorization: `Bearer ${getToken()}` },
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(extractApiError(data, '读取用量失败'))
  return {
    used: Number(data.used) || 0,
    limit: Number(data.limit) || 0,
  }
}

/** 解析 SSE：data: {...}\n\n */
export async function* readSse(response) {
  const reader = response.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let idx
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      for (const line of chunk.split('\n')) {
        if (line.startsWith('data:')) {
          const raw = line.slice(5).trim()
          if (!raw || raw === '[DONE]') continue
          try {
            yield JSON.parse(raw)
          } catch {
            /* ignore heartbeat garbage */
          }
        }
      }
    }
  }
}

export class ApiHttpError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiHttpError'
    this.status = status
  }
}

export async function streamAsk(question, history, onEvent) {
  const hist = truncateHistory(history || [], 3).map((t) => ({
    question: t.question,
    answer: (t.answer || '').slice(0, 300),
  }))
  const r = await fetch('/api/qa/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify({ question, history: hist }),
  })
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    const msg =
      extractApiError(data, '') ||
      (r.status === 429 ? '今日问答次数已达上限，请明天再来' : `HTTP ${r.status}`)
    throw new ApiHttpError(msg, r.status)
  }
  for await (const ev of readSse(r)) {
    onEvent(ev)
  }
}

export async function sendFeedback(requestId, rating) {
  const r = await fetch('/api/feedback', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify({ request_id: requestId, rating }),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(extractApiError(data, '反馈失败'))
  return data
}

/** 三语：简体原文在前端本地切；繁/英调后端。 */
export async function translateAnswer({ text, sources = [], targetLang, question = '', cacheKey = '' }) {
  const r = await fetch('/api/translate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify({
      text,
      sources,
      target_lang: targetLang,
      question,
      cache_key: cacheKey,
    }),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new ApiHttpError(extractApiError(data, '翻译失败'), r.status)
  // 后端字段为 answer；兼容 text
  return {
    answer: data.answer ?? data.text ?? '',
    sources: Array.isArray(data.sources) ? data.sources : [],
    text: data.answer ?? data.text ?? '',
  }
}

/** MiniMax 朗读：返回可播放的 Blob。 */
export async function fetchTtsMinimax(text, lang = 'zh') {
  const r = await fetch('/api/tts/minimax', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify({ text, lang }),
  })
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    throw new ApiHttpError(extractApiError(data, '朗读失败'), r.status)
  }
  return r.blob()
}

/** 语音转写：FormData 上传录音。 */
export async function transcribeAudio(blob, filename = 'recording.webm') {
  const form = new FormData()
  form.append('file', blob, filename)
  const r = await fetch('/api/asr', {
    method: 'POST',
    headers: { Authorization: `Bearer ${getToken()}` },
    body: form,
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new ApiHttpError(extractApiError(data, '识别失败'), r.status)
  return String(data.text || '')
}

export async function adminTraces(adminToken, limit = 50) {
  const r = await fetch(`/api/admin/traces?limit=${limit}`, {
    headers: { 'X-Admin-Token': adminToken },
  })
  return r.json()
}

export async function adminTraceDetail(adminToken, id) {
  const r = await fetch(`/api/admin/traces/${id}`, {
    headers: { 'X-Admin-Token': adminToken },
  })
  return r.json()
}

export async function adminCreateInvite(adminToken, code, { maxUses = 1, note = '' } = {}) {
  const r = await fetch('/api/admin/invites', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Token': adminToken,
    },
    body: JSON.stringify({ code, max_uses: maxUses, note }),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(extractApiError(data, '生成邀请码失败'))
  return data
}

export async function adminListInvites(adminToken) {
  const r = await fetch('/api/admin/invites', {
    headers: { 'X-Admin-Token': adminToken },
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(extractApiError(data, '邀请码列表失败'))
  return data.items || []
}

export async function adminListUsers(adminToken) {
  const r = await fetch('/api/admin/users', {
    headers: { 'X-Admin-Token': adminToken },
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(extractApiError(data, '用户列表失败'))
  return data.items || []
}

export async function adminSetUserLimit(adminToken, username, dailyLimit) {
  const r = await fetch(`/api/admin/users/${encodeURIComponent(username)}/limit`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Token': adminToken,
    },
    body: JSON.stringify({ daily_limit: dailyLimit }),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(extractApiError(data, '调整额度失败'))
  return data
}

export async function adminDeleteUser(adminToken, username) {
  const r = await fetch(`/api/admin/users/${encodeURIComponent(username)}`, {
    method: 'DELETE',
    headers: { 'X-Admin-Token': adminToken },
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(extractApiError(data, '删除用户失败'))
  return data
}

export async function adminDisableUser(adminToken, username, disabled = true) {
  const r = await fetch(`/api/admin/users/${encodeURIComponent(username)}/disable`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Token': adminToken,
    },
    body: JSON.stringify({ disabled: !!disabled }),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(extractApiError(data, '停用用户失败'))
  return data
}

export async function adminStats(adminToken) {
  const r = await fetch('/api/admin/stats', {
    headers: { 'X-Admin-Token': adminToken },
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(extractApiError(data, '统计加载失败'))
  return data
}

export async function adminFeedbackStats(adminToken) {
  const r = await fetch('/api/admin/feedback/stats', {
    headers: { 'X-Admin-Token': adminToken },
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(extractApiError(data, '反馈统计失败'))
  return data
}

export async function adminClearCache(adminToken) {
  const r = await fetch('/api/admin/cache/clear', {
    method: 'POST',
    headers: { 'X-Admin-Token': adminToken },
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(extractApiError(data, '清除缓存失败'))
  return data
}

export async function adminClearStats(adminToken) {
  const r = await fetch('/api/admin/stats/clear', {
    method: 'POST',
    headers: { 'X-Admin-Token': adminToken },
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(extractApiError(data, '清空统计失败'))
  return data
}

export async function adminDisableInvite(adminToken, code) {
  const r = await fetch(`/api/admin/invites/${encodeURIComponent(code)}/disable`, {
    method: 'POST',
    headers: { 'X-Admin-Token': adminToken },
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(extractApiError(data, '停用邀请码失败'))
  return data
}

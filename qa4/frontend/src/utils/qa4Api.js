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

/**
 * 解析 SSE：data: {...}\n\n
 * 对齐 3.0 QAPage：TextDecoder stream、\r\n→\n、按 \n\n 切事件、边读边 yield（不等整响应结束）。
 */
export async function* readSse(response) {
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    buffer = buffer.replace(/\r\n/g, '\n')
    let sepIdx
    while ((sepIdx = buffer.indexOf('\n\n')) !== -1) {
      const rawEvent = buffer.slice(0, sepIdx)
      buffer = buffer.slice(sepIdx + 2)
      for (const line of rawEvent.split('\n')) {
        if (!line.startsWith('data:')) continue
        const raw = line.startsWith('data: ') ? line.slice(6).trim() : line.slice(5).trim()
        if (!raw || raw === '[DONE]') continue
        try {
          yield JSON.parse(raw)
        } catch {
          /* ignore heartbeat / garbage */
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

function _debugStreamEnabled() {
  try {
    if (typeof localStorage !== 'undefined' && localStorage.getItem('qa4_debug_stream') === '1') {
      return true
    }
  } catch {
    /* ignore */
  }
  return false
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
  const t0 = typeof performance !== 'undefined' ? performance.now() : Date.now()
  let tokenN = 0
  let firstTokenAt = null
  for await (const ev of readSse(r)) {
    // 每次事件再读开关，避免页面加载时定死
    if (_debugStreamEnabled() && ev && (ev.event === 'token' || ev.type === 'token')) {
      tokenN += 1
      const now = typeof performance !== 'undefined' ? performance.now() : Date.now()
      if (firstTokenAt == null) firstTokenAt = now
      console.log(
        `[qa4-stream] token#${tokenN} +${(now - t0).toFixed(1)}ms sinceStart +${(now - firstTokenAt).toFixed(1)}ms sinceFirst len=${String(ev.text || '').length}`,
        (ev.text || '').slice(0, 40),
      )
    }
    if (_debugStreamEnabled() && ev && (ev.event === 'done' || ev.type === 'done')) {
      const now = typeof performance !== 'undefined' ? performance.now() : Date.now()
      console.log(
        `[qa4-stream] done +${(now - t0).toFixed(1)}ms tokens=${tokenN} spanFirstToDone=${
          firstTokenAt != null ? (now - firstTokenAt).toFixed(1) : 'n/a'
        }ms`,
      )
    }
    // 对齐 3.0：done 分支可 await 打字机清空，须等回调完成
    await onEvent(ev)
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

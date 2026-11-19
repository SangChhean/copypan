/**
 * 语言切换：与 3.0 QAPage.switchLang 对齐。
 * 原文始终保留在 plainDisplay / plain / sourceItems；译文缓存在 translatedAnswers。
 * 切繁/英一律从原始简体出发，切回简体只改 currentLang，不调接口。
 */

/** 「引用书目」小标题随语言（与 3.0 一致）。 */
export function sourcesTitle(lang) {
  if (lang === 'en') return 'References'
  if (lang === 'zh_tw') return '引用書目'
  return '引用书目'
}

/** 送译正文：永远用原始简体（重编号后的 plainDisplay），不用当前已显示的繁/英。 */
export function originalTranslateText(m) {
  return String(m?.plainDisplay || m?.plain || m?.notFoundMsg || '')
}

/**
 * 送译书目：永远用原始简体 sourceItems（含 source_en 等字段供后端选用）。
 * 旧缓存无结构化书目时回退为 bibliography 分行。
 */
export function originalTranslateSources(m) {
  if (Array.isArray(m?.sourceItems) && m.sourceItems.length) {
    return m.sourceItems.map((s) => ({
      n: s.n,
      zh: s.zh || '',
      en: s.en || '',
      source_zh: s.source_zh || '',
      book_title: s.book_title || '',
      message_title: s.message_title || '',
      message_number: s.message_number != null ? s.message_number : null,
    }))
  }
  const bib = String(m?.bibliography || '').trim()
  if (!bib) return []
  return bib
    .split(/\n+/)
    .map((s) => s.trim())
    .filter(Boolean)
}

/** 从 translatedAnswers 同步到 translated* 展示字段（Vue 侧仍可读这些字段）。 */
export function applyCachedTranslation(m, lang, decorateHtml) {
  const cached = m.translatedAnswers?.[lang]
  if (!cached) return false
  const answer = cached.answer || ''
  m.translatedPlain = answer
  m.translatedHtml = typeof decorateHtml === 'function' ? decorateHtml(answer) : answer
  m.translatedBib = Array.isArray(cached.sources) ? cached.sources.join('\n') : m.bibliography || ''
  m.currentLang = lang
  return true
}

/**
 * 切换消息语言（与 3.0 switchLang 同序）。
 * @param {object} m 助手消息
 * @param {'zh'|'zh_tw'|'en'} lang
 * @param {{ translate: Function, decorateHtml?: Function, stopTts?: Function }} deps
 * @returns {Promise<{ skipped?: boolean, restored?: string, cached?: string, translated?: string, request?: object }>}
 */
export async function switchMessageLang(m, lang, deps = {}) {
  const { translate, decorateHtml, stopTts } = deps
  if (!m || m.translating) return { skipped: true }
  if (lang === m.currentLang) return { skipped: true }
  if (typeof stopTts === 'function') stopTts()

  // 回简体：直接恢复原始，不调接口（3.0 只设 currentLang）
  if (lang === 'zh') {
    m.currentLang = 'zh'
    return { restored: 'zh' }
  }

  // 已有缓存：直接展示
  if (m.translatedAnswers?.[lang]) {
    applyCachedTranslation(m, lang, decorateHtml)
    return { cached: lang }
  }

  const text = originalTranslateText(m)
  if (!text.trim()) return { skipped: true }

  const sources = originalTranslateSources(m)
  const request = {
    text,
    sources,
    targetLang: lang,
    question: m.question || '',
    cacheKey: (m.doneMeta && m.doneMeta.request_id) || '',
  }

  m.translating = true
  try {
    if (typeof translate !== 'function') {
      throw new Error('translate 未提供')
    }
    const data = await translate(request)
    const answer = data.answer || data.text || ''
    const outSources = Array.isArray(data.sources) ? data.sources : []
    if (!m.translatedAnswers) m.translatedAnswers = {}
    m.translatedAnswers[lang] = { answer, sources: outSources }
    applyCachedTranslation(m, lang, decorateHtml)
    return { translated: lang, request }
  } finally {
    m.translating = false
  }
}

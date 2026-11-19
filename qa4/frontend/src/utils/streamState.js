/**
 * qa4 SSE / 事件流状态机（纯函数，便于 vitest）。
 * 事件：step / plan / token / direct / verse_data / hymn_data / choose / done / error / heartbeat
 *
 * 契约：done 正文在后端字段 `answer`（含引文核对后的〔未核实〕）；
 * 前端兼容 `answer_text` 别名。
 */

export function createStreamState() {
  return {
    steps: [],
    plan: null,
    tokens: [],
    text: '',
    invalidated: false,
    directs: [],
    verseData: null,
    hymnData: null,
    choose: null,
    done: null,
    error: null,
    historyLimit: 3,
  }
}

/** 取 done 最终正文：优先 answer_text，其次 answer（orchestrator 实际字段）。 */
export function doneAnswerText(ev) {
  if (!ev || typeof ev !== 'object') return null
  if (ev.answer_text != null) return String(ev.answer_text)
  if (ev.answer != null) return String(ev.answer)
  return null
}

export function applyEvent(state, ev) {
  if (!ev || typeof ev !== 'object') return state
  const type = ev.event || ev.type
  const next = { ...state }
  if (type === 'step') {
    next.steps = [...state.steps, { step: ev.step, subq: ev.subq, note: ev.note, progress: ev.progress }]
  } else if (type === 'plan') {
    next.plan = ev
  } else if (type === 'token') {
    if (!state.invalidated) {
      next.tokens = [...state.tokens, ev.text || '']
      next.text = state.text + (ev.text || '')
    }
  } else if (type === 'direct') {
    next.directs = [...state.directs, ev]
  } else if (type === 'verse_data') {
    // 3.0 同形：单节对象，或 {verses, query_type}
    next.verseData = ev.data !== undefined ? ev.data : ev
  } else if (type === 'hymn_data') {
    next.hymnData = ev.data !== undefined ? ev.data : ev
  } else if (type === 'choose') {
    next.choose = ev
  } else if (type === 'error') {
    next.error = ev
    if (ev.invalidate_streamed) {
      next.invalidated = true
      next.text = ''
      next.tokens = []
    }
  } else if (type === 'done') {
    next.done = ev
    const finalText = doneAnswerText(ev)
    // 空/全空白 answer 且已有流式正文时不覆盖（兜底 done.answer:""）；invalidated 不覆盖
    if (!state.invalidated && finalText != null) {
      if (String(finalText).trim() !== '' || !state.text) {
        next.text = finalText
      }
    }
  }
  return next
}

export function truncateHistory(turns, limit = 3) {
  const arr = Array.isArray(turns) ? turns : []
  return arr.slice(-limit)
}

/**
 * 按正文中 [n] 首次出现顺序重编显示编号 1、2、3…；
 * data-n 仍为原始段落号（供点击/悬浮查原文）；书目只含实际引用到的条目。
 */
export function renderCitationsMarkdown(text, citations) {
  const cites = Array.isArray(citations) ? citations : []
  const byOrig = new Map()
  for (const c of cites) {
    const n = Number(c && c.n)
    if (Number.isFinite(n) && !byOrig.has(n)) byOrig.set(n, c)
  }
  const src = String(text || '')
  const order = []
  const seen = new Set()
  const re = /\[(\d+)\]/g
  let m
  while ((m = re.exec(src))) {
    const n = Number(m[1])
    if (!seen.has(n)) {
      seen.add(n)
      order.push(n)
    }
  }
  const origToDisp = new Map(order.map((n, i) => [n, i + 1]))
  const plainBody = src.replace(/\[(\d+)\]/g, (_, nStr) => {
    const orig = Number(nStr)
    const disp = origToDisp.get(orig)
    if (disp == null) return `[${nStr}]`
    return `[${disp}]`
  })
  const body = src.replace(/\[(\d+)\]/g, (_, nStr) => {
    const orig = Number(nStr)
    const disp = origToDisp.get(orig)
    if (disp == null) return `[${nStr}]`
    return `<sup class="cite" data-n="${orig}">[${disp}]</sup>`
  })
  const sourceItems = order.map((orig, i) => {
    const c = byOrig.get(orig) || { n: orig }
    const disp = i + 1
    const loc = (c && c.location) || {}
    const index = (c && c.index) || ''
    // map_note 对齐 3.0：书目用 source_zh（恢复本注释）；空则回退 book+message
    let zhBody = `${c.book_title || ''} ${c.message_title || ''}`.trim()
    if (index === 'map_note') {
      const raw = String(loc.source_zh || '').trim()
      const cleaned = raw.replace(/^[（(]+/, '').replace(/[）)]+$/, '').trim()
      if (cleaned) zhBody = cleaned
    }
    const zh = `[${disp}] ${zhBody}`.trim()
    return {
      n: disp,
      zh,
      en: (c.source_en || loc.source_en || '').trim(),
      source_zh: (loc.source_zh || '').trim(),
      book_title: c.book_title || '',
      message_title: c.message_title || '',
      message_number: loc.message_number != null ? loc.message_number : null,
      index,
    }
  })
  const bibliography = sourceItems.map((s) => s.zh).join('\n')
  return {
    body,
    plainBody,
    bibliography,
    sourceItems,
    origToDisp: Object.fromEntries(origToDisp),
  }
}

function decorateInline(chunk) {
  return String(chunk || '')
    .replace(/〔归纳〕/g, '<em class="induction">〔归纳〕</em>')
    .replace(/「([^」]+)」/g, '<span class="quote">「$1」</span>')
    .replace(/〔未核实〕/g, '<mark class="unverified">〔未核实〕</mark>')
}

/** 对正文做朴素 HTML 标记（非 Markdown）。「## 」「### 」行转标题；半行不报错。 */
export function decorateAnswerHtml(body) {
  const lines = String(body || '').split(/\r?\n/)
  return lines
    .map((line) => {
      if (line.startsWith('### ')) {
        return `<div class="a-sub">${decorateInline(line.slice(4))}</div>`
      }
      if (line.startsWith('## ')) {
        return `<div class="a-title">${decorateInline(line.slice(3))}</div>`
      }
      return decorateInline(line)
    })
    .join('\n')
}

export function chooseFollowupQuestion(cand) {
  const series = cand.series || cand.series_zh || 'big'
  const n = cand.hymn_number
  if (series === 'sup' || String(series).includes('补充')) return `补充本第${n}首`
  if (series === 'fu' || String(series).includes('附')) return `诗歌附${n}`
  return `诗歌第${n}首`
}

/** direct 块出处标题（meta 内字段）。 */
export function formatDirectTitle(ev, blockIndex = 0) {
  const meta = (ev && (ev.meta || ev)) || {}
  const ref = meta.ref || meta.scripture || meta.label
  const book = meta.book_title || meta.name
  const msg = meta.message_title || meta.title
  const msgNo = meta.message_number
  const series = meta.series || meta.series_zh
  const hymnNo = meta.hymn_number
  if (ref && book) return `${book} ${ref}`
  if (ref) return String(ref)
  if (series && hymnNo != null) return `诗歌 ${series} ${hymnNo}`
  if (book && msgNo != null) return `${book} 第${msgNo}篇`
  if (book && msg) return `${book} ${msg}`
  if (book) return String(book)
  if (msg) return String(msg)
  return `块 ${blockIndex + 1}`
}

export function formatNotFoundMessage(done, plainText = '') {
  const raw = String(plainText || doneAnswerText(done) || '').trim()
  const premise = (done && done.premise_note) || ''
  let detail = raw
  if (!detail || detail === 'not_found' || detail === 'not_supported') {
    detail = ''
  }
  const lines = ['没有找到相关内容']
  if (detail) lines.push(detail)
  else if (premise) lines.push(String(premise))
  return lines.join('：')
}

export function hasUnverifiedMark(text) {
  return String(text || '').includes('〔未核实〕')
}

export function planIsComplex(plan) {
  return !!(plan && plan.complex)
}

export function planIsSensitive(plan) {
  return !!(plan && plan.sensitive)
}

export function planSubquestions(plan) {
  return (plan && Array.isArray(plan.subquestions) ? plan.subquestions : []) || []
}

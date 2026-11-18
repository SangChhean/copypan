<template>
  <div class="qa-root">
    <header class="qa-header">
      <div class="qa-header-inner">
        <div class="qa-logo">
          <span class="qa-logo-text">职事信息问答</span>
        </div>
        <div class="qa-header-right">
          <span
            v-if="dailyUsage.limit > 0"
            class="qa-daily-usage"
            :class="usageLevelClass"
          >{{ usageDisplayText }}</span>
          <button type="button" class="qa-new-chat-btn" @click="newConversation">+ 新对话</button>
          <a-dropdown placement="bottomRight">
            <a-avatar class="qa-user-avatar">{{ avatarText }}</a-avatar>
            <template #overlay>
              <a-menu>
                <a-menu-item disabled>{{ currentUsername || '未登录' }}</a-menu-item>
                <a-menu-divider />
                <a-menu-item @click="goAdmin">管理后台</a-menu-item>
                <a-menu-item class="qa-logout-item" @click="logout">退出登录</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
      </div>
    </header>

    <main class="qa-main" ref="mainEl">
      <div v-if="messages.length === 0" class="qa-welcome">
        <div class="qa-welcome-title">真理必叫你们得以自由</div>
        <div class="qa-welcome-sub">The truth shall set you free</div>
        <div class="qa-example-list">
          <div
            v-for="ex in examples"
            :key="ex"
            class="qa-example-chip"
            @click="fillExample(ex)"
          >{{ ex }}</div>
        </div>
      </div>

      <div v-else class="qa-chat">
        <div
          v-for="m in messages"
          :key="m.id"
          class="qa-msg-row"
          :class="m.role === 'user' ? 'qa-msg-row--user' : 'qa-msg-row--assistant'"
        >
          <div v-if="m.role === 'user'" class="qa-bubble qa-bubble-user">{{ m.content }}</div>
          <div v-else class="qa-bubble qa-bubble-assistant">
            <div v-if="m.loading" class="qa-loading">
              <a-spin size="small" />
              <span class="qa-loading-text">{{ m.stepHint ? ('进行中… ' + m.stepHint) : '正在检索职事信息…' }}</span>
            </div>

            <div v-if="m.plan && !m.loading" class="qa-plan">
              <div class="qa-plan-type">
                题型：{{ m.plan.main_type || m.plan.mainType || '—' }}
                <span v-if="m.plan.sensitive" class="tag sens">敏感</span>
                <span v-if="m.plan.complex" class="tag complex">复杂</span>
              </div>
              <div v-if="m.plan.understanding" class="qa-premise">{{ m.plan.understanding }}</div>
              <ul v-if="m.plan.complex && m.subqList && m.subqList.length" class="subq-list">
                <li v-for="(sq, i) in m.subqList" :key="i">
                  <span class="muted">#{{ i }}</span>
                  {{ sq.text || sq.qtype || '子问题' }}
                  <span v-if="sq.synthesis" class="tag">综合</span>
                  <span v-if="m.subqProgress && m.subqProgress[i]" class="muted"> · {{ m.subqProgress[i] }}</span>
                </li>
              </ul>
            </div>

            <BibleMessage
              v-if="m.intent === 'bible' && (m.verse || (m.verses && m.verses.length))"
              :verse="m.verse"
              :verses="m.verses"
              :query-type="m.queryType || 'verse'"
              :generating="m.bibleGenerating"
            />
            <HymnMessage
              v-if="m.intent === 'hymn' && m.hymnData"
              :hymn-data="m.hymnData"
              :generating="m.hymnGenerating"
              :show-ministry="!!(m.html || m.hymnGenerating)"
            />
            <div
              v-if="m.directHtml && m.intent !== 'bible' && m.intent !== 'hymn'"
              class="direct"
              v-html="m.directHtml"
            ></div>
            <div v-if="m.choose" class="choose">
              <div class="choose-title">找到多首相关诗歌，请选择：</div>
              <button
                v-for="(c, i) in m.choose.candidates || []"
                :key="i"
                class="choose-btn"
                @click="pickChoose(c)"
              >
                <span class="choose-main">
                  {{ displaySeries(c) }}第{{ c.hymn_number }}首
                  <span v-if="c.name" class="choose-name">{{ c.name }}</span>
                </span>
                <span v-if="c.unit_label || c.snippet" class="choose-snip">
                  {{ c.unit_label ? c.unit_label + ' · ' : '' }}{{ c.snippet || '' }}
                </span>
              </button>
            </div>

            <div v-if="m.notFoundMsg" class="qa-not-found">
              <span class="qa-not-found-icon">🔍</span>
              {{ m.notFoundMsg }}
            </div>
            <div
              v-if="displayHtml(m) && !m.notFoundMsg && m.intent !== 'hymn'"
              class="qa-answer-body"
              :class="{ 'qa-answer-fade': m.currentLang && m.currentLang !== 'zh' }"
              v-html="displayHtml(m)"
            ></div>
            <div
              v-if="displayHtml(m) && !m.notFoundMsg && m.intent === 'hymn'"
              class="qa-answer-body hymn-ministry"
              :class="{ 'qa-answer-fade': m.currentLang && m.currentLang !== 'zh' }"
              v-html="displayHtml(m)"
            ></div>

            <div v-if="displayBib(m)" class="qa-sources">
              <div class="qa-sources-title">引用书目</div>
              <pre class="qa-sources-body">{{ displayBib(m) }}</pre>
            </div>

            <div v-if="m.doneMeta" class="qa-meta">
              <span v-if="m.doneMeta.cache_hit" class="qa-meta-badge qa-meta-cache">缓存</span>
              <span v-if="m.doneMeta.degraded" class="qa-meta-badge qa-meta-degraded">已降级</span>
              <span v-if="m.doneMeta.lyrics_status" class="qa-meta-time">歌词：{{ m.doneMeta.lyrics_status }}</span>
              <span v-if="m.doneMeta.elapsed_s" class="qa-meta-time">{{ m.doneMeta.elapsed_s }}s</span>
            </div>
            <div v-if="m.doneMeta && showDevMeta" class="qa-meta detail-line">
              <button type="button" class="linkish" @click="m.showDetail = !m.showDetail">
                {{ m.showDetail ? '收起详情' : '详情' }}
              </button>
              <div v-if="m.showDetail" class="detail-box">
                <div v-if="m.doneMeta.request_id">request_id={{ m.doneMeta.request_id }}</div>
                <div v-if="m.doneMeta.plan_source">source={{ m.doneMeta.plan_source }}</div>
              </div>
            </div>

            <div v-if="m.error" class="qa-request-fail">
              <div class="qa-request-fail-text">{{ m.error }}</div>
              <button type="button" class="qa-retry-btn" :disabled="loading" @click="retryLast(m)">重试</button>
            </div>

            <div v-if="m.doneMeta && !m.loading" class="qa-actions">
              <div class="qa-actions-row1">
                <button
                  type="button"
                  class="qa-feedback-btn qa-copy-btn"
                  :disabled="m.copied"
                  @click="copyAnswer(m)"
                >
                  <svg
                    v-if="m.copied"
                    xmlns="http://www.w3.org/2000/svg"
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  >
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                  <span v-if="m.copied">copied</span>
                  <svg
                    v-if="!m.copied"
                    xmlns="http://www.w3.org/2000/svg"
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  >
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                  </svg>
                  <span v-if="!m.copied">copy</span>
                </button>
                <button
                  v-if="!m.notFoundMsg"
                  type="button"
                  class="qa-feedback-btn"
                  :class="{ 'is-selected': m.feedback === 1, 'is-muted': m.feedback === -1 }"
                  :disabled="m.feedback != null || m.feedbackSubmitting"
                  @click="vote(m, 1)"
                >
                  👍
                </button>
                <button
                  v-if="!m.notFoundMsg"
                  type="button"
                  class="qa-feedback-btn"
                  :class="{ 'is-selected': m.feedback === -1, 'is-muted': m.feedback === 1 }"
                  :disabled="m.feedback != null || m.feedbackSubmitting"
                  @click="vote(m, -1)"
                >
                  👎
                </button>
              </div>
              <div v-if="!m.notFoundMsg && m.plain" class="qa-action-row2">
                <div class="qa-lang-toggle">
                  <button
                    v-for="opt in langOptions"
                    :key="opt.value"
                    type="button"
                    class="qa-lang-toggle-btn"
                    :class="{ 'is-active': m.currentLang === opt.value }"
                    :disabled="m.translating"
                    @click="switchLang(m, opt.value)"
                  >
                    {{ m.translating && m.currentLang !== opt.value ? '…' : opt.label }}
                  </button>
                </div>
                <button
                  type="button"
                  class="qa-tts-btn qa-tts-btn--minimax"
                  :disabled="ttsState(m) === 'loading'"
                  :title="ttsTitle(m)"
                  @click="toggleTTS(m)"
                >
                  <span v-if="ttsState(m) === 'loading'">…</span>
                  <span v-else-if="ttsState(m) === 'playing'">{{ ttsProgress(m) ? `⏸ ${ttsProgress(m)}` : '⏸' }}</span>
                  <span v-else-if="ttsState(m) === 'paused'">{{ ttsProgress(m) ? `▶ ${ttsProgress(m)}` : '▶' }}</span>
                  <span v-else>{{ ttsIdleLabel(m) }}</span>
                </button>
              </div>
            </div>

            <div v-if="!m.loading && !m.error" class="qa-disclaimer">
              <span v-if="m.currentLang === 'en'">The above content is quoted directly from the ministry messages.</span>
              <span v-else-if="m.currentLang === 'zh_tw'">以上內容直接摘自職事信息原文。</span>
              <span v-else>以上内容直接摘自职事信息原文。</span>
            </div>
          </div>
        </div>
      </div>
    </main>

    <footer class="qa-footer">
      <div class="qa-input-wrap">
        <button
          type="button"
          class="qa-mic-btn"
          :class="{ active: voiceMode, recording: audioState === 'recording', processing: audioState === 'processing' }"
          :disabled="loading || audioState === 'processing'"
          :title="voiceMode ? '退出语音' : '语音输入'"
          @click="clickMic"
        >
          <svg
            v-if="!voiceMode"
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M12 1a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
            <path d="M19 10v1a7 7 0 0 1-14 0v-1"></path>
            <line x1="12" y1="19" x2="12" y2="23"></line>
            <line x1="8" y1="23" x2="16" y2="23"></line>
          </svg>
          <svg
            v-else
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
        <a-textarea
          v-if="!voiceMode"
          v-model:value="input"
          placeholder="请输入问题（支持简体、繁體、English，切换输入法提问，答案语言自动跟随）"
          :auto-size="{ minRows: 1, maxRows: 5 }"
          :maxlength="500"
          :disabled="loading"
          class="qa-textarea"
          @keydown.enter.exact.prevent="submit"
        />
        <div v-else class="qa-voice-area">
          <div v-if="audioState === 'recording'" class="qa-recording-panel">
            <div class="qa-recording-top">
              <span class="qa-recording-dot"></span>
              <span class="qa-recording-label">录音中...</span>
              <span class="qa-recording-timer">{{ recordingTimeStr }}</span>
            </div>
            <div class="qa-recording-tip">请保持语速平缓，发音正确</div>
            <div class="qa-recording-wave">
              <span
                v-for="(h, i) in waveHeights"
                :key="i"
                class="qa-wave-bar"
                :style="{ height: h + 'px' }"
              ></span>
            </div>
          </div>
          <button
            type="button"
            class="qa-press-btn"
            :class="{
              pressing: audioState === 'recording',
              processing: audioState === 'processing',
            }"
            :disabled="audioState === 'processing'"
            @click="toggleRecording"
          >
            <span v-if="audioState === 'processing'">识别中...</span>
            <span v-else-if="audioState === 'recording'">点击 结束</span>
            <span v-else>点击 说话</span>
          </button>
          <div v-if="asrError" class="qa-asr-error">🎤 识别失败，请重试</div>
        </div>
        <a-button
          type="primary"
          class="qa-submit-btn"
          :loading="loading"
          :disabled="!input.trim()"
          @click="submit"
        >问</a-button>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { ref, nextTick, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  getToken,
  clearAuth,
  getUsername,
  streamAsk,
  sendFeedback,
  fetchDailyUsage,
  formatDailyUsageText,
  dailyUsageLevelClass,
  translateAnswer,
  fetchTtsMinimax,
  transcribeAudio,
  ApiHttpError,
} from '../utils/qa4Api.js'
import BibleMessage from './BibleMessage.vue'
import HymnMessage from './HymnMessage.vue'
import {
  createStreamState,
  applyEvent,
  renderCitationsMarkdown,
  decorateAnswerHtml,
  chooseFollowupQuestion,
  truncateHistory,
  formatDirectTitle,
  formatNotFoundMessage,
  planSubquestions,
} from '../utils/streamState.js'

function displaySeries(c) {
  const zh = c.series_zh || ''
  if (zh.includes('补充')) return '补充本'
  if (zh.includes('附')) return '诗歌附'
  if (zh.includes('儿童')) return '儿童诗歌'
  if (zh === '诗歌' || zh === '大本' || !zh) {
    const s = c.series || ''
    if (s === 'sup' || String(s).includes('补充')) return '补充本'
    if (s === 'fu' || String(s).includes('附')) return '诗歌附'
    return '大本'
  }
  return zh
}

const router = useRouter()
const route = useRoute()
if (!getToken()) router.replace('/login')

const messages = ref([])
const input = ref('')
const loading = ref(false)
const dailyUsage = ref({ used: 0, limit: 0 })
const currentUsername = ref(getUsername())
const mainEl = ref(null)
let seq = 1

const examples = [
  '神的经纶的中心是什么？',
  '生命与性情有何关系？',
  '召会是基督的身体，如何理解？',
  '圣灵的膏抹是什么意思？',
  '创世记生命读经第三十篇的重点是什么？',
]

const langOptions = [
  { value: 'zh', label: '简体' },
  { value: 'zh_tw', label: '繁體' },
  { value: 'en', label: 'English' },
]

const avatarText = computed(() => (currentUsername.value || '?').slice(0, 1).toUpperCase())

const voiceMode = ref(false)
const audioState = ref('idle') // idle | recording | processing
const asrError = ref(false)
const recordingSeconds = ref(0)
const waveHeights = ref(Array(12).fill(3))
const recordingTimeStr = computed(() => {
  const s = recordingSeconds.value
  const m = Math.floor(s / 60)
  const r = s % 60
  return `${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}`
})

let mediaRecorder = null
let mediaStream = null
let audioChunks = []
let recordingTimer = null
let audioStopTimer = null
let audioContext = null
let analyserNode = null
let waveAnimFrame = null

const ttsAudio = ref(null)
const ttsMsgId = ref(null)
const ttsPlaying = ref(false)
const ttsPaused = ref(false)
const ttsLoadingId = ref(null)
const ttsTick = ref(0)
let ttsTickTimer = null

const usageDisplayText = computed(() =>
  formatDailyUsageText(dailyUsage.value.used, dailyUsage.value.limit),
)
const usageLevelClass = computed(() =>
  dailyUsageLevelClass(dailyUsage.value.used, dailyUsage.value.limit),
)

async function refreshDailyUsage() {
  try {
    dailyUsage.value = await fetchDailyUsage()
  } catch (_) {
    /* 忽略；鉴权失败由后续请求处理 */
  }
}

function incrementDailyUsageLocal() {
  const { used, limit } = dailyUsage.value
  if (limit <= 0) return
  dailyUsage.value = { used: Math.min(used + 1, limit), limit }
}

onMounted(() => {
  refreshDailyUsage()
})

onBeforeUnmount(() => {
  stopRecordingCleanup()
  stopTTS()
})

/** 管理员路径或 ?dev=1 时显示详情（含 request_id）。 */
const showDevMeta = computed(() => {
  if (route.query.dev === '1' || route.query.dev === 'true') return true
  if (typeof localStorage !== 'undefined' && localStorage.getItem('qa4_admin_token')) return true
  return true // 仍提供「详情」按钮，默认折叠；普通用户可不点开
})

function logout() {
  clearAuth()
  router.push('/login')
}

function goAdmin() {
  router.push('/admin')
}

function newConversation() {
  window.location.reload()
}

function fillExample(ex) {
  input.value = ex
}

function retryLast(m) {
  // 找到该助手消息前一条用户问题
  const idx = messages.value.findIndex((x) => x.id === m.id)
  let q = ''
  for (let i = idx - 1; i >= 0; i--) {
    if (messages.value[i].role === 'user') {
      q = messages.value[i].content || ''
      break
    }
  }
  if (!q.trim()) return
  input.value = q
  submit()
}

function scrollBottom() {
  nextTick(() => {
    if (mainEl.value) mainEl.value.scrollTop = mainEl.value.scrollHeight
  })
}

function historyPayload() {
  const turns = []
  for (let i = 0; i < messages.value.length; i++) {
    const m = messages.value[i]
    if (m.role === 'user') {
      const a = messages.value[i + 1]
      if (a && a.role === 'assistant' && a.plain) {
        turns.push({ question: m.content, answer: a.plain })
      }
    }
  }
  return truncateHistory(turns, 3)
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function renderDirectHtml(directs) {
  return (directs || [])
    .map((d, i) => {
      const title = formatDirectTitle(d, i)
      const open = i === 0 ? 'open' : ''
      return `<details ${open}><summary>${escapeHtml(title)}</summary><pre>${escapeHtml(d.text || d.content || '')}</pre></details>`
    })
    .join('')
}

function updateSubqProgress(asst, st) {
  const prog = {}
  for (const s of st.steps || []) {
    if (s.subq != null) {
      prog[s.subq] = s.note || `步骤${s.step}`
    }
    if (s.progress && s.progress.done != null) {
      const n = planSubquestions(st.plan).length
      for (let i = 0; i < n; i++) {
        if (!prog[i]) prog[i] = i < s.progress.done ? '完成' : '进行中'
      }
    }
  }
  asst.subqProgress = prog
}

function displayHtml(m) {
  if (m.currentLang && m.currentLang !== 'zh' && m.translatedHtml) return m.translatedHtml
  return m.html || ''
}

function displayBib(m) {
  if (m.currentLang && m.currentLang !== 'zh' && m.translatedBib != null) return m.translatedBib
  return m.bibliography || ''
}

function displayPlain(m) {
  if (m.currentLang && m.currentLang !== 'zh' && m.translatedPlain) return m.translatedPlain
  return m.notFoundMsg || m.plain || ''
}

function sourceLines(m) {
  const bib = (m.bibliography || '').trim()
  if (!bib) return []
  return bib.split(/\n+/).map((s) => s.trim()).filter(Boolean)
}

async function submit() {
  const q = input.value.trim()
  if (!q || loading.value) return
  input.value = ''
  asrError.value = false
  const uid = seq++
  const aid = seq++
  messages.value.push({ id: uid, role: 'user', content: q })
  const asst = {
    id: aid,
    role: 'assistant',
    loading: true,
    stepHint: '',
    plan: null,
    subqList: [],
    subqProgress: {},
    html: '',
    plain: '',
    bibliography: '',
    directHtml: '',
    intent: null,
    verse: null,
    verses: null,
    queryType: 'verse',
    bibleGenerating: false,
    hymnData: null,
    hymnGenerating: false,
    choose: null,
    doneMeta: null,
    notFoundMsg: '',
    showDetail: false,
    error: null,
    feedback: null,
    feedbackSubmitting: false,
    copied: false,
    currentLang: 'zh',
    translating: false,
    translatedPlain: '',
    translatedHtml: '',
    translatedBib: '',
    translatedAnswers: {},
    question: q,
  }
  messages.value.push(asst)
  loading.value = true
  let st = createStreamState()
  try {
    await streamAsk(q, historyPayload(), (ev) => {
      st = applyEvent(st, ev)
      if (ev.event === 'step') {
        asst.stepHint = `步骤 ${ev.step}` + (ev.subq != null ? ` · 子问题 ${ev.subq}` : '')
        updateSubqProgress(asst, st)
      }
      if (ev.event === 'plan') {
        asst.plan = ev
        asst.subqList = planSubquestions(ev)
      }
      if (ev.event === 'token' || ev.event === 'done') {
        const cites = (st.done && st.done.citations) || []
        const { body, bibliography } = renderCitationsMarkdown(st.text, cites)
        asst.html = decorateAnswerHtml(body)
        asst.plain = st.text
        asst.bibliography = bibliography
      }
      if (ev.event === 'direct') {
        asst.directHtml = renderDirectHtml(st.directs)
      }
      if (ev.event === 'verse_data') {
        asst.intent = 'bible'
        asst.bibleGenerating = true
        const d = st.verseData
        if (d && Array.isArray(d.verses)) {
          asst.verses = d.verses
          asst.verse = null
          asst.queryType = d.query_type || 'range'
        } else {
          asst.verse = d
          asst.verses = null
          asst.queryType = 'verse'
        }
      }
      if (ev.event === 'hymn_data') {
        asst.intent = 'hymn'
        asst.hymnGenerating = true
        asst.hymnData = st.hymnData
      }
      if (ev.event === 'choose') asst.choose = ev
      if (ev.event === 'error') asst.error = ev.message || '出错'
      if (ev.event === 'done') {
        asst.doneMeta = ev
        asst.loading = false
        asst.bibleGenerating = false
        asst.hymnGenerating = false
        incrementDailyUsageLocal()
        if (ev.not_found) {
          asst.notFoundMsg = formatNotFoundMessage(ev, st.text)
          asst.html = ''
        }
      }
      // 经文/诗歌不强制滚到底，便于读折叠区
      if (asst.intent !== 'bible' && asst.intent !== 'hymn') scrollBottom()
    })
    refreshDailyUsage()
  } catch (e) {
    const msg = e.message || String(e)
    asst.error = msg
    if (e instanceof ApiHttpError && e.status === 429) {
      message.warning(msg || '今日问答次数已达上限，请明天再来')
      refreshDailyUsage()
    }
  } finally {
    asst.loading = false
    loading.value = false
    scrollBottom()
  }
}

function pickChoose(c) {
  input.value = chooseFollowupQuestion(c)
  submit()
}

async function vote(m, v) {
  if (m.feedback != null || m.feedbackSubmitting) return
  const rid = m.doneMeta && m.doneMeta.request_id
  if (!rid) return
  m.feedbackSubmitting = true
  try {
    await sendFeedback(rid, v)
    m.feedback = v
  } catch (e) {
    message.error((e && e.message) || '反馈失败')
  } finally {
    m.feedbackSubmitting = false
  }
}

async function copyAnswer(m) {
  const body = displayPlain(m)
  const bib = displayBib(m)
  const t = `${body}\n\n${bib}`.trim()
  try {
    await navigator.clipboard.writeText(t)
    m.copied = true
    setTimeout(() => {
      m.copied = false
    }, 1500)
  } catch (_) {
    message.error('复制失败')
  }
}

async function switchLang(m, lang) {
  if (!m || m.translating) return
  if (lang === m.currentLang) return
  stopTTS()
  if (lang === 'zh') {
    m.currentLang = 'zh'
    m.translatedPlain = ''
    m.translatedHtml = ''
    m.translatedBib = ''
    return
  }
  if (m.translatedAnswers && m.translatedAnswers[lang]) {
    const cached = m.translatedAnswers[lang]
    m.translatedPlain = cached.answer || ''
    m.translatedHtml = decorateAnswerHtml(m.translatedPlain)
    m.translatedBib = Array.isArray(cached.sources) ? cached.sources.join('\n') : m.bibliography || ''
    m.currentLang = lang
    return
  }
  const text = m.plain || m.notFoundMsg || ''
  if (!text.trim()) return
  m.translating = true
  try {
    const cacheKey = (m.doneMeta && m.doneMeta.request_id) || ''
    const data = await translateAnswer({
      text,
      sources: sourceLines(m),
      targetLang: lang,
      question: m.question || '',
      cacheKey,
    })
    const answer = data.answer || data.text || ''
    const sources = Array.isArray(data.sources) ? data.sources : []
    m.translatedAnswers[lang] = { answer, sources }
    m.translatedPlain = answer
    m.translatedHtml = decorateAnswerHtml(answer)
    m.translatedBib = sources.length ? sources.join('\n') : m.bibliography || ''
    m.currentLang = lang
  } catch (e) {
    message.error((e && e.message) || '翻译失败')
  } finally {
    m.translating = false
  }
}

function ttsState(m) {
  if (ttsLoadingId.value === m.id) return 'loading'
  if (ttsMsgId.value === m.id && ttsPlaying.value) return 'playing'
  if (ttsMsgId.value === m.id && ttsPaused.value) return 'paused'
  return 'idle'
}

function ttsIdleLabel(m) {
  if (m.currentLang === 'en') return '🔊 Listen'
  if (m.currentLang === 'zh_tw') return '🔊 朗讀'
  return '🔊 朗读'
}

function ttsTitle(m) {
  const s = ttsState(m)
  if (s === 'loading') return '生成中…'
  if (s === 'playing') return m.currentLang === 'en' ? 'Pause' : m.currentLang === 'zh_tw' ? '暫停' : '暂停'
  if (s === 'paused') return m.currentLang === 'en' ? 'Continue' : '继续'
  return m.currentLang === 'en' ? 'Read' : m.currentLang === 'zh_tw' ? '朗讀' : '朗读'
}

function formatAudioTime(sec) {
  if (!Number.isFinite(sec) || sec < 0) return '0:00'
  const s = Math.floor(sec)
  const m = Math.floor(s / 60)
  const r = s % 60
  return `${m}:${String(r).padStart(2, '0')}`
}

function ttsProgress(m) {
  void ttsTick.value
  if (ttsMsgId.value !== m.id || !ttsAudio.value) return ''
  const a = ttsAudio.value
  if (!a.duration || !Number.isFinite(a.duration)) return ''
  return `${formatAudioTime(a.currentTime)} / ${formatAudioTime(a.duration)}`
}

function startTtsTick() {
  if (ttsTickTimer) return
  ttsTickTimer = setInterval(() => {
    ttsTick.value += 1
  }, 250)
}

function stopTtsTick() {
  if (ttsTickTimer) {
    clearInterval(ttsTickTimer)
    ttsTickTimer = null
  }
}

function stopTTS() {
  if (ttsAudio.value) {
    try {
      ttsAudio.value.pause()
      ttsAudio.value.src = ''
    } catch (_) {}
    ttsAudio.value = null
  }
  ttsMsgId.value = null
  ttsPlaying.value = false
  ttsPaused.value = false
  ttsLoadingId.value = null
  stopTtsTick()
}

async function toggleTTS(m) {
  if (ttsMsgId.value === m.id && ttsAudio.value) {
    if (ttsPlaying.value) {
      ttsAudio.value.pause()
      ttsPlaying.value = false
      ttsPaused.value = true
      return
    }
    if (ttsPaused.value) {
      await ttsAudio.value.play()
      ttsPlaying.value = true
      ttsPaused.value = false
      startTtsTick()
      return
    }
  }
  // 与 3.0 一致：简/繁都读简体原文；英文读译文
  const lang = m.currentLang || 'zh'
  const rawText =
    lang === 'en'
      ? m.translatedPlain || (m.translatedAnswers && m.translatedAnswers.en && m.translatedAnswers.en.answer) || m.plain || ''
      : m.plain || m.notFoundMsg || ''
  if (!String(rawText).trim()) return
  stopTTS()
  ttsLoadingId.value = m.id
  try {
    const blob = await fetchTtsMinimax(rawText, lang === 'en' ? 'en' : 'zh')
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    ttsAudio.value = audio
    ttsMsgId.value = m.id
    audio.onended = () => {
      ttsPlaying.value = false
      ttsPaused.value = false
      ttsMsgId.value = null
      stopTtsTick()
      URL.revokeObjectURL(url)
    }
    audio.onerror = () => {
      message.error('朗读播放失败')
      stopTTS()
      URL.revokeObjectURL(url)
    }
    await audio.play()
    ttsPlaying.value = true
    ttsPaused.value = false
    startTtsTick()
  } catch (e) {
    message.error((e && e.message) || '朗读失败')
    stopTTS()
  } finally {
    ttsLoadingId.value = null
  }
}

async function clickMic() {
  if (voiceMode.value) {
    if (audioState.value === 'recording') stopRecordingCleanup()
    voiceMode.value = false
    audioState.value = 'idle'
    asrError.value = false
    return
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    message.warning('当前浏览器不支持录音')
    return
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    stream.getTracks().forEach((t) => t.stop())
    voiceMode.value = true
    asrError.value = false
  } catch (err) {
    const name = (err && err.name) || ''
    if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
      message.warning('未检测到麦克风，请连接麦克风后重试')
    } else if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
      message.warning('请允许麦克风权限后重试')
    } else {
      message.warning('麦克风启动失败，请重试')
    }
  }
}

async function toggleRecording() {
  if (audioState.value === 'processing') return
  if (audioState.value === 'recording') {
    await stopAndTranscribe()
    return
  }
  await startRecording()
}

async function startRecording() {
  asrError.value = false
  if (loading.value || audioState.value !== 'idle') return
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    })
    audioChunks = []
    const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : 'audio/webm'
    mediaRecorder = new MediaRecorder(mediaStream, { mimeType: mime, audioBitsPerSecond: 128000 })
    mediaRecorder.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) audioChunks.push(ev.data)
    }
    mediaRecorder.start()
    audioState.value = 'recording'
    recordingSeconds.value = 0
    recordingTimer = setInterval(() => {
      recordingSeconds.value += 1
    }, 1000)
    try {
      audioContext = new AudioContext()
      const source = audioContext.createMediaStreamSource(mediaStream)
      analyserNode = audioContext.createAnalyser()
      analyserNode.fftSize = 64
      source.connect(analyserNode)
      const dataArray = new Uint8Array(analyserNode.frequencyBinCount)
      const updateWave = () => {
        if (audioState.value !== 'recording') return
        analyserNode.getByteFrequencyData(dataArray)
        waveHeights.value = Array.from({ length: 12 }, (_, i) => {
          const idx = Math.floor((i * dataArray.length) / 12)
          const val = dataArray[idx] || 0
          return Math.max(3, Math.round((val / 255) * 32))
        })
        waveAnimFrame = requestAnimationFrame(updateWave)
      }
      updateWave()
    } catch (_) {
      waveHeights.value = Array(12).fill(8)
    }
    audioStopTimer = setTimeout(() => {
      if (mediaRecorder && mediaRecorder.state === 'recording') stopAndTranscribe()
    }, 60000)
  } catch (_) {
    message.warning('请允许麦克风权限后重试')
    stopRecordingCleanup()
  }
}

function stopRecordingCleanup() {
  if (recordingTimer) {
    clearInterval(recordingTimer)
    recordingTimer = null
  }
  if (audioStopTimer) {
    clearTimeout(audioStopTimer)
    audioStopTimer = null
  }
  if (waveAnimFrame) {
    cancelAnimationFrame(waveAnimFrame)
    waveAnimFrame = null
  }
  analyserNode = null
  if (audioContext) {
    try {
      audioContext.close()
    } catch (_) {}
    audioContext = null
  }
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    try {
      mediaRecorder.stop()
    } catch (_) {}
  }
  mediaRecorder = null
  if (mediaStream) {
    mediaStream.getTracks().forEach((t) => t.stop())
    mediaStream = null
  }
  audioChunks = []
  recordingSeconds.value = 0
  waveHeights.value = Array(12).fill(3)
}

async function stopAndTranscribe() {
  if (!mediaRecorder || audioState.value !== 'recording') return
  audioState.value = 'processing'
  if (recordingTimer) {
    clearInterval(recordingTimer)
    recordingTimer = null
  }
  if (audioStopTimer) {
    clearTimeout(audioStopTimer)
    audioStopTimer = null
  }
  if (waveAnimFrame) {
    cancelAnimationFrame(waveAnimFrame)
    waveAnimFrame = null
  }
  if (audioContext) {
    try {
      audioContext.close()
    } catch (_) {}
    audioContext = null
  }
  analyserNode = null
  waveHeights.value = Array(12).fill(3)
  const blob = await new Promise((resolve) => {
    const mr = mediaRecorder
    mr.onstop = () => {
      resolve(new Blob(audioChunks, { type: mr.mimeType || 'audio/webm' }))
    }
    try {
      mr.stop()
    } catch (_) {
      resolve(new Blob())
    }
  })
  if (mediaStream) {
    mediaStream.getTracks().forEach((t) => t.stop())
    mediaStream = null
  }
  mediaRecorder = null
  try {
    if (!blob || blob.size < 100) throw new Error('录音过短')
    const text = await transcribeAudio(blob)
    if (!String(text).trim()) throw new Error('未识别到内容')
    input.value = String(text).trim()
    voiceMode.value = false
    audioState.value = 'idle'
    asrError.value = false
    await submit()
  } catch (_) {
    asrError.value = true
    audioState.value = 'idle'
    setTimeout(() => {
      asrError.value = false
    }, 3000)
  }
}
</script>

<style scoped>
.qa-root {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--color-bg);
}

.qa-header {
  flex-shrink: 0;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface);
}
.qa-header-inner {
  max-width: min(860px, 90vw);
  margin: 0 auto;
  padding: 14px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.qa-header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.qa-daily-usage {
  font-size: 13px;
  color: var(--color-text-secondary);
  white-space: nowrap;
  user-select: none;
}
.qa-daily-usage--warn { color: #e6a23c; }
.qa-daily-usage--danger { color: #f5222d; }
.qa-new-chat-btn {
  border: 1px solid var(--color-border);
  background: #fff;
  border-radius: 16px;
  padding: 4px 12px;
  font-size: 13px;
  color: var(--color-text-secondary);
  cursor: pointer;
  line-height: 1.5;
}
.qa-new-chat-btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: #fdf8ee;
}
.qa-logo { display: flex; align-items: center; gap: 8px; }
.qa-logo-text {
  font-size: 30px;
  font-weight: 400;
  color: var(--color-primary);
  letter-spacing: 0.05em;
  font-family: 'KaiTi', 'Kaiti SC', 'STKaiti', serif;
}
.qa-user-avatar {
  cursor: pointer;
  background-color: #8b6914;
  user-select: none;
}
:deep(.qa-logout-item) { color: #ff4d4f; }

.qa-main {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 24px;
}

.qa-welcome {
  max-width: 600px;
  margin: 60px auto 0;
  text-align: center;
}
.qa-welcome-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 8px;
}
.qa-welcome-sub {
  font-size: 13px;
  color: #a8a39c;
  font-style: italic;
  margin-bottom: 32px;
}
.qa-example-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: center;
}
.qa-example-chip {
  padding: 8px 16px;
  border: 1px solid var(--color-border);
  border-radius: 20px;
  font-size: 13px;
  color: var(--color-text-secondary);
  cursor: pointer;
  background: var(--color-surface);
  transition: all 0.2s;
}
.qa-example-chip:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: #fdf8ee;
}

.qa-chat {
  max-width: min(860px, 90vw);
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-bottom: 8px;
}
.qa-msg-row { display: flex; width: 100%; }
.qa-msg-row--user { justify-content: flex-end; }
.qa-msg-row--assistant { justify-content: flex-start; }

.qa-bubble {
  border-radius: var(--radius);
  padding: 14px 18px;
  line-height: 1.8;
  font-size: 15px;
}
.qa-bubble-user {
  max-width: 78%;
  background: var(--color-primary);
  color: #fff;
  border-bottom-right-radius: 2px;
  word-break: break-word;
}
.qa-bubble-assistant {
  max-width: 92%;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow);
  border-bottom-left-radius: 2px;
  word-break: break-word;
}

.qa-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--color-text-secondary);
}
.qa-loading-text { font-size: 14px; }

.qa-not-found {
  color: var(--color-text-secondary);
  font-size: 14px;
}
.qa-not-found-icon { margin-right: 6px; }

.qa-request-fail {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
  margin-top: 8px;
}
.qa-request-fail-text {
  color: var(--color-text-secondary);
  font-size: 14px;
}
.qa-retry-btn {
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-primary);
  border-radius: 8px;
  padding: 4px 14px;
  cursor: pointer;
  font-size: 14px;
}
.qa-retry-btn:disabled { opacity: 0.6; cursor: not-allowed; }

.qa-answer-body {
  color: var(--color-text);
  margin-bottom: 12px;
}
.qa-answer-body :deep(.a-title) {
  font-size: 1.05em;
  font-weight: 700;
  margin: 0 0 12px 0;
  color: var(--color-text);
  line-height: 1.4;
}
.qa-answer-body :deep(.a-sub) {
  font-size: 1.02em;
  font-weight: 600;
  margin: 0.85em 0 0.35em;
  line-height: 1.4;
  color: var(--color-text);
}
.qa-answer-body :deep(.quote) {
  background: #fff8e6;
}
.qa-answer-body :deep(.induction) {
  color: var(--color-text-secondary);
}
.qa-answer-body :deep(.unverified) {
  background: #ffe0e0;
}
.qa-answer-body :deep(sup.cite),
.qa-answer-body :deep(.cite) {
  font-size: 10px;
  vertical-align: super;
  color: var(--color-text-secondary);
  margin-left: 1px;
}
.qa-answer-fade {
  animation: qa-answer-fadein 0.2s ease;
}
@keyframes qa-answer-fadein {
  from { opacity: 0; }
  to { opacity: 1; }
}

.qa-sources {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border);
}
.qa-sources-title {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-bottom: 6px;
  font-weight: 600;
  letter-spacing: 0.05em;
}
.qa-sources-body {
  margin: 0;
  white-space: pre-wrap;
  font-size: 12px;
  color: var(--color-text-secondary);
  font-family: inherit;
  line-height: 1.6;
}

.qa-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
.qa-meta-badge {
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 10px;
  font-weight: 600;
}
.qa-meta-cache {
  background: #e6f4ff;
  color: #1677ff;
}
.qa-meta-degraded {
  background: #fff7e6;
  color: #d48806;
}
.qa-meta-time {
  font-size: 11px;
  color: var(--color-text-secondary);
}

.qa-plan {
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px dashed var(--color-border);
}
.qa-plan-type {
  font-size: 13px;
  color: var(--color-text-secondary);
}
.qa-premise {
  margin-top: 6px;
  padding: 8px 10px;
  background: #faf5ea;
  border-left: 3px solid var(--color-primary);
  color: var(--color-text);
  font-size: 14px;
}
.muted { color: var(--color-text-secondary); font-size: 13px; }
.tag {
  display: inline-block;
  margin-left: 6px;
  padding: 0 6px;
  font-size: 12px;
  border: 1px solid var(--color-border);
  border-radius: 3px;
  background: #f5f5f5;
  color: var(--color-text-secondary);
}
.tag.sens { border-color: #c88; background: #fff0f0; }
.tag.complex { border-color: #88a; background: #f0f3ff; }
.subq-list { margin: 8px 0 0; padding-left: 1.2em; font-size: 14px; }

.choose { margin-top: 8px; }
.choose-title { font-weight: 600; margin-bottom: 8px; color: var(--color-text); }
.choose-btn {
  display: block;
  width: 100%;
  text-align: left;
  margin: 6px 0;
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: #fafafa;
  cursor: pointer;
}
.choose-btn:hover {
  background: #fdf8ee;
  border-color: var(--color-primary);
}
.choose-main { display: block; font-weight: 600; color: var(--color-text); }
.choose-name { font-weight: 400; color: var(--color-text-secondary); margin-left: 6px; }
.choose-snip { display: block; margin-top: 4px; font-size: 13px; color: var(--color-text-secondary); }
.hymn-ministry { margin-top: 8px; }
.detail-line { margin-top: 6px; }
.linkish {
  background: none;
  border: none;
  color: var(--color-link);
  text-decoration: underline;
  cursor: pointer;
  padding: 0;
  font-size: 13px;
}
.detail-box {
  margin-top: 4px;
  font-family: ui-monospace, monospace;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.qa-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}
.qa-actions-row1 {
  display: flex;
  align-items: center;
  gap: 8px;
}
.qa-feedback-btn {
  border: 1px solid var(--color-border);
  background: #fff;
  border-radius: 14px;
  padding: 2px 10px;
  cursor: pointer;
  font-size: 14px;
  line-height: 1.6;
  transition: all 0.2s;
}
.qa-feedback-btn.is-selected {
  border-color: var(--color-primary);
  background: #f5ead2;
  color: #7a5a0f;
}
.qa-feedback-btn.is-muted { opacity: 0.45; }
.qa-feedback-btn:disabled { cursor: not-allowed; }
.qa-copy-btn {
  min-width: 84px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.qa-action-row2 {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  flex-wrap: wrap;
}
.qa-lang-toggle {
  display: flex;
  align-items: center;
  border: 1px solid var(--color-border);
  border-radius: 20px;
  overflow: hidden;
  background: #fff;
}
.qa-lang-toggle-btn {
  border: none;
  background: transparent;
  padding: 6px 18px;
  font-size: 14px;
  color: var(--color-text-secondary);
  cursor: pointer;
  line-height: 1.6;
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.qa-lang-toggle-btn:not(:last-child) {
  border-right: 1px solid var(--color-border);
}
.qa-lang-toggle-btn:hover:not(:disabled):not(.is-active) {
  background: #faf5ea;
  color: var(--color-primary);
}
.qa-lang-toggle-btn.is-active {
  background: #f5ead2;
  color: #7a5a0f;
  font-weight: 600;
}
.qa-lang-toggle-btn:disabled { cursor: not-allowed; }
.qa-tts-btn {
  flex-shrink: 0;
  background: none;
  border: 1px solid #d9d9d9;
  border-radius: 16px;
  padding: 2px 10px;
  font-size: 15px;
  cursor: pointer;
  color: #666;
}
.qa-tts-btn--minimax {
  color: var(--color-primary);
  opacity: 0.85;
}
.qa-tts-btn:hover:not(:disabled) { background: #f5f5f5; }
.qa-tts-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.qa-disclaimer {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--color-border);
  font-size: 12px;
  color: var(--color-disclaimer);
  font-style: italic;
}

.qa-footer {
  flex-shrink: 0;
  border-top: 1px solid var(--color-border);
  background: var(--color-surface);
  padding: 16px 24px 20px;
}
.qa-input-wrap {
  max-width: min(860px, 90vw);
  margin: 0 auto;
  display: flex;
  flex-direction: row;
  gap: 8px;
  align-items: center;
}
.qa-textarea {
  flex: 1;
  min-width: 0;
  border-radius: var(--radius) !important;
  font-family: inherit !important;
  font-size: 15px !important;
  resize: none;
}
.qa-submit-btn {
  height: 40px;
  min-width: 80px;
  padding: 0 18px;
  border-radius: var(--radius) !important;
  font-size: 16px;
  font-weight: 600;
  flex-shrink: 0;
  align-self: center;
}
.qa-mic-btn {
  flex-shrink: 0;
  align-self: center;
  background: #fff1f0;
  border: none;
  border-radius: 50%;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #ff4d4f;
}
.qa-mic-btn:hover,
.qa-mic-btn.active { background: #ffd6d6; }
.qa-mic-btn.recording { animation: mic-pulse 1s ease-in-out infinite; }
.qa-mic-btn.processing { color: #bbb; cursor: default; }
.qa-mic-btn:disabled { opacity: 0.6; cursor: not-allowed; }
@keyframes mic-pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.08); opacity: 0.85; }
}
.qa-voice-area {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.qa-asr-error {
  color: #ff4d4f;
  font-size: 13px;
  text-align: center;
}
.qa-press-btn {
  width: 100%;
  height: 40px;
  border-radius: 20px;
  border: 1.5px solid #d9d9d9;
  background: #fafafa;
  font-size: 15px;
  color: #555;
  cursor: pointer;
}
.qa-press-btn.pressing {
  background: #fff1f0;
  border-color: #ff4d4f;
  color: #ff4d4f;
}
.qa-press-btn.processing {
  color: #aaa;
  cursor: default;
}
.qa-press-btn:hover:not(:disabled):not(.pressing) {
  border-color: #aaa;
  background: #f0f0f0;
}
.qa-recording-panel {
  background: #fff;
  border: 1px solid #ffa39e;
  border-radius: 12px;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.qa-recording-top {
  display: flex;
  align-items: center;
  gap: 8px;
}
.qa-recording-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #ff4d4f;
  animation: mic-pulse 1s ease-in-out infinite;
  flex-shrink: 0;
}
.qa-recording-label {
  font-size: 14px;
  color: #ff4d4f;
  font-weight: 500;
  flex: 1;
}
.qa-recording-timer {
  font-size: 14px;
  color: #888;
  font-variant-numeric: tabular-nums;
}
.qa-recording-tip {
  font-size: 12px;
  color: #888;
}
.qa-recording-wave {
  display: flex;
  align-items: center;
  gap: 3px;
  height: 32px;
}
.qa-wave-bar {
  width: 3px;
  border-radius: 2px;
  background: #ff7875;
  display: inline-block;
}

@media (max-width: 768px) {
  .qa-header {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 101;
    padding-top: env(safe-area-inset-top, 0px);
  }
  .qa-header-inner {
    padding: 10px 16px;
    min-height: 48px;
    box-sizing: border-box;
  }
  .qa-logo-text {
    font-size: 22px;
    line-height: 1.25;
  }
  .qa-footer {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    z-index: 100;
    padding: 12px 16px;
    padding-bottom: calc(12px + env(safe-area-inset-bottom, 0px));
  }
  .qa-main {
    box-sizing: border-box;
    padding-left: 16px;
    padding-right: 16px;
    padding-top: calc(12px + env(safe-area-inset-top, 0px) + 56px);
    padding-bottom: calc(max(140px, 32vh) + env(safe-area-inset-bottom, 0px));
    scroll-padding-top: calc(8px + env(safe-area-inset-top, 0px) + 56px);
    scroll-padding-bottom: calc(max(140px, 32vh) + env(safe-area-inset-bottom, 0px));
  }
  .qa-welcome { margin-top: 24px; }
  .qa-bubble-user { max-width: 92%; }
  .qa-bubble-assistant { max-width: 100%; }
  .qa-lang-toggle-btn { padding: 6px 12px; }
}
</style>

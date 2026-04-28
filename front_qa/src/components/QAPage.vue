<template>
  <div class="qa-root">
    <!-- 页头 -->
    <header class="qa-header">
      <div class="qa-header-inner">
        <div class="qa-logo">
          <span class="qa-logo-text">职事信息问答</span>
        </div>
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
    </header>

    <!-- 主体：对话区可滚动 -->
    <main class="qa-main" ref="historyRef">
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
          v-for="msg in messages"
          :key="msg.id"
          :ref="(el) => setMessageRef(msg.id, el)"
          class="qa-msg-row"
          :class="msg.role === 'user' ? 'qa-msg-row--user' : 'qa-msg-row--assistant'"
        >
          <div v-if="msg.role === 'user'" class="qa-bubble qa-bubble-user">
            {{ msg.content }}
          </div>

          <div v-else class="qa-bubble qa-bubble-assistant">
            <div v-if="msg.loading" class="qa-loading">
              <a-spin size="small" />
              <span class="qa-loading-text">正在检索职事信息…</span>
            </div>

            <div v-else-if="!msg.found" class="qa-not-found">
              <span class="qa-not-found-icon">🔍</span>
              以下内容未能在职事信息中找到相关依据。
            </div>

            <template v-else>
              <div class="qa-answer-body" v-html="renderAnswer(msg.answer)"></div>

              <div v-if="msg.sources && msg.sources.length" class="qa-sources">
                <div class="qa-sources-title">引用书目</div>
                <div class="qa-sources-list">
                  <div
                    v-for="(src, srcIdx) in msg.sources"
                    :key="srcIdx + '-' + src"
                    class="qa-source-item"
                  >
                    <span class="qa-source-name">{{ src }}</span>
                  </div>
                </div>
              </div>

              <div class="qa-meta" v-if="!msg.streaming">
                <span v-if="msg.cache_hit" class="qa-meta-badge qa-meta-cache">缓存</span>
                <span class="qa-meta-time">{{ msg.elapsed }}s</span>
                <span class="qa-meta-cost">${{ Number(msg.cost || 0).toFixed(4) }}</span>
              </div>

              <div
                v-if="!msg.streaming"
                class="qa-feedback"
              >
                <button
                  class="qa-feedback-btn qa-copy-btn"
                  :disabled="msg.copied"
                  @click="copyAnswer(msg)"
                >
                  <svg
                    v-if="msg.copied"
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
                  <span v-if="msg.copied">copied</span>
                  <svg
                    v-if="!msg.copied"
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
                  <span v-if="!msg.copied">copy</span>
                </button>
                <button
                  v-if="msg.found"
                  class="qa-feedback-btn"
                  :class="{
                    'is-selected': msg.feedback === 1,
                    'is-muted': msg.feedback === -1,
                  }"
                  :disabled="msg.feedback !== null || msg.feedbackSubmitting"
                  @click="submitFeedback(msg, 1)"
                >
                  👍
                </button>
                <button
                  v-if="msg.found"
                  class="qa-feedback-btn"
                  :class="{
                    'is-selected': msg.feedback === -1,
                    'is-muted': msg.feedback === 1,
                  }"
                  :disabled="msg.feedback !== null || msg.feedbackSubmitting"
                  @click="submitFeedback(msg, -1)"
                >
                  👎
                </button>
              </div>
            </template>

            <div v-if="!msg.loading" class="qa-disclaimer">
              以上答案由 AI 根据职事信息归纳生成，建议对照原文查证。
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- 输入区 -->
    <footer class="qa-footer">
      <div class="qa-input-wrap">
        <a-textarea
          :key="textareaKey"
          ref="textareaRef"
          v-model:value="question"
          :placeholder="'请输入问题'"
          :auto-size="{ minRows: 1, maxRows: 5 }"
          :maxlength="500"
          :disabled="loading"
          class="qa-textarea"
          @keydown.enter.exact.prevent="submit"
        />
        <button
          class="qa-mic-btn"
          :class="audioState"
          :disabled="loading"
          @click="toggleRecording"
        >
          <svg
            v-if="audioState !== 'recording'"
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
            <rect x="6" y="6" width="12" height="12" rx="2" ry="2"></rect>
          </svg>
        </button>
        <a-button
          type="primary"
          :loading="loading"
          :disabled="!question.trim()"
          class="qa-submit-btn"
          @click="submit"
        >问</a-button>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { marked } from 'marked'
import { message } from 'ant-design-vue'

const router = useRouter()
const question = ref('')
const textareaKey = ref(0)
const loading = ref(false)
const textareaRef = ref(null)
const currentUsername = ref(localStorage.getItem('qa_username') || '')
/** 发往接口的最近 3 轮 { question, answer } */
const history = ref([])
/** 界面气泡：user / assistant，assistant 含 loading 与展示字段 */
const messages = ref([])
const historyRef = ref(null)

let nextMessageId = 0
const messageRefMap = new Map()

const examples = [
  '神的经纶的中心是什么？',
  '生命与性情有何关系？',
  '召会是基督的身体，如何理解？',
  '圣灵的膏抹是什么意思？',
  '创世记生命读经第三十篇的重点是什么？',
]

function fillExample(ex) {
  question.value = ex
}

const avatarText = (currentUsername.value || '?').slice(0, 1).toUpperCase()

function goAdmin() {
  router.push('/admin')
}

function logout() {
  localStorage.removeItem('qa_token')
  localStorage.removeItem('qa_username')
  router.replace('/login')
}

function renderAnswer(text) {
  if (!text) return ''
  const parts = text.split('【引用书目】')
  const body = parts[0].trim()
  return marked.parse(body)
}

// 打字机队列
const typewriterQueue = ref([])
let typewriterTimer = null
const audioState = ref('idle') // 'idle' | 'recording' | 'processing'
let mediaRecorder = null
let audioChunks = []
let audioStopTimer = null

function startTypewriter(targetMsg) {
  if (typewriterTimer) return
  typewriterTimer = setInterval(() => {
    if (typewriterQueue.value.length === 0) return
    const char = typewriterQueue.value.shift()
    const idx = messages.value.findIndex((m) => m.id === targetMsg.id)
    if (idx !== -1) {
      messages.value[idx].answer += char
    }
  }, 20) // 每 20ms 一个字符
}

function stopTypewriter() {
  if (typewriterTimer) {
    clearInterval(typewriterTimer)
    typewriterTimer = null
  }
  typewriterQueue.value = []
}

async function uploadAudio() {
  audioState.value = 'processing'
  try {
    const token = localStorage.getItem('qa_token') || ''
    if (!token) throw new Error('no token')
    const blob = new Blob(audioChunks, { type: 'audio/webm' })
    const formData = new FormData()
    formData.append('file', blob, 'recording.webm')
    const res = await fetch('/api/qa/asr', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
      },
      body: formData,
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    const text = (data?.text || '').trim()
    if (text) {
      question.value = question.value.trim()
        ? `${question.value.trim()} ${text}`
        : text
      await nextTick()
      if (textareaRef.value?.focus) {
        textareaRef.value.focus()
      } else if (textareaRef.value?.resizableTextArea?.textArea?.focus) {
        textareaRef.value.resizableTextArea.textArea.focus()
      }
    }
  } catch (e) {
    message.error('语音识别失败，请重试')
  } finally {
    audioState.value = 'idle'
    audioChunks = []
  }
}

async function toggleRecording() {
  if (loading.value || audioState.value === 'processing') return
  if (audioState.value === 'recording') {
    if (audioStopTimer) {
      clearTimeout(audioStopTimer)
      audioStopTimer = null
    }
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      mediaRecorder.stop()
    }
    return
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    audioChunks = []
    mediaRecorder = new MediaRecorder(stream)
    mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        audioChunks.push(event.data)
      }
    }
    mediaRecorder.onstop = async () => {
      if (audioStopTimer) {
        clearTimeout(audioStopTimer)
        audioStopTimer = null
      }
      stream.getTracks().forEach((track) => track.stop())
      await uploadAudio()
    }
    mediaRecorder.start()
    audioState.value = 'recording'
    audioStopTimer = setTimeout(() => {
      if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop()
      }
    }, 60000)
  } catch (e) {
    message.warning('请允许麦克风权限后重试')
  }
}

async function submit() {
  const q = question.value.trim()
  if (!q || loading.value) return

  question.value = ''
  textareaKey.value += 1
  loading.value = true
  await nextTick()

  messages.value.push({
    id: ++nextMessageId,
    role: 'user',
    content: q,
    loading: false,
  })

  const assistantMsg = {
    id: ++nextMessageId,
    role: 'assistant',
    content: '',
    loading: true,
    streaming: true,
    answer: '',
    /** 流式过程中先视为有答案，避免 loading 结束后短暂出现「未找到」；最终以 done / error 为准 */
    found: true,
    sources: [],
    concepts: [],
    cache_hit: false,
    elapsed: 0,
    cost: 0,
    request_id: '',
    question: q,
    feedback: null,
    feedbackSubmitting: false,
    copied: false,
    /** 流式遇到「【引用书目】」后为 true，后续 token 不再入打字机队列 */
    _bodyDone: false,
  }
  messages.value.push(assistantMsg)

  const assistantRow = () => {
    const i = messages.value.findIndex((m) => m.id === assistantMsg.id)
    return i !== -1 ? messages.value[i] : assistantMsg
  }

  await scrollToBottom()

  // 追问补全：若当前问题疑似追问（不含书名但含篇章词），用上一轮问题的书名补全
  let finalQuestion = q
  const lastTurn = history.value[history.value.length - 1]
  let hasChapter = false
  let hasBookName = false
  let isTooShort = false
  let bookMatch = null
  if (lastTurn) {
    hasChapter = /第?[零一二三四五六七八九十百千]+[篇章课]|第\d+[篇章课]/.test(finalQuestion)
    hasBookName =
      /文集|读经|训练|特会|总论|课程|福音|使徒|罗马|创世|出埃及|利未|民数|申命|约书亚|士师|路得|撒母耳|列王|历代|以斯|约伯|诗篇|箴言|传道|雅歌|以赛亚|耶利米|以西结|但以理|何西阿|约珥|阿摩司|俄巴底|约拿|弥迦|那鸿|哈巴谷|西番雅|哈该|撒迦利亚|玛拉基|马太|马可|路加|约翰|歌林多|加拉太|以弗所|腓利比|歌罗西|帖撒|提摩太|提多|腓利门|希伯来|雅各|彼得|犹大|启示/.test(
        finalQuestion,
      )
    isTooShort = finalQuestion.length <= 15
    if (hasChapter && !hasBookName && isTooShort) {
      const prevQ = lastTurn.question
      bookMatch = prevQ.match(/^(.+?)(?:第[零一二三四五六七八九十百千\d]+[篇章课]|的)/)
      if (bookMatch && bookMatch[1].length >= 4) {
        finalQuestion = bookMatch[1].trim() + finalQuestion
      }
    }
  }

  try {
    const sendTime = Date.now()
    let firstTokenReceived = false

    const token = localStorage.getItem('qa_token') || ''
    const response = await fetch('/api/qa/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        question: finalQuestion,
        skip_cache: false,
        debug: false,
        history: history.value.map((h) => ({
          question: h.question,
          answer: h.answer,
        })),
      }),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

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
          if (!raw) continue
          let chunk
          try {
            chunk = JSON.parse(raw)
          } catch {
            continue
          }
          if (chunk.type === 'token') {
            if (!firstTokenReceived) {
              firstTokenReceived = true
              const row = assistantRow()
              if (row) {
                row.elapsed = ((Date.now() - sendTime) / 1000).toFixed(1)
              }
              await scrollToMessageTop(assistantMsg.id - 1)
            }
            const idx = messages.value.findIndex((m) => m.id === assistantMsg.id)
            if (idx !== -1) {
              messages.value[idx].loading = false
            }
            const text = chunk.text || ''
            const row = assistantRow()
            if (row && row._bodyDone) {
              // 已进入书目区，不再打字
            } else {
              let bodyText = text
              if (text.includes('【引用书目】')) {
                bodyText = text.split('【引用书目】')[0]
                if (row) row._bodyDone = true
              }
              for (const char of bodyText) {
                typewriterQueue.value.push(char)
              }
              startTypewriter(assistantMsg)
            }
          } else if (chunk.type === 'done') {
            await new Promise((resolve) => {
              const wait = setInterval(() => {
                if (typewriterQueue.value.length === 0) {
                  clearInterval(wait)
                  resolve()
                }
              }, 50)
            })
            stopTypewriter()
            const row = assistantRow()
            row.found = chunk.found ?? true
            if (!row.answer) {
              row.answer = chunk.answer || ''
            }
            row.sources = chunk.sources || []
            row.concepts = chunk.concepts || []
            row.cache_hit = chunk.cache_hit ?? false
            row.request_id = chunk.request_id || ''
            if (!firstTokenReceived) {
              row.elapsed = ((chunk.elapsed_ms || 0) / 1000).toFixed(1)
            }
            row.cost = chunk.cost || 0
            row.loading = false
            row.streaming = false
          } else if (chunk.type === 'error') {
            stopTypewriter()
            const row = assistantRow()
            row.answer = '请求失败，请稍后重试。'
            row.found = false
            row.loading = false
            row.streaming = false
          }
        }
      }
    }
  } catch (e) {
    stopTypewriter()
    const r = assistantRow()
    r.found = false
    r.answer = '请求失败，请稍后重试。'
  } finally {
    stopTypewriter()
    const r = assistantRow()
    r.loading = false
    r.streaming = false
    loading.value = false
    question.value = ''
    // 存补全后的问句，便于下一轮从 history 提取书名再做追问补全（气泡仍用上面的 q）
    history.value.push({
      question: finalQuestion,
      answer: r.answer || '',
    })
    history.value = history.value.slice(-3)
    await nextTick()
  }
}

async function submitFeedback(msg, rating) {
  if (!msg || msg.feedback !== null || msg.feedbackSubmitting) return
  const token = localStorage.getItem('qa_token') || ''
  if (!token) return

  msg.feedbackSubmitting = true
  try {
    const res = await fetch('/api/qa/feedback', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        request_id: msg.request_id || '',
        question: msg.question || '',
        answer: msg.answer || '',
        rating,
      }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    msg.feedback = rating
  } catch (e) {
    console.error('submit feedback failed', e)
  } finally {
    msg.feedbackSubmitting = false
  }
}

function stripMarkdown(text) {
  return text
    .replace(/\*\*(.*?)\*\*/g, '$1')   // **粗体** -> 粗体
    .replace(/\*(.*?)\*/g, '$1')        // *斜体* -> 斜体
    .replace(/^---+$/gm, '——')          // --- 分隔线 -> ——
    .replace(/^#{1,6}\s+/gm, '')        // ## 标题 -> 去掉#
    .replace(/`(.*?)`/g, '$1')          // `代码` -> 代码
    .trim()
}

async function copyAnswer(msg) {
  if (!msg || msg.copied) return
  try {
    const cleanAnswer = stripMarkdown(msg.answer || '')
    const sourcesText = msg.sources && msg.sources.length
      ? '\n\n【引用书目】\n' + msg.sources.join('\n')
      : ''
    const fullText = cleanAnswer + sourcesText
    await navigator.clipboard.writeText(fullText)
    msg.copied = true
    setTimeout(() => {
      msg.copied = false
    }, 1500)
  } catch (e) {
    console.error('copy answer failed', e)
  }
}

async function scrollToBottom() {
  await nextTick()
  if (historyRef.value) {
    historyRef.value.scrollTop = historyRef.value.scrollHeight
  }
}

function setMessageRef(id, el) {
  if (el) {
    messageRefMap.set(id, el)
  } else {
    messageRefMap.delete(id)
  }
}

async function scrollToMessageTop(messageId) {
  await nextTick()
  const el = messageRefMap.get(messageId)
  if (el && typeof el.scrollIntoView === 'function') {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}
</script>

<style lang="less" scoped>
.qa-root {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--color-bg);
}

/* 页头 */
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
.qa-logo {
  display: flex;
  align-items: center;
  gap: 8px;
}
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
:deep(.qa-logout-item) {
  color: #ff4d4f;
}

/* 主体：中间可滚动 */
.qa-main {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 24px;
}

/* 欢迎区 */
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
  transition: all 0.2s;
  background: var(--color-surface);
  &:hover {
    border-color: var(--color-primary);
    color: var(--color-primary);
    background: #fdf8ee;
  }
}

/* 对话流 */
.qa-chat {
  max-width: min(860px, 90vw);
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-bottom: 8px;
}

.qa-msg-row {
  display: flex;
  width: 100%;
}
.qa-msg-row--user {
  justify-content: flex-end;
}
.qa-msg-row--assistant {
  justify-content: flex-start;
}

/* 气泡 */
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

/* 加载 */
.qa-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--color-text-secondary);
}
.qa-loading-text { font-size: 14px; }

/* 未找到 */
.qa-not-found {
  color: var(--color-text-secondary);
  font-size: 14px;
}
.qa-not-found-icon { margin-right: 6px; }

/* 答案正文 */
.qa-answer-body {
  color: var(--color-text);
  margin-bottom: 12px;
}

/* 引用书目 */
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
.qa-sources-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}
.qa-source-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 4px 0;
  border-bottom: 1px solid var(--color-border);
  &:last-child { border-bottom: none; }
}
.qa-source-name {
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

/* 元信息 */
.qa-meta {
  display: flex;
  align-items: center;
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
.qa-meta-time, .qa-meta-cost {
  font-size: 11px;
  color: var(--color-text-secondary);
}

.qa-feedback {
  margin-top: 8px;
  display: flex;
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
.qa-feedback-btn.is-muted {
  opacity: 0.45;
}
.qa-feedback-btn:disabled {
  cursor: not-allowed;
}
.qa-copy-btn {
  min-width: 84px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

/* 免责说明 */
.qa-disclaimer {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--color-border);
  font-size: 12px;
  color: var(--color-disclaimer);
  font-style: italic;
}

/* 输入区 */
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
  gap: 10px;
  align-items: flex-end;
}
.qa-textarea {
  flex: 1;
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
}
.qa-mic-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 6px;
  border-radius: 6px;
  color: #bbb;
  transition: color 0.2s;
  flex-shrink: 0;
}
.qa-mic-btn:hover { color: #666; }
.qa-mic-btn.recording {
  color: #ff4d4f;
  animation: mic-pulse 1s ease-in-out infinite;
}
.qa-mic-btn.processing { color: #bbb; cursor: default; }
@keyframes mic-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.qa-input-hint {
  max-width: min(860px, 90vw);
  margin: 6px auto 0;
  font-size: 11px;
  color: var(--color-text-secondary);
  text-align: right;
}

@media (max-width: 768px) {
  /* 顶栏固定：与底栏输入区对称，中间主区域单独滚动 */
  .qa-header {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 101;
    background: var(--color-surface);
    border-bottom: 1px solid var(--color-border);
    /* 刘海屏安全区 */
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
    background: var(--color-bg);
    padding: 12px 16px;
    padding-bottom: calc(12px + env(safe-area-inset-bottom, 0px));
    border-top: 1px solid var(--color-border);
  }

  /*
   * 主区域预留：必须 ≥ 实际固定顶栏/底栏高度，否则首尾文字会被遮住。
   * 底栏含多行输入时会变高，故底部留白加大并用 min 兜底。
   */
  .qa-main {
    box-sizing: border-box;
    padding-left: 16px;
    padding-right: 16px;
    padding-top: calc(12px + env(safe-area-inset-top, 0px) + 56px);
    padding-bottom: calc(max(140px, 32vh) + env(safe-area-inset-bottom, 0px));
    scroll-padding-top: calc(8px + env(safe-area-inset-top, 0px) + 56px);
    scroll-padding-bottom: calc(max(140px, 32vh) + env(safe-area-inset-bottom, 0px));
  }

  /* 欢迎区原先 margin-top 较大，与顶栏留白叠加后首屏过空，略收紧 */
  .qa-welcome {
    margin-top: 24px;
  }
}
</style>

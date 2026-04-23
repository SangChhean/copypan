<template>
  <div class="qa-root">
    <!-- 页头 -->
    <header class="qa-header">
      <div class="qa-header-inner">
        <div class="qa-logo">
          <span class="qa-logo-icon">📖</span>
          <span class="qa-logo-text">职事信息问答</span>
        </div>
        <a class="qa-admin-link" href="#/debug" style="margin-right:12px">调试</a>
        <a class="qa-admin-link" href="#/admin">管理</a>
      </div>
    </header>

    <!-- 主体：对话区可滚动 -->
    <main class="qa-main" ref="historyRef">
      <div v-if="messages.length === 0" class="qa-welcome">
        <div class="qa-welcome-title">以自然语言提问</div>
        <div class="qa-welcome-sub">从职事信息中寻找答案</div>
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
                    <span class="qa-source-idx">{{ srcIdx + 1 }}</span>
                    <span class="qa-source-name">{{ src.replace('➡️', '').trim() }}</span>
                  </div>
                </div>
              </div>

              <div class="qa-meta">
                <span v-if="msg.cache_hit" class="qa-meta-badge qa-meta-cache">缓存</span>
                <span class="qa-meta-time">{{ msg.elapsed }}s</span>
                <span class="qa-meta-cost">${{ Number(msg.cost || 0).toFixed(4) }}</span>
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
          v-model:value="question"
          :placeholder="'请输入问题，例如：神的经纶的中心是什么？'"
          :auto-size="{ minRows: 1, maxRows: 5 }"
          :maxlength="500"
          :disabled="loading"
          class="qa-textarea"
          @keydown.enter.exact.prevent="submit"
        />
        <a-button
          type="primary"
          :loading="loading"
          :disabled="!question.trim()"
          class="qa-submit-btn"
          @click="submit"
        >问</a-button>
      </div>
      <div class="qa-input-hint">Enter 发送 · 最多 500 字</div>
    </footer>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import axios from 'axios'
import { marked } from 'marked'

const question = ref('')
const textareaKey = ref(0)
const loading = ref(false)
/** 发往接口的最近 3 轮 { question, answer } */
const history = ref([])
/** 界面气泡：user / assistant，assistant 含 loading 与展示字段 */
const messages = ref([])
const historyRef = ref(null)

let nextMessageId = 0

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

function renderAnswer(text) {
  if (!text) return ''
  const parts = text.split('【引用书目】')
  const body = parts[0].trim()
  return marked.parse(body)
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
    answer: '',
    found: false,
    sources: [],
    concepts: [],
    cache_hit: false,
    elapsed: 0,
    cost: 0,
  }
  messages.value.push(assistantMsg)
  await scrollToBottom()

  // 追问补全：若当前问题疑似追问（不含书名但含篇章词），用上一轮问题的书名补全
  let finalQuestion = q
  const lastTurn = history.value[history.value.length - 1]
  if (lastTurn) {
    const hasChapter = /第[零一二三四五六七八九十百千]+[篇章课]|第\d+[篇章课]/.test(finalQuestion)
    const hasBookName =
      /文集|读经|训练|特会|总论|课程|福音|使徒|罗马|创世|出埃及|利未|民数|申命|约书亚|士师|路得|撒母耳|列王|历代|以斯|约伯|诗篇|箴言|传道|雅歌|以赛亚|耶利米|以西结|但以理|何西阿|约珥|阿摩司|俄巴底|约拿|弥迦|那鸿|哈巴谷|西番雅|哈该|撒迦利亚|玛拉基|马太|马可|路加|约翰|歌林多|加拉太|以弗所|腓利比|歌罗西|帖撒|提摩太|提多|腓利门|希伯来|雅各|彼得|犹大|启示/.test(
        finalQuestion,
      )
    const isTooShort = finalQuestion.length <= 15
    if (hasChapter && !hasBookName && isTooShort) {
      const prevQ = lastTurn.question
      const bookMatch = prevQ.match(/^(.+?)(?:第[零一二三四五六七八九十百千\d]+[篇章课]|的)/)
      if (bookMatch && bookMatch[1].length >= 4) {
        finalQuestion = bookMatch[1].trim() + finalQuestion
      }
    }
  }

  try {
    const res = await axios.post('/api/qa/query', {
      question: finalQuestion,
      skip_cache: true,
      debug: true,
      history: history.value.map((h) => ({
        question: h.question,
        answer: h.answer,
      })),
    })
    const d = res.data
    assistantMsg.found = d.found
    assistantMsg.answer = d.answer
    assistantMsg.sources = d.sources || []
    assistantMsg.concepts = d.concepts || []
    assistantMsg.cache_hit = d.cache_hit
    assistantMsg.elapsed = (d.total_elapsed_ms / 1000).toFixed(1)
    assistantMsg.cost = d.total_cost_usd || 0
  } catch (e) {
    assistantMsg.found = false
    assistantMsg.answer = '请求失败，请稍后重试。'
  } finally {
    assistantMsg.loading = false
    loading.value = false
    question.value = ''
    // 存补全后的问句，便于下一轮从 history 提取书名再做追问补全（气泡仍用上面的 q）
    history.value.push({
      question: finalQuestion,
      answer: assistantMsg.answer || '',
    })
    history.value = history.value.slice(-3)
    await nextTick()
    await scrollToBottom()
  }
}

async function scrollToBottom() {
  await nextTick()
  if (historyRef.value) {
    historyRef.value.scrollTop = historyRef.value.scrollHeight
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
  max-width: 760px;
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
.qa-logo-icon { font-size: 20px; }
.qa-logo-text {
  font-size: 17px;
  font-weight: 600;
  color: var(--color-primary);
  letter-spacing: 0.05em;
}
.qa-admin-link {
  font-size: 13px;
  color: var(--color-text-secondary);
  text-decoration: none;
  &:hover { color: var(--color-primary); }
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
  font-size: 15px;
  color: var(--color-text-secondary);
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
  max-width: 760px;
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
.qa-source-idx {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--color-primary);
  font-weight: 600;
  min-width: 16px;
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
  max-width: 760px;
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
.qa-input-hint {
  max-width: 760px;
  margin: 6px auto 0;
  font-size: 11px;
  color: var(--color-text-secondary);
  text-align: right;
}
</style>

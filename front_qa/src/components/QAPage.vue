<template>
  <div class="qa-root">
    <!-- 页头 -->
    <header class="qa-header">
      <div class="qa-header-inner">
        <div class="qa-logo">
          <span class="qa-logo-icon">📖</span>
          <span class="qa-logo-text">职事信息问答</span>
        </div>
        <a class="qa-admin-link" href="#/admin">管理</a>
      </div>
    </header>

    <!-- 主体 -->
    <main class="qa-main" ref="historyRef">
      <!-- 欢迎语（无历史时显示） -->
      <div v-if="history.length === 0" class="qa-welcome">
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

      <!-- 历史问答 -->
      <div class="qa-history">
        <div
          v-for="(item, idx) in history"
          :key="idx"
          class="qa-history-item"
        >
          <!-- 问题气泡 -->
          <div class="qa-bubble qa-bubble-question">
            <span>{{ item.question }}</span>
          </div>

          <!-- 答案卡片 -->
          <div class="qa-bubble qa-bubble-answer">
            <!-- 加载中 -->
            <div v-if="item.loading" class="qa-loading">
              <a-spin size="small" />
              <span class="qa-loading-text">正在检索职事信息…</span>
            </div>

            <!-- 未找到 -->
            <div v-else-if="!item.found" class="qa-not-found">
              <span class="qa-not-found-icon">🔍</span>
              以下内容未能在职事信息中找到相关依据。
            </div>

            <!-- 答案正文 -->
            <template v-else>
              <div class="qa-answer-body" v-html="renderAnswer(item.answer)"></div>

              <!-- 引用书目 -->
              <div v-if="item.sources && item.sources.length" class="qa-sources">
                <div class="qa-sources-title">引用书目</div>
                <div class="qa-sources-list">
                  <span
                    v-for="src in item.sources"
                    :key="src"
                    class="qa-source-tag"
                  >{{ src }}</span>
                </div>
              </div>

              <!-- 元信息 -->
              <div class="qa-meta">
                <span v-if="item.cache_hit" class="qa-meta-badge qa-meta-cache">缓存</span>
                <span class="qa-meta-time">{{ item.elapsed }}s</span>
                <span class="qa-meta-cost">¢{{ (item.cost * 100).toFixed(3) }}</span>
              </div>
            </template>

            <!-- 免责说明 -->
            <div v-if="!item.loading" class="qa-disclaimer">
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

const question = ref('')
const loading = ref(false)
const history = ref([])
const historyRef = ref(null)

const examples = [
  '神的经纶的中心是什么？',
  '生命与性情有何关系？',
  '教会是基督的身体，如何理解？',
  '圣灵的膏抹是什么意思？',
]

function fillExample(ex) {
  question.value = ex
}

function renderAnswer(text) {
  if (!text) return ''
  // 将【引用书目】之前的正文部分取出，换行转 <br>
  const parts = text.split('【引用书目】')
  const body = parts[0].trim()
  return body.replace(/\n/g, '<br>')
}

async function submit() {
  const q = question.value.trim()
  if (!q || loading.value) return

  question.value = ''
  loading.value = true

  const item = {
    question: q,
    loading: true,
    found: false,
    answer: '',
    sources: [],
    concepts: [],
    cache_hit: false,
    elapsed: 0,
    cost: 0,
  }
  history.value.push(item)
  await scrollToBottom()

  try {
    const res = await axios.post('/api/qa/query', {
      question: q,
      skip_cache: false,
    })
    const d = res.data
    item.found = d.found
    item.answer = d.answer
    item.sources = d.sources || []
    item.concepts = d.concepts || []
    item.cache_hit = d.cache_hit
    item.elapsed = (d.total_elapsed_ms / 1000).toFixed(1)
    item.cost = d.total_cost_usd || 0
  } catch (e) {
    item.found = false
    item.answer = '请求失败，请稍后重试。'
  } finally {
    item.loading = false
    loading.value = false
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

/* 主体 */
.qa-main {
  flex: 1;
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

/* 历史问答 */
.qa-history {
  max-width: 760px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.qa-history-item {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 气泡 */
.qa-bubble {
  border-radius: var(--radius);
  padding: 14px 18px;
  line-height: 1.8;
  font-size: 15px;
}
.qa-bubble-question {
  align-self: flex-end;
  background: var(--color-primary);
  color: #fff;
  max-width: 75%;
  border-bottom-right-radius: 2px;
}
.qa-bubble-answer {
  align-self: flex-start;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  max-width: 100%;
  box-shadow: var(--shadow);
  border-bottom-left-radius: 2px;
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
.qa-sources-list { display: flex; flex-wrap: wrap; gap: 6px; }
.qa-source-tag {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 12px;
  background: #f5f0e8;
  color: var(--color-primary);
  border: 1px solid #e8dcc8;
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
  width: 56px;
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

<template>
  <div class="ai-chat">
    <header class="ai-chat-header">
      <h1 class="ai-chat-title">圣经 AI 助手</h1>
      <p class="ai-chat-desc">输入问题，基于经文智能回答</p>
    </header>

    <div class="ai-chat-messages" ref="messagesRef">
      <div v-if="messages.length === 0" class="ai-chat-empty">
        输入问题开始对话，例如：「圣经如何定义爱？」
      </div>
      <div
        v-for="(msg, index) in messages"
        :key="index"
        :class="['ai-chat-bubble-wrap', msg.role]"
      >
        <div class="ai-chat-bubble">
          <div class="ai-chat-bubble-label" v-if="msg.content">中文纲目</div>
          <div class="ai-chat-bubble-content" v-html="formatContent(msg.content)"></div>
          <div v-if="msg.loadingEnglish" class="ai-chat-bubble-en ai-chat-loading-en">正在生成英文纲目…</div>
          <div v-else-if="msg.errorEnglish" class="ai-chat-bubble-en ai-chat-error-en">{{ msg.errorEnglish }}</div>
          <div v-else-if="msg.contentEn" class="ai-chat-bubble-en">
            <div class="ai-chat-bubble-label">英文纲目</div>
            <div class="ai-chat-bubble-content" v-html="formatContent(msg.contentEn)"></div>
          </div>
          <div v-if="msg.sources && msg.sources.length" class="ai-chat-sources">
            <div class="ai-chat-sources-title">参考来源</div>
            <div
              v-for="(src, i) in msg.sources"
              :key="i"
              class="ai-chat-source-item"
            >
              <span class="ai-chat-source-type">{{ src.type }}</span>
              <span class="ai-chat-source-ref">{{ src.reference }}</span>
              <p class="ai-chat-source-content">{{ src.content }}</p>
            </div>
          </div>
          <div v-if="msg.cached" class="ai-chat-cached-tag">缓存</div>
        </div>
      </div>
      <div v-if="loading" class="ai-chat-bubble-wrap assistant">
        <div class="ai-chat-bubble ai-chat-bubble-loading">
          <div class="ai-chat-loading-dots">
            <span></span><span></span><span></span>
          </div>
        </div>
      </div>
    </div>

    <div class="ai-chat-input-wrap" @click="expandForm">
      <textarea
        v-model="form.question"
        class="ai-chat-input"
        placeholder="点击输入问题，展开下方栏位后补充纲目主题等信息…"
        rows="2"
        :disabled="loading"
        @focus="expandForm"
        @keydown.enter.exact.prevent="send"
      />
    </div>

    <transition name="ai-chat-panel">
      <div v-if="showFormDetails" class="ai-chat-details-panel">
        <div class="ai-chat-details-grid">
          <label class="ai-chat-field">
            <span>纲目主题</span>
            <input
              v-model="form.outlineTopic"
              type="text"
              placeholder="本次纲目的核心题目"
              :disabled="loading"
            />
          </label>
          <label class="ai-chat-field">
            <span>面对对象</span>
            <input
              v-model="form.audience"
              type="text"
              placeholder="例如：青职弟兄、初信者、小排服事者..."
              :disabled="loading"
            />
          </label>
          <label class="ai-chat-field full">
            <span>负担说明</span>
            <textarea
              v-model="form.burdenDescription"
              rows="2"
              placeholder="用简短段落说明本次聚会或分享的负担"
              :disabled="loading"
            />
          </label>
          <div class="ai-chat-field full">
            <span>纲目性质*（必选）</span>
            <div class="ai-nature-btns">
              <button
                type="button"
                v-for="opt in AI_NATURE_OPTIONS"
                :key="opt"
                :class="['ai-nature-btn', { active: form.specialNeeds === opt }]"
                :disabled="loading"
                @click="form.specialNeeds = form.specialNeeds === opt ? '' : opt"
              >
                {{ opt }}
              </button>
            </div>
          </div>
        </div>

        <div class="ai-chat-depth-select">
          <span>检索深度</span>
          <div class="ai-chat-depth-buttons">
            <button
              type="button"
              :class="['ai-chat-depth-btn', { active: form.depth === 'general' }]"
              :disabled="loading"
              @click="form.depth = 'general'"
            >
              一般（快速）
            </button>
            <button
              type="button"
              :class="['ai-chat-depth-btn', { active: form.depth === 'deep' }]"
              :disabled="loading"
              @click="form.depth = 'deep'"
            >
              深度（更全面）
            </button>
          </div>
        </div>

        <div class="ai-chat-panel-actions">
          <div v-if="!formValid" class="ai-chat-hint">
            请填写【问题】、【纲目主题】、【负担说明】、【纲目性质】、【面对对象】后再发送。
          </div>
          <label class="ai-chat-checkbox">
            <input type="checkbox" v-model="includeEnglishOutline" :disabled="!ENGLISH_OUTLINE_FEATURE_ENABLED || loading" />
            <span>同时生成英文纲目</span>
          </label>
          <button
            class="ai-chat-send"
            :disabled="loading || !formValid"
            @click="send"
          >
            {{ loading ? '发送中…' : '发送给 Claude' }}
          </button>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick } from 'vue'

const messagesRef = ref(null)
const loading = ref(false)
const messages = ref([])
const showFormDetails = ref(false)
// 暂封英文纲目功能，测试通过后改为 true
const ENGLISH_OUTLINE_FEATURE_ENABLED = false
const includeEnglishOutline = ref(false)
const AI_NATURE_OPTIONS = ['一般性', '高真理浓度', '高生命浓度', '重实行应用']
const form = reactive({
  question: '',
  outlineTopic: '',
  burdenDescription: '',
  specialNeeds: '一般性',
  audience: '',
  depth: 'general'
})

const apiBase = import.meta.env?.VITE_API_BASE || ''

const formValid = computed(() => {
  const questionFilled = form.question.trim().length > 0
  const outlineFilled = form.outlineTopic.trim().length > 0
  const burdenFilled = form.burdenDescription.trim().length > 0
  const natureFilled = form.specialNeeds.trim().length > 0
  const audienceFilled = form.audience.trim().length > 0
  return questionFilled && outlineFilled && burdenFilled && natureFilled && audienceFilled
})

function expandForm() {
  showFormDetails.value = true
}

function formatContent(text) {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>')
}

async function fetchTranslateForLastMessage(chineseOutline) {
  const list = messages.value
  const last = list[list.length - 1]
  if (!last || last.role !== 'assistant' || !chineseOutline.trim()) return
  try {
    const res = await fetch(`${apiBase}/api/ai_search/translate_outline`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ chinese_outline: chineseOutline })
    })
    const data = await res.json().catch(() => ({}))
    last.loadingEnglish = false
    if (data.answer_en) {
      last.contentEn = data.answer_en
    } else {
      last.errorEnglish = data.error || '英文纲目生成失败'
    }
  } catch (e) {
    last.loadingEnglish = false
    last.errorEnglish = e.message || '翻译请求失败，请稍后重试'
  }
  await nextTick()
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

function buildUserPreview() {
  const lines = [
    `【问题】${form.question.trim()}`,
    `【纲目主题】${form.outlineTopic.trim()}`,
    `【负担说明】${form.burdenDescription.trim()}`,
    `【面对对象】${form.audience.trim()}`,
    `【检索深度】${form.depth === 'deep' ? '深度' : '一般'}`
  ]
  const nature = form.specialNeeds.trim()
  if (nature) lines.splice(3, 0, `【纲目性质】${nature}`)
  return lines.join('\n')
}

async function send() {
  if (loading.value || !formValid.value) {
    showFormDetails.value = true
    return
  }

  const question = form.question.trim()
  const payload = {
    question,
    max_results: 8,
    depth: form.depth,
    outline_topic: form.outlineTopic.trim(),
    burden_description: form.burdenDescription.trim(),
    special_needs: form.specialNeeds.trim(),
    audience: form.audience.trim()
  }

  messages.value.push({ role: 'user', content: buildUserPreview() })
  loading.value = true

  try {
    const res = await fetch(`${apiBase}/api/ai_search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(payload)
    })
    const data = await res.json().catch(() => ({}))
    const answer = data.answer || '抱歉，暂无回答。'
    const sources = data.sources || []
    const cached = !!data.cached
    messages.value.push({
      role: 'assistant',
      content: answer,
      contentEn: null,
      loadingEnglish: includeEnglishOutline.value,
      errorEnglish: null,
      sources,
      cached
    })
    form.question = ''
    if (includeEnglishOutline.value && answer) {
      fetchTranslateForLastMessage(answer)
    }
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: '请求失败，请检查网络或稍后重试。'
    })
  } finally {
    loading.value = false
    await nextTick()
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  }
}
</script>

<style scoped>
.ai-chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-width: 720px;
  margin: 0 auto;
  background: #f5f5f5;
}

.ai-chat-header {
  flex-shrink: 0;
  padding: 16px 20px;
  background: #1677ff;
  color: #fff;
  text-align: center;
}

.ai-chat-title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
}

.ai-chat-desc {
  margin: 6px 0 0;
  font-size: 0.85rem;
  opacity: 0.9;
}

.ai-chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ai-chat-empty {
  color: #999;
  text-align: center;
  padding: 32px 16px;
  font-size: 0.9rem;
}

.ai-chat-bubble-wrap {
  display: flex;
  width: 100%;
}

.ai-chat-bubble-wrap.user {
  justify-content: flex-end;
}

.ai-chat-bubble-wrap.assistant {
  justify-content: flex-start;
}

.ai-chat-bubble {
  max-width: 85%;
  padding: 12px 16px;
  border-radius: 12px;
  position: relative;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
}

.ai-chat-bubble-wrap.user .ai-chat-bubble {
  background: #1677ff;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.ai-chat-bubble-wrap.assistant .ai-chat-bubble {
  background: #fff;
  color: #333;
  border-bottom-left-radius: 4px;
}

.ai-chat-bubble-wrap.assistant .ai-chat-bubble-label {
  color: #1677ff;
}
.ai-chat-bubble-wrap.assistant .ai-chat-bubble-en {
  border-top-color: #eee;
}
.ai-chat-bubble-wrap.assistant .ai-chat-loading-en,
.ai-chat-bubble-wrap.assistant .ai-chat-error-en {
  color: #666;
}
.ai-chat-bubble-wrap.assistant .ai-chat-error-en {
  color: #c41e3a;
}

.ai-chat-bubble-content {
  font-size: 0.95rem;
  line-height: 1.6;
  word-break: break-word;
}

.ai-chat-bubble-label {
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.85);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}

.ai-chat-bubble-en {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.2);
}

.ai-chat-loading-en,
.ai-chat-error-en {
  font-size: 0.9rem;
  color: rgba(255, 255, 255, 0.9);
}
.ai-chat-error-en {
  color: #ffccc7;
}

.ai-chat-checkbox {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-right: 12px;
  cursor: pointer;
  font-size: 0.9rem;
}
.ai-chat-checkbox input { margin: 0; }

.ai-chat-sources {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #eee;
}

.ai-chat-sources-title {
  font-size: 0.8rem;
  color: #666;
  margin-bottom: 8px;
}

.ai-chat-source-item {
  font-size: 0.85rem;
  margin-bottom: 8px;
  padding: 8px;
  background: #f9f9f9;
  border-radius: 8px;
}

.ai-chat-source-type {
  color: #1677ff;
  margin-right: 8px;
}

.ai-chat-source-ref {
  font-weight: 600;
  color: #333;
}

.ai-chat-source-content {
  margin: 6px 0 0;
  color: #666;
  line-height: 1.5;
}

.ai-chat-cached-tag {
  position: absolute;
  top: 8px;
  right: 12px;
  font-size: 0.7rem;
  color: #999;
}

/* 加载动画 */
.ai-chat-bubble-loading {
  min-width: 60px;
}

.ai-chat-loading-dots {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 4px 0;
}

.ai-chat-loading-dots span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #1677ff;
  animation: ai-chat-dot 1.4s ease-in-out infinite both;
}

.ai-chat-loading-dots span:nth-child(1) { animation-delay: -0.32s; }
.ai-chat-loading-dots span:nth-child(2) { animation-delay: -0.16s; }

@keyframes ai-chat-dot {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.6; }
  40% { transform: scale(1); opacity: 1; }
}

.ai-chat-input-wrap {
  flex-shrink: 0;
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  background: #fff;
  border-top: 1px solid #eee;
  align-items: flex-end;
}

.ai-chat-input {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  font-size: 0.95rem;
  resize: none;
  font-family: inherit;
  transition: border-color 0.2s;
}

.ai-chat-input:focus {
  outline: none;
  border-color: #1677ff;
}

.ai-chat-input:disabled {
  background: #f5f5f5;
  cursor: not-allowed;
}

.ai-chat-send {
  padding: 10px 20px;
  background: #1677ff;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 0.95rem;
  cursor: pointer;
  white-space: nowrap;
}

.ai-chat-send:hover:not(:disabled) {
  background: #4096ff;
}

.ai-chat-send:disabled {
  background: #bfbfbf;
  cursor: not-allowed;
}

.ai-chat-details-panel {
  background: #fff;
  border-top: 1px solid #eee;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ai-chat-details-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px 16px;
}

.ai-chat-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 0.85rem;
  color: #555;
}

.ai-chat-field.full {
  grid-column: 1 / -1;
}

.ai-chat-field input,
.ai-chat-field textarea {
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 0.95rem;
  font-family: inherit;
  resize: none;
  transition: border-color 0.2s;
}

.ai-chat-field input:focus,
.ai-chat-field textarea:focus {
  outline: none;
  border-color: #1677ff;
}

.ai-chat-depth-select {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.ai-chat-depth-buttons {
  display: flex;
  gap: 8px;
}

.ai-chat-depth-btn {
  border: 1px solid #d9d9d9;
  background: #f5f5f5;
  color: #555;
  padding: 8px 16px;
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.2s;
}

.ai-chat-depth-btn.active {
  background: #1677ff;
  border-color: #1677ff;
  color: #fff;
  box-shadow: 0 4px 12px rgba(22, 119, 255, 0.25);
}

.ai-chat-depth-btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.ai-nature-btns {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.ai-nature-btn {
  border: 1px solid #d9d9d9;
  background: #f5f5f5;
  color: #555;
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.9rem;
  transition: all 0.2s;
}

.ai-nature-btn:hover:not(:disabled):not(.active) {
  border-color: #1677ff;
  color: #1677ff;
}

.ai-nature-btn.active {
  background: #1677ff;
  border-color: #1677ff;
  color: #fff;
}

.ai-nature-btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.ai-chat-panel-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.ai-chat-hint {
  color: #fa8c16;
  font-size: 0.85rem;
}

.ai-chat-panel-enter-active,
.ai-chat-panel-leave-active {
  transition: all 0.2s ease;
}

.ai-chat-panel-enter-from,
.ai-chat-panel-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>

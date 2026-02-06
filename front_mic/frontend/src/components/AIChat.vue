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
          <div class="ai-chat-bubble-content" v-html="formatContent(msg.content)"></div>
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

    <div class="ai-chat-input-wrap">
      <textarea
        v-model="inputText"
        class="ai-chat-input"
        placeholder="输入你的问题…"
        rows="2"
        :disabled="loading"
        @keydown.enter.exact.prevent="send"
      />
      <button
        class="ai-chat-send"
        :disabled="loading || !inputText.trim()"
        @click="send"
      >
        {{ loading ? '发送中…' : '发送' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'

const messagesRef = ref(null)
const inputText = ref('')
const loading = ref(false)
const messages = ref([])

const apiBase = import.meta.env?.VITE_API_BASE || ''

function formatContent(text) {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>')
}

async function send() {
  const question = inputText.value?.trim()
  if (!question || loading.value) return

  messages.value.push({ role: 'user', content: question })
  inputText.value = ''
  loading.value = true

  try {
    const res = await fetch(`${apiBase}/api/ai_search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ question, max_results: 8 })
    })
    const data = await res.json().catch(() => ({}))
    const answer = data.answer || '抱歉，暂无回答。'
    const sources = data.sources || []
    const cached = !!data.cached
    messages.value.push({
      role: 'assistant',
      content: answer,
      sources,
      cached
    })
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

.ai-chat-bubble-content {
  font-size: 0.95rem;
  line-height: 1.6;
  word-break: break-word;
}

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
</style>

<template>
  <div class="container">
    <h2 class="title">纲目翻译（练习版）</h2>
    <div class="direction-toggle">
      <button :class="['toggle-btn', direction === 'zh2en' ? 'active' : '']" @click="direction = 'zh2en'">中文 → 英文</button>
      <button :class="['toggle-btn', direction === 'en2zh' ? 'active' : '']" @click="direction = 'en2zh'">英文 → 中文</button>
      <button :class="['toggle-btn', direction === 'en2es' ? 'active' : '']" @click="direction = 'en2es'">英文 → 西语</button>
    </div>
    <!-- 「同时生成繁体」勾选框，只在英转中时显示 -->
    <div v-if="direction === 'en2zh'" class="tw-option">
      <label>
        <input type="checkbox" v-model="generateTw" />
        同时生成繁体
      </label>
    </div>
    <textarea v-model="content" class="input-area" placeholder="请粘贴纲目内容..." rows="12" />
    <p v-if="emptyError" class="error-text">请先输入内容</p>
    <button class="translate-btn" :disabled="loading" @click="handleTranslate">
      {{ loading ? '翻译中…' : '翻译' }}
    </button>
    <p v-if="requestError" class="error-text">{{ requestError }}</p>

    <!-- 简体结果 -->
    <div v-if="result" class="result-box">
      <button class="copy-btn" @click="handleCopy('zh')">{{ copiedZh ? '已复制' : '复制' }}</button>
      <div class="result-label">{{ generateTw && direction === 'en2zh' ? '简体结果' : '翻译结果' }}</div>
      <pre class="result-text">{{ result }}</pre>
    </div>

    <!-- 繁体结果 + 易错字审核区 -->
    <div v-if="twResult" class="result-box tw-result-box">
      <button class="copy-btn" @click="handleCopy('tw')">{{ copiedTw ? '已复制' : '复制' }}</button>
      <div class="result-label tw-label">繁体结果</div>
      <pre class="result-text">{{ twResult }}</pre>
      <ErrorReview
        v-model="twResult"
        v-model:errorChecks="twErrorChecks"
      />
    </div>
    <p v-if="twLoading" class="tw-loading">繁体转换中…</p>
    <p v-if="twError" class="error-text">{{ twError }}</p>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import ErrorReview from '../../zh2tw/frontend/src/components/ErrorReview.vue'

const direction = ref('zh2en')
const content = ref('')
const result = ref('')
const loading = ref(false)
const emptyError = ref(false)
const requestError = ref('')
const copiedZh = ref(false)
const copiedTw = ref(false)
const generateTw = ref(false)
const twResult = ref('')
const twErrorChecks = ref([])
const twLoading = ref(false)
const twError = ref('')

async function handleTranslate() {
  emptyError.value = false
  requestError.value = ''
  result.value = ''
  twResult.value = ''
  twErrorChecks.value = []
  twError.value = ''
  if (!content.value.trim()) {
    emptyError.value = true
    return
  }
  loading.value = true
  try {
    const res = await fetch('/api/practice/translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ direction: direction.value, content: content.value }),
    })
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}))
      requestError.value = errData.detail || `请求失败（${res.status}）`
      return
    }
    const data = await res.json()
    if (data.error) {
      requestError.value = data.error
    } else {
      result.value = data.result
      // 勾选了「同时生成繁体」且是英转中时，自动调简转繁
      if (generateTw.value && direction.value === 'en2zh') {
        await convertToTw(data.result)
      }
    }
  } catch (e) {
    requestError.value = '网络错误，请稍后重试'
  } finally {
    loading.value = false
  }
}

async function convertToTw(zhText) {
  twLoading.value = true
  twError.value = ''
  try {
    const res = await fetch('/api/testc/zh_convert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: zhText, direction: 'zh2tw' })
    })
    if (!res.ok) {
      twError.value = `繁体转换失败（${res.status}）`
      return
    }
    const data = await res.json()
    if (data.error) {
      twError.value = data.error
    } else {
      twResult.value = data.answer_zh_tw
      twErrorChecks.value = data.error_check || []
    }
  } catch (e) {
    twError.value = '繁体转换网络错误'
  } finally {
    twLoading.value = false
  }
}

async function handleCopy(type) {
  const text = type === 'tw' ? twResult.value : result.value
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    if (type === 'tw') {
      copiedTw.value = true
      setTimeout(() => { copiedTw.value = false }, 2000)
    } else {
      copiedZh.value = true
      setTimeout(() => { copiedZh.value = false }, 2000)
    }
  } catch {}
}
</script>

<style scoped>
.container { max-width: 900px; margin: 40px auto; padding: 0 20px; font-family: sans-serif; }
.title { font-size: 20px; font-weight: 600; margin-bottom: 20px; color: #222; }
.direction-toggle { display: flex; gap: 8px; margin-bottom: 14px; }
.toggle-btn { padding: 6px 18px; border: 1px solid #ccc; border-radius: 4px; background: #f5f5f5; cursor: pointer; font-size: 14px; }
.toggle-btn.active { background: #1a6ef5; border-color: #1a6ef5; color: #fff; }
.tw-option { margin-bottom: 12px; font-size: 14px; color: #444; display: flex; align-items: center; gap: 6px; }
.tw-option input { cursor: pointer; }
.input-area { width: 100%; box-sizing: border-box; padding: 10px 12px; border: 1px solid #ccc; border-radius: 4px; font-size: 14px; line-height: 1.6; resize: vertical; outline: none; }
.input-area:focus { border-color: #1a6ef5; }
.error-text { margin: 6px 0 0; color: #d0021b; font-size: 13px; }
.translate-btn { margin-top: 14px; padding: 8px 28px; background: #1a6ef5; color: #fff; border: none; border-radius: 4px; font-size: 15px; cursor: pointer; }
.translate-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.result-box { position: relative; margin-top: 24px; padding: 16px; border: 1px solid #ddd; border-radius: 4px; background: #fafafa; }
.tw-result-box { border-color: #5c4db1; background: #faf9ff; }
.result-label { font-size: 13px; font-weight: 600; color: #555; margin-bottom: 8px; }
.tw-label { color: #5c4db1; }
.copy-btn { position: absolute; top: 10px; right: 12px; padding: 4px 14px; font-size: 12px; border: 1px solid #ccc; border-radius: 4px; background: #fff; cursor: pointer; }
.copy-btn:hover { background: #f0f0f0; }
.result-text { margin: 0; padding-right: 60px; white-space: pre-wrap; word-break: break-word; font-size: 14px; line-height: 1.7; color: #333; }
.tw-loading { margin-top: 12px; font-size: 14px; color: #5c4db1; }
</style>

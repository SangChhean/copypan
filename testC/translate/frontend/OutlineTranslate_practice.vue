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

    <FormatDownloadBar
      v-if="result"
      :text="formatText"
      :direction="formatDirection"
      api-endpoint="/api/practice/format_download"
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import ErrorReview from '../../zh2tw/frontend/src/components/ErrorReview.vue'
import FormatDownloadBar from '../../../front_mic/frontend/src/components/toolbox/FormatDownloadBar.vue'

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

const formatDirection = computed(() => {
  if (direction.value === 'zh2en') return 'en'
  if (direction.value === 'en2zh') return generateTw.value ? 'zh_tw' : 'zh'
  if (direction.value === 'en2es') return 'es'
  return 'zh'
})

const formatText = computed(() => {
  if (direction.value === 'en2zh' && generateTw.value && twResult.value) return twResult.value
  return result.value
})

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
:global(body) {
  background-color: #f7f5f0;
}

.container {
  --bg-page: #f7f5f0;
  --bg-card: #ffffff;
  --bg-input: #fdfcfb;
  --color-primary: #2c5f8a;
  --color-primary-hover: #1e4a6e;
  --color-primary-light: #e8f0f7;
  --color-text: #2d2d2d;
  --color-text-secondary: #6b6b6b;
  --color-border: #dde3e9;
  --radius: 8px;
  --shadow: 0 2px 12px rgba(44, 95, 138, 0.08), 0 1px 3px rgba(0, 0, 0, 0.05);

  max-width: 920px;
  margin: 0 auto;
  padding: 28px 24px;
  background-color: #f7f5f0;
  min-height: 100vh;
  color: var(--color-text);
}

.title {
  font-size: 22px;
  font-weight: 700;
  color: #2d2d2d;
  margin-bottom: 24px;
  padding-bottom: 12px;
  border-bottom: 2px solid #dde3e9;
}

.direction-toggle {
  display: inline-flex;
  gap: 6px;
  margin-bottom: 20px;
  background: #fff;
  border-radius: 10px;
  padding: 6px;
  box-shadow: var(--shadow);
}

.toggle-btn {
  padding: 9px 24px;
  font-size: 15px;
  font-weight: 500;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: #6b6b6b;
  cursor: pointer;
  transition: all 0.2s ease;
}
.toggle-btn:hover:not(.active) {
  background: #e8f0f7;
  color: #2c5f8a;
}
.toggle-btn.active {
  background: #2c5f8a;
  color: #fff;
  box-shadow: 0 2px 6px rgba(44, 95, 138, 0.25);
}

.tw-option {
  margin-bottom: 16px;
  font-size: 14px;
  color: #555;
  display: flex;
  align-items: center;
  gap: 8px;
}
.tw-option input {
  cursor: pointer;
}

.input-area {
  width: 100%;
  box-sizing: border-box;
  padding: 14px 16px;
  font-size: 15px;
  line-height: 1.8;
  border: 1.5px solid #dde3e9;
  border-radius: 8px;
  background: #fdfcfb;
  color: #2d2d2d;
  resize: vertical;
  outline: none;
  min-height: 200px;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.input-area:focus {
  border-color: #2c5f8a;
  box-shadow: 0 0 0 3px rgba(44, 95, 138, 0.1);
}

.translate-btn {
  margin-top: 16px;
  padding: 10px 36px;
  font-size: 16px;
  font-weight: 500;
  background: #2c5f8a;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s ease;
}
.translate-btn:hover:not(:disabled) {
  background: #1e4a6e;
}
.translate-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.error-text {
  margin: 8px 0 0;
  color: #c0392b;
  font-size: 13px;
}

.result-box {
  position: relative;
  margin-top: 24px;
  padding: 20px;
  border: 1px solid #dde3e9;
  border-radius: 10px;
  background: #ffffff;
  box-shadow: var(--shadow);
}

.tw-result-box {
  border: 1px solid #2c5f8a;
  border-left: 4px solid #2c5f8a;
  background: #f0f4f8;
}

.result-label {
  font-size: 13px;
  font-weight: 600;
  color: #6b6b6b;
  margin-bottom: 10px;
}

.tw-label {
  color: #2c5f8a;
}

.copy-btn {
  position: absolute;
  top: 16px;
  right: 16px;
  padding: 5px 14px;
  font-size: 12px;
  border: 1.5px solid #2c5f8a;
  border-radius: 4px;
  background: #fff;
  color: #2c5f8a;
  cursor: pointer;
  transition: background 0.2s ease;
}
.copy-btn:hover {
  background: #e8f0f7;
}

.result-text {
  margin: 0;
  padding-right: 70px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 15px;
  line-height: 1.8;
  color: #2d2d2d;
}

.tw-loading {
  margin-top: 12px;
  font-size: 14px;
  color: #2c5f8a;
}
</style>

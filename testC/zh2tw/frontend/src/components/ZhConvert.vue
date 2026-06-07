<template>
  <div class="container">
    <button class="btn btn-back" onclick="history.back()">← 返回</button>
    <h1 class="title">简繁互转</h1>
    <div class="direction-row">
      <button class="btn btn-dir" :class="{ active: direction === 'zh2tw' }" @click="direction = 'zh2tw'">简 → 繁</button>
      <button class="btn btn-dir" :class="{ active: direction === 'tw2zh' }" @click="direction = 'tw2zh'">繁 → 简</button>
    </div>
    <textarea v-model="input" class="textarea" :placeholder="direction === 'zh2tw' ? '请输入简体中文...' : '請輸入繁體中文...'" rows="8"></textarea>
    <div class="btn-row">
      <button class="btn btn-primary" @click="convert" :disabled="loading">{{ loading ? '转换中…' : '转换' }}</button>
      <button class="btn btn-secondary" @click="clear">清空</button>
    </div>
    <p v-if="emptyError" class="error-msg">请先输入内容</p>
    <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>

    <!-- 转换结果 -->
    <div v-if="resultText" class="result-box">
      <div class="result-header">
        <span>转换结果</span>
        <button class="btn btn-copy" @click="copy">复制结果</button>
      </div>
      <div class="result-text">{{ resultText }}</div>
      <FormatDownloadBar
        :text="resultText"
        :direction="formatDirection"
        api-endpoint="/api/testc/format_download"
      />
    </div>

    <!-- 易错字审核区 -->
    <ErrorReview
      v-if="resultText && direction === 'zh2tw'"
      v-model="resultText"
      v-model:errorChecks="errorChecks"
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import ErrorReview from './ErrorReview.vue'
import FormatDownloadBar from '../../../../../front_mic/frontend/src/components/toolbox/FormatDownloadBar.vue'

const input = ref('')
const resultText = ref('')
const errorChecks = ref([])
const loading = ref(false)
const emptyError = ref(false)
const errorMsg = ref('')
const direction = ref('zh2tw')

const formatDirection = computed(() => {
  return direction.value === 'zh2tw' ? 'zh_tw' : 'zh'
})

async function convert() {
  emptyError.value = false
  errorMsg.value = ''
  resultText.value = ''
  errorChecks.value = []
  if (!input.value.trim()) {
    emptyError.value = true
    return
  }
  loading.value = true
  try {
    const res = await fetch('/api/testc/zh_convert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: input.value, direction: direction.value })
    })
    const data = await res.json()
    if (!res.ok) {
      errorMsg.value = data.detail || `请求失败（${res.status}）`
    } else if (data.error) {
      errorMsg.value = data.error
    } else {
      resultText.value = data.answer_zh_tw
      errorChecks.value = data.error_check || []
    }
  } catch (e) {
    errorMsg.value = '网络错误，请稍后重试'
  } finally {
    loading.value = false
  }
}

function clear() {
  input.value = ''
  resultText.value = ''
  errorChecks.value = []
  emptyError.value = false
  errorMsg.value = ''
}

function copy() {
  navigator.clipboard.writeText(resultText.value)
}
</script>

<style scoped>
:global(body) {
  background-color: #f7f5f0;
}

.container {
  max-width: 920px;
  margin: 0 auto;
  padding: 28px 24px;
  background: #f7f5f0;
  color: #2d2d2d;
  font-family: sans-serif;
}

.title {
  font-size: 22px;
  font-weight: 700;
  color: #2d2d2d;
  text-align: center;
  margin-bottom: 24px;
  padding-bottom: 12px;
  border-bottom: 2px solid #dde3e9;
}

.direction-row {
  display: inline-flex;
  gap: 6px;
  margin-bottom: 20px;
  background: #fff;
  border-radius: 10px;
  padding: 6px;
  box-shadow: 0 2px 12px rgba(44, 95, 138, 0.08);
}

.btn-dir {
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
.btn-dir:hover:not(.active) {
  background: #e8f0f7;
  color: #2c5f8a;
}
.btn-dir.active {
  background: #2c5f8a;
  color: #fff;
  border-color: #2c5f8a;
  box-shadow: 0 2px 6px rgba(44, 95, 138, 0.25);
}

.btn-back {
  background: transparent;
  color: #6b6b6b;
  border: 1.5px solid #dde3e9;
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 13px;
  cursor: pointer;
  margin-bottom: 20px;
  transition: all 0.2s ease;
}
.btn-back:hover {
  border-color: #2c5f8a;
  color: #2c5f8a;
}

.textarea {
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
.textarea:focus {
  border-color: #2c5f8a;
  box-shadow: 0 0 0 3px rgba(44, 95, 138, 0.1);
}

.btn-row {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}

.btn {
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-primary {
  background: #2c5f8a;
  color: #fff;
  font-weight: 500;
  border: none;
  border-radius: 6px;
  padding: 10px 36px;
  font-size: 16px;
}
.btn-primary:hover:not(:disabled) {
  background: #1e4a6e;
}
.btn-primary:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.btn-secondary {
  background: #fff;
  color: #6b6b6b;
  border: 1.5px solid #dde3e9;
  border-radius: 6px;
  padding: 10px 20px;
  font-size: 15px;
}
.btn-secondary:hover {
  color: #c0392b;
  border-color: #c0392b;
}

.error-msg {
  color: #c0392b;
  margin-top: 8px;
  font-size: 13px;
}

.result-box {
  margin-top: 24px;
  padding: 20px;
  border: 1px solid #dde3e9;
  border-radius: 10px;
  background: #ffffff;
  box-shadow: 0 2px 12px rgba(44, 95, 138, 0.08);
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  color: #2c5f8a;
  font-weight: 600;
  font-size: 14px;
}

.btn-copy {
  border: 1.5px solid #2c5f8a;
  color: #2c5f8a;
  background: #fff;
  border-radius: 4px;
  padding: 5px 14px;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.2s ease;
}
.btn-copy:hover {
  background: #e8f0f7;
}

.result-text {
  white-space: pre-wrap;
  font-size: 15px;
  line-height: 1.8;
  color: #2d2d2d;
}

/* 审核区 */
.review-box {
  margin-top: 20px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #dee2e6;
  padding: 16px;
}
.review-header {
  font-size: 14px;
  margin-bottom: 16px;
  font-weight: 500;
}
.no-error { color: #2d6a4f; }
.has-error { color: #e67e00; }
.error-group {
  border: 1px solid #e9ecef;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 12px;
  background: #f8f9fa;
}
.group-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.group-char {
  font-size: 16px;
  font-weight: bold;
  color: #2c5f8a;
}
.group-count { font-size: 13px; color: #6c757d; }
.group-candidates {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.label { font-size: 13px; color: #6c757d; }
.btn-candidate {
  background: #fff;
  color: #2c5f8a;
  border: 1px solid #2c5f8a;
  border-radius: 4px;
  padding: 2px 10px;
  font-size: 13px;
  cursor: pointer;
}
.btn-candidate:hover { background: #ede9f8; }
.btn-candidate.selected {
  background: #2c5f8a;
  color: #fff;
}
.btn-set-all {
  background: #e9ecef;
  color: #495057;
  border: 1px solid #ced4da;
  border-radius: 4px;
  padding: 2px 10px;
  font-size: 13px;
  cursor: pointer;
}
.btn-set-all:hover { background: #dee2e6; }
.error-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0;
  border-top: 1px solid #e9ecef;
  gap: 12px;
}
.item-context {
  font-size: 16px;
  color: #343a40;
  flex: 1;
  line-height: 1.6;
}
.item-candidates { display: flex; gap: 6px; flex-shrink: 0; }
:deep(.hl) {
  background: #fff3cd;
  color: #212529;
  border-radius: 3px;
  padding: 0 3px;
  font-weight: bold;
}
.global-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #dee2e6;
}
.btn-confirm {
  background: #2c5f8a;
  color: #fff;
  font-weight: bold;
  padding: 10px 28px;
}
.btn-confirm:hover { background: #4a3d9a; }
.btn-undo {
  background: #fff;
  color: #dc3545;
  border: 1px solid #dc3545;
  padding: 10px 28px;
}
.btn-undo:hover { background: #fff5f5; }
.btn-undo:disabled { opacity: 0.4; cursor: not-allowed; }
</style>

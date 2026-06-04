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
import { ref } from 'vue'
import ErrorReview from './ErrorReview.vue'

const input = ref('')
const resultText = ref('')
const errorChecks = ref([])
const loading = ref(false)
const emptyError = ref(false)
const errorMsg = ref('')
const direction = ref('zh2tw')

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
.container {
  max-width: 1100px;
  margin: 32px auto;
  padding: 40px;
  background: #f8f9fa;
  border-radius: 12px;
  color: #1a1a2e;
  font-family: sans-serif;
}
.title {
  text-align: center;
  font-size: 24px;
  margin-bottom: 24px;
  color: #5c4db1;
  font-weight: 600;
}
.direction-row {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.btn-dir {
  padding: 8px 20px;
  border-radius: 8px;
  background: #e9ecef;
  color: #495057;
  border: 1px solid #dee2e6;
  font-size: 14px;
  cursor: pointer;
}
.btn-dir.active {
  background: #5c4db1;
  color: #fff;
  font-weight: bold;
  border-color: #5c4db1;
}
.textarea {
  width: 100%;
  background: #fff;
  border: 1px solid #ced4da;
  border-radius: 8px;
  color: #212529;
  font-size: 15px;
  padding: 12px;
  resize: vertical;
  box-sizing: border-box;
}
.btn-row {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}
.btn {
  padding: 10px 24px;
  border: none;
  border-radius: 8px;
  font-size: 15px;
  cursor: pointer;
}
.btn-primary {
  background: #5c4db1;
  color: #fff;
  font-weight: bold;
}
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-secondary { background: #e9ecef; color: #495057; }
.btn-back {
  background: transparent;
  color: #6c757d;
  border: 1px solid #ced4da;
  margin-bottom: 16px;
  padding: 6px 16px;
  font-size: 13px;
  border-radius: 8px;
  cursor: pointer;
}
.error-msg { color: #dc3545; margin-top: 12px; }
.result-box {
  margin-top: 24px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #dee2e6;
  padding: 16px;
}
.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  color: #2d6a4f;
  font-weight: bold;
}
.btn-copy { background: #e9ecef; color: #495057; padding: 6px 16px; font-size: 13px; }
.result-text { white-space: pre-wrap; line-height: 1.8; color: #212529; font-size: 17px; }
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
  color: #5c4db1;
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
  color: #5c4db1;
  border: 1px solid #5c4db1;
  border-radius: 4px;
  padding: 2px 10px;
  font-size: 13px;
  cursor: pointer;
}
.btn-candidate:hover { background: #ede9f8; }
.btn-candidate.selected {
  background: #5c4db1;
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
  background: #5c4db1;
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

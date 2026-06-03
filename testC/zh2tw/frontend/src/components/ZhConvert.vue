<template>
  <div class="container">
    <button class="btn btn-back" onclick="history.back()">← 返回</button>
    <h1 class="title">简繁互转</h1>

    <div class="direction-row">
      <button
        class="btn btn-dir"
        :class="{ active: direction === 'zh2tw' }"
        @click="direction = 'zh2tw'"
      >简 → 繁</button>
      <button
        class="btn btn-dir"
        :class="{ active: direction === 'tw2zh' }"
        @click="direction = 'tw2zh'"
      >繁 → 简</button>
    </div>

    <textarea
      v-model="input"
      class="textarea"
      :placeholder="direction === 'zh2tw' ? '请输入简体中文...' : '請輸入繁體中文...'"
      rows="8"
    ></textarea>

    <div class="btn-row">
      <button class="btn btn-primary" @click="convert" :disabled="loading">
        {{ loading ? '转换中…' : '转换' }}
      </button>
      <button class="btn btn-secondary" @click="clear">清空</button>
    </div>

    <p v-if="emptyError" class="error">请先输入内容</p>
    <p v-if="errorMsg" class="error">{{ errorMsg }}</p>

    <div v-if="result" class="result-box">
      <div class="result-header">
        <span>转换结果</span>
        <button class="btn btn-copy" @click="copy">复制结果</button>
      </div>
      <div class="result-text">{{ result }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const input = ref('')
const result = ref('')
const loading = ref(false)
const emptyError = ref(false)
const errorMsg = ref('')
const direction = ref('zh2tw')

async function convert() {
  emptyError.value = false
  errorMsg.value = ''
  result.value = ''

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
      result.value = data.answer_zh_tw
    }
  } catch (e) {
    errorMsg.value = '网络错误，请稍后重试'
  } finally {
    loading.value = false
  }
}

function clear() {
  input.value = ''
  result.value = ''
  emptyError.value = false
  errorMsg.value = ''
}

function copy() {
  navigator.clipboard.writeText(result.value)
}
</script>

<style scoped>
.container {
  max-width: 700px;
  margin: 40px auto;
  padding: 32px;
  background: #1e1e2e;
  border-radius: 12px;
  color: #cdd6f4;
  font-family: sans-serif;
}
.title {
  text-align: center;
  font-size: 24px;
  margin-bottom: 24px;
  color: #cba6f7;
}
.direction-row {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.btn-dir {
  padding: 8px 20px;
  border-radius: 8px;
  background: #45475a;
  color: #cdd6f4;
  border: 1px solid #45475a;
  font-size: 14px;
  cursor: pointer;
}
.btn-dir.active {
  background: #cba6f7;
  color: #1e1e2e;
  font-weight: bold;
  border-color: #cba6f7;
}
.textarea {
  width: 100%;
  background: #313244;
  border: 1px solid #45475a;
  border-radius: 8px;
  color: #cdd6f4;
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
  background: #cba6f7;
  color: #1e1e2e;
  font-weight: bold;
}
.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.btn-secondary {
  background: #45475a;
  color: #cdd6f4;
}
.btn-back {
  background: transparent;
  color: #a6adc8;
  border: 1px solid #45475a;
  margin-bottom: 16px;
  padding: 6px 16px;
  font-size: 13px;
}
.error {
  color: #f38ba8;
  margin-top: 12px;
}
.result-box {
  margin-top: 24px;
  background: #313244;
  border-radius: 8px;
  padding: 16px;
}
.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  color: #a6e3a1;
  font-weight: bold;
}
.btn-copy {
  background: #45475a;
  color: #cdd6f4;
  padding: 6px 16px;
  font-size: 13px;
}
.result-text {
  white-space: pre-wrap;
  line-height: 1.7;
}
</style>

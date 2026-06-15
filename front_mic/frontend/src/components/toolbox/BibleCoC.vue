<script setup>
import { ref, computed } from 'vue'

const inputText = ref('')
const loading   = ref(false)
const results   = ref([])
const copyMsg   = ref('')

const hasResults = computed(() => results.value.length > 0)

async function collectVerses() {
  if (!inputText.value.trim()) return
  loading.value = true
  results.value = []
  copyMsg.value = ''
  try {
    const res = await fetch('/api/testc/bible_co/process', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: inputText.value }),
    })
    results.value = await res.json()
  } finally {
    loading.value = false
  }
}

function clearAll() {
  inputText.value = ''
  results.value   = []
  copyMsg.value   = ''
}

function copyAll() {
  const lines = []
  for (const item of results.value) {
    const lineText = (item.text || '').trim()
    if (lineText) lines.push(lineText)
    for (const ver of item.vers || []) {
      const src = (ver.source || '').trim()
      const txt = (ver.text   || '').trim()
      if (src || txt) lines.push(`　${src}　${txt}`)
    }
  }
  const content = lines.join('\n')
  if (!content) return
  navigator.clipboard.writeText(content).then(() => {
    copyMsg.value = '已复制！'
    setTimeout(() => { copyMsg.value = '' }, 2000)
  })
}
</script>

<template>
  <div class="page">
    <div class="header">
      <button class="btn-back" @click="$router.back()">← 返回</button>
      <h2 class="title">经文汇集练习</h2>
      <p class="subtitle">正则识别引用 · ES 精确查库 · 零 AI 成本</p>
    </div>

    <div class="card">
      <textarea
        v-model="inputText"
        class="input-area"
        rows="12"
        placeholder="请输入纲目文字，每行一条，例如：&#10;壹　神是光—约壹一5&#10;贰　基督是神荣耀的光辉—来一3"
      />
      <div class="btn-row">
        <button class="btn btn-primary" :disabled="loading" @click="collectVerses">
          {{ loading ? '汇集中…' : '汇集经文' }}
        </button>
        <button class="btn btn-danger" @click="clearAll">清空</button>
      </div>
    </div>

    <div v-if="hasResults" class="card results-card">
      <div class="results-header">
        <span class="results-label">汇集结果</span>
        <div class="copy-area">
          <span v-if="copyMsg" class="copy-msg">{{ copyMsg }}</span>
          <button class="btn btn-outline" @click="copyAll">复制全部</button>
        </div>
      </div>

      <div v-for="(item, idx) in results" :key="idx" class="result-block">
        <div v-if="item.text.trim()" class="outline-line">{{ item.text }}</div>
        <div v-if="item.vers && item.vers.length > 0" class="verse-list">
          <div v-for="(ver, vidx) in item.vers" :key="vidx" class="verse-item">
            <span class="ver-source">{{ ver.source }}　</span>
            <span class="ver-text">{{ ver.text }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  background: #f7f5f0;
  padding: 1.5em;
  box-sizing: border-box;
}

.header {
  margin-bottom: 1.2em;
}

.btn-back {
  background: none;
  border: none;
  color: #2c5f8a;
  font-size: 0.9em;
  cursor: pointer;
  padding: 0;
  margin-bottom: 0.6em;
  display: inline-block;
}

.btn-back:hover {
  text-decoration: underline;
}

.title {
  font-size: 1.4em;
  font-weight: bold;
  color: #2c5f8a;
  margin: 0 0 0.2em 0;
}

.subtitle {
  font-size: 0.88em;
  color: #7a95ae;
  margin: 0;
}

.card {
  background: #ffffff;
  border: 1px solid #d0dce8;
  border-radius: 8px;
  padding: 1.2em;
  margin-bottom: 1.2em;
}

.input-area {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #d0dce8;
  border-radius: 6px;
  padding: 0.7em;
  font-size: 0.95em;
  color: #333;
  resize: vertical;
  outline: none;
  font-family: inherit;
  line-height: 1.7;
}

.input-area:focus {
  border-color: #2c5f8a;
}

.btn-row {
  display: flex;
  gap: 0.8em;
  margin-top: 0.9em;
}

.btn {
  padding: 0.45em 1.3em;
  border: none;
  border-radius: 5px;
  font-size: 0.92em;
  cursor: pointer;
  transition: opacity 0.15s;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background: #2c5f8a;
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.85;
}

.btn-danger {
  background: #e05c5c;
  color: #fff;
}

.btn-danger:hover {
  opacity: 0.85;
}

.btn-outline {
  background: transparent;
  color: #2c5f8a;
  border: 1px solid #2c5f8a;
}

.btn-outline:hover {
  background: #eef2f7;
}

.results-card {
  padding: 1em 1.2em;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1em;
  padding-bottom: 0.6em;
  border-bottom: 1px solid #d0dce8;
}

.results-label {
  font-weight: bold;
  color: #2c5f8a;
  font-size: 0.95em;
}

.copy-area {
  display: flex;
  align-items: center;
  gap: 0.6em;
}

.copy-msg {
  font-size: 0.82em;
  color: #4a9a6a;
}

.result-block {
  margin-bottom: 1em;
  padding-bottom: 1em;
  border-bottom: 1px solid #eef2f7;
}

.result-block:last-child {
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}

.outline-line {
  background: #eef2f7;
  color: #1e3f5a;
  font-weight: bold;
  padding: 0.5em 0.8em;
  border-radius: 5px;
  margin-bottom: 0.5em;
  font-size: 0.95em;
  line-height: 1.6;
}

.verse-list {
  padding-left: 0.5em;
}

.verse-item {
  margin-bottom: 0.4em;
  line-height: 1.7;
  font-size: 0.92em;
}

.ver-source {
  font-weight: bold;
  color: #2c5f8a;
}

.ver-text {
  color: #333;
}
</style>

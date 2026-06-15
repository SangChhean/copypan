<template>
  <div class="bible-co-wrap">
    <div class="bible-co-header">
      <span class="bible-co-title">经文汇集</span>
      <span class="bible-co-sub">自动识别纲目中的经文引用并取出经文正文</span>
    </div>

    <div class="bible-co-input-box">
      <textarea
        v-model="inputText"
        class="bible-co-textarea"
        placeholder="每行一条纲目，支持整篇粘贴"
        rows="8"
      />
      <button
        class="bible-co-btn"
        :disabled="!inputText.trim() || loading"
        @click="collectVerses"
      >
        {{ loading ? '汇集中…' : '汇集经文' }}
      </button>
    </div>

    <div v-if="results.length" class="bible-co-result-box">
      <div class="bible-co-copy-bar">
        <button class="bible-co-copy-btn" @click="copyAll">
          {{ copied ? '已复制' : '复制全部经文' }}
        </button>
      </div>

      <div
        v-for="(row, idx) in results"
        :key="idx"
        class="bible-co-row"
      >
        <div class="bible-co-line">{{ row.text }}</div>
        <div v-if="row.vers.length" class="bible-co-vers">
          <div
            v-for="(ver, vi) in row.vers"
            :key="vi"
            class="bible-co-ver-item"
          >
            <span class="ver-source">{{ ver.source }}：</span
            ><span class="ver-text">{{ ver.text }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const inputText = ref('')
const loading = ref(false)
const results = ref([])
const copied = ref(false)

async function collectVerses() {
  if (!inputText.value.trim()) return
  loading.value = true
  results.value = []
  try {
    const res = await fetch('/api/testa/bible_co/process', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: inputText.value })
    })
    results.value = await res.json()
  } catch (e) {
    console.error('经文汇集请求失败', e)
  } finally {
    loading.value = false
  }
}

function copyAll() {
  const blocks = []
  for (const row of results.value) {
    let block = row.text
    for (const ver of row.vers) {
      block += '\n' + ver.source + '：' + ver.text
    }
    blocks.push(block)
  }
  if (!blocks.length) return
  navigator.clipboard.writeText(blocks.join('\n\n')).then(() => {
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  })
}
</script>

<style scoped>
.bible-co-wrap {
  max-width: 800px;
  margin: 0 auto;
  padding: 2rem 1.5rem;
  font-family: sans-serif;
}

.bible-co-header {
  background: #4a6fa5;
  color: #fff;
  padding: 0.9rem 1.25rem;
  border-radius: 8px 8px 0 0;
  display: flex;
  align-items: baseline;
  gap: 1rem;
}
.bible-co-title {
  font-size: 1.1rem;
  font-weight: 600;
}
.bible-co-sub {
  font-size: 0.82rem;
  opacity: 0.85;
}

.bible-co-input-box {
  background: #fff;
  border: 1px solid #d0dce8;
  border-top: none;
  border-radius: 0 0 8px 8px;
  padding: 1.1rem 1.25rem;
  margin-bottom: 1.25rem;
}
.bible-co-textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 0.65rem 0.75rem;
  font-size: 0.92rem;
  border: 1px solid #c0cfe0;
  border-radius: 6px;
  resize: vertical;
  outline: none;
  line-height: 1.7;
  color: #333;
}
.bible-co-textarea:focus {
  border-color: #4a6fa5;
}
.bible-co-btn {
  margin-top: 0.75rem;
  background: #4a6fa5;
  color: #fff;
  border: none;
  padding: 0.5rem 1.5rem;
  border-radius: 6px;
  font-size: 0.92rem;
  cursor: pointer;
  transition: background 0.2s;
}
.bible-co-btn:hover:not(:disabled) {
  background: #3a5a8a;
}
.bible-co-btn:disabled {
  background: #a0b4c8;
  cursor: not-allowed;
}

.bible-co-result-box {
  background: #fff;
  border: 1px solid #d0dce8;
  border-radius: 8px;
  padding: 1.1rem 1.25rem;
}

.bible-co-copy-bar {
  text-align: right;
  margin-bottom: 1rem;
}
.bible-co-copy-btn {
  background: #fff;
  color: #4a6fa5;
  border: 1px solid #4a6fa5;
  padding: 0.35rem 1.1rem;
  border-radius: 6px;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
}
.bible-co-copy-btn:hover {
  background: #4a6fa5;
  color: #fff;
}

.bible-co-row {
  margin-bottom: 1.1rem;
}
.bible-co-line {
  font-size: 1rem;
  color: #222;
  border-left: 3px solid #4a6fa5;
  padding-left: 0.75rem;
  border-radius: 0;
  margin-bottom: 0.4rem;
}
.bible-co-vers {
  margin-left: 1.25rem;
}
.bible-co-ver-item {
  font-size: 0.9rem;
  line-height: 1.75;
  margin-bottom: 0.2rem;
}
.ver-source {
  color: #4a6fa5;
  font-weight: 600;
}
.ver-text {
  color: #222;
  font-weight: 600;
}
</style>

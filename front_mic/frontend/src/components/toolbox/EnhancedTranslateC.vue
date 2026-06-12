<script setup>
import { ref, computed } from 'vue'

const inputText = ref('')
const loading = ref(false)
const rows = ref([])
const costUsd = ref(0)
const expandedRefs = ref({})

const API_BASE = '/api/testc/enhanced-translate'

const STATUS_CONFIG = {
  pool:      { label: '直接引用', color: '#52c41a', bg: '#f6ffed', border: '#b7eb8f' },
  retrieved: { label: '参考翻译', color: '#1890ff', bg: '#e6f4ff', border: '#91caff' },
  none:      { label: '无匹配',   color: '#8c8c8c', bg: '#fafafa', border: '#d9d9d9' },
}

async function startTranslate() {
  if (!inputText.value.trim()) return
  loading.value = true
  rows.value = []
  costUsd.value = 0
  expandedRefs.value = {}
  try {
    const res = await fetch(`${API_BASE}/translate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: inputText.value }),
    })
    const data = await res.json()
    rows.value = data.rows || []
    costUsd.value = data.cost_usd || 0
  } catch (e) {
    alert('请求失败：' + e.message)
  } finally {
    loading.value = false
  }
}

async function onBlurLine(row) {
  const newEn = (row.en || '').trim()
  if (!newEn) return
  try {
    const res = await fetch(`${API_BASE}/update_translation`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ original_line: row.line, new_translation: newEn }),
    })
    const data = await res.json()
    if (data.success) {
      row._saved = true
      setTimeout(() => { row._saved = false }, 1500)
    }
  } catch (e) {
    console.warn('写回失败', e)
  }
}

function copyAll() {
  const text = rows.value.map(r => r.en).join('\n')
  navigator.clipboard.writeText(text).then(() => alert('已复制到剪贴板'))
}

function toggleRef(i) {
  expandedRefs.value[i] = !expandedRefs.value[i]
}

const stats = computed(() => ({
  total:     rows.value.length,
  pool:      rows.value.filter(r => r.status === 'pool').length,
  retrieved: rows.value.filter(r => r.status === 'retrieved').length,
  none:      rows.value.filter(r => r.status === 'none').length,
}))
</script>

<template>
  <div class="page">
    <div class="page-header">
      <span class="back" @click="() => window.location.hash = '/'">← 返回</span>
      <span class="title">增强式翻译练习</span>
      <span class="subtitle">testC · 端口 8062</span>
    </div>

    <div class="main">
      <!-- 输入区 -->
      <div class="panel">
        <div class="panel-label">纲目输入 <small>（每行一条，最多 200 行）</small></div>
        <textarea
          v-model="inputText"
          class="input-area"
          placeholder="请粘贴纲目内容，每行一条……"
          rows="10"
        />
        <div class="action-row">
          <button
            class="btn-primary"
            :disabled="loading || !inputText.trim()"
            @click="startTranslate"
          >
            {{ loading ? '翻译中，请稍候（约 20～60 秒）……' : '开始翻译' }}
          </button>
        </div>
      </div>

      <template v-if="rows.length">
        <!-- 统计栏 -->
        <div class="stats-bar">
          <span>共 {{ stats.total }} 行</span>
          <span><span class="dot" style="background:#52c41a"></span>直接引用 {{ stats.pool }}</span>
          <span><span class="dot" style="background:#1890ff"></span>参考翻译 {{ stats.retrieved }}</span>
          <span><span class="dot" style="background:#8c8c8c"></span>无匹配 {{ stats.none }}</span>
          <span class="cost">本次花费 ${{ costUsd.toFixed(6) }}</span>
        </div>

        <!-- 英文全文 -->
        <div class="panel">
          <div class="panel-label">
            英文全文
            <button class="btn-copy" @click="copyAll">复制全部</button>
          </div>
          <div class="result-text">{{ rows.map(r => r.en).join('\n') }}</div>
        </div>

        <!-- 逐行结果 -->
        <div class="panel">
          <div class="panel-label">逐行结果（可编辑译文，失焦自动保存）</div>
          <div
            v-for="(row, i) in rows"
            :key="i"
            class="line-item"
            :style="{
              borderLeft: `4px solid ${STATUS_CONFIG[row.status]?.color}`,
              background: STATUS_CONFIG[row.status]?.bg,
            }"
          >
            <div class="line-top">
              <span
                class="status-tag"
                :style="{
                  color:      STATUS_CONFIG[row.status]?.color,
                  border:     `1px solid ${STATUS_CONFIG[row.status]?.border}`,
                  background: '#fff',
                }"
              >{{ STATUS_CONFIG[row.status]?.label }}</span>
              <span class="line-zh">{{ row.line }}</span>
              <span v-if="row.ref" class="ref-toggle" @click="toggleRef(i)">
                {{ expandedRefs[i] ? '▲ 收起参考' : '▼ 查看参考' }}
              </span>
            </div>

            <div v-if="row.ref && expandedRefs[i]" class="ref-block">
              <div class="ref-zh">{{ row.ref.text }}</div>
              <div class="ref-en">{{ row.ref.en }}</div>
            </div>

            <textarea
              v-model="row.en"
              class="line-en"
              :class="{ saved: row._saved }"
              rows="2"
              @blur="onBlurLine(row)"
            />
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
* { box-sizing: border-box; }
.page { min-height: 100vh; background: #f0f4f8; font-family: 'Segoe UI', 'PingFang SC', sans-serif; }
.page-header {
  display: flex; align-items: center; gap: 16px;
  padding: 14px 28px; background: #1a3a5c; color: #fff;
  font-size: 1.1rem; font-weight: bold;
}
.back { cursor: pointer; color: #7ec8f7; font-size: 0.95rem; }
.back:hover { color: #fff; }
.title { flex: 1; }
.subtitle { font-size: 0.8rem; color: #7ec8f7; font-weight: normal; }
.main { max-width: 900px; margin: 0 auto; padding: 24px 16px; }
.panel {
  background: #fff; border-radius: 10px; padding: 20px;
  margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.07);
}
.panel-label { font-weight: bold; color: #1a3a5c; margin-bottom: 12px; font-size: 1rem; }
.input-area {
  width: 100%; padding: 12px; border: 1px solid #c8d8e8;
  border-radius: 6px; font-size: 0.95rem; resize: vertical;
  font-family: inherit; line-height: 1.6;
}
.input-area:focus { outline: none; border-color: #1890ff; }
.action-row { margin-top: 12px; }
.btn-primary {
  padding: 10px 28px; background: #1a3a5c; color: #fff;
  border: none; border-radius: 6px; font-size: 1rem; cursor: pointer;
}
.btn-primary:hover:not(:disabled) { background: #245a8a; }
.btn-primary:disabled { background: #aaa; cursor: not-allowed; }
.stats-bar {
  display: flex; align-items: center; gap: 18px; flex-wrap: wrap;
  padding: 12px 20px; background: #fff; border-radius: 10px;
  margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.07); font-size: 0.93rem;
}
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 4px; vertical-align: middle; }
.cost { margin-left: auto; color: #888; font-size: 0.88rem; }
.result-text {
  white-space: pre-wrap; font-size: 0.95rem; color: #333; line-height: 1.8;
  max-height: 300px; overflow-y: auto; background: #f8fafb;
  padding: 12px; border-radius: 6px;
}
.btn-copy {
  margin-left: 12px; padding: 2px 12px; font-size: 0.85rem;
  border: 1px solid #1890ff; color: #1890ff; background: #fff;
  border-radius: 4px; cursor: pointer;
}
.btn-copy:hover { background: #e6f4ff; }
.line-item { padding: 12px 14px; margin-bottom: 10px; border-radius: 6px; }
.line-top { display: flex; align-items: flex-start; gap: 10px; flex-wrap: wrap; margin-bottom: 6px; }
.status-tag { padding: 1px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: bold; white-space: nowrap; }
.line-zh { font-size: 0.95rem; color: #333; flex: 1; line-height: 1.6; }
.ref-toggle { font-size: 0.8rem; color: #1890ff; cursor: pointer; white-space: nowrap; }
.ref-toggle:hover { text-decoration: underline; }
.ref-block {
  background: #fffbe6; border: 1px solid #ffe58f;
  border-radius: 4px; padding: 8px 12px; margin-bottom: 8px;
  font-size: 0.85rem; line-height: 1.6;
}
.ref-zh { color: #555; margin-bottom: 4px; }
.ref-en { color: #1a3a5c; font-style: italic; }
.line-en {
  width: 100%; padding: 8px 10px; border: 1px solid #d0dce8;
  border-radius: 4px; font-size: 0.93rem; resize: vertical;
  font-family: inherit; line-height: 1.6; background: #fff; transition: border-color .2s;
}
.line-en:focus { outline: none; border-color: #1890ff; }
.line-en.saved { border-color: #52c41a !important; }
</style>

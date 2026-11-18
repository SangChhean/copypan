<template>
  <div class="hymn-message">
    <div v-if="notes.length" class="hymn-notes">
      <div v-for="(n, i) in notes" :key="i" class="hymn-note">{{ n }}</div>
    </div>

    <div v-for="(h, hi) in hymns" :key="hi" class="hymn-card">
      <div class="hymn-title-row">
        <span class="hymn-title-text">{{ hymnTitle(h) }}</span>
        <button
          v-if="needsFold(h)"
          type="button"
          class="fold-btn"
          @click="toggleFold(hi)"
        >
          {{ folded[hi] === false ? '收起全文' : '展开全文' }}
        </button>
      </div>
      <div
        class="hymn-body"
        :class="{ folded: needsFold(h) && folded[hi] !== false }"
      >
        <pre class="hymn-lyrics">{{ h.text || '' }}</pre>
      </div>
    </div>

    <div v-if="showMinistry" class="ministry-header">
      <span class="ministry-title">相关职事信息</span>
      <span v-if="generating" class="ministry-generating">
        <span class="dot-flashing"></span>
        生成中
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, watch } from 'vue'

const props = defineProps({
  hymnData: { type: Object, default: null },
  generating: { type: Boolean, default: false },
  showMinistry: { type: Boolean, default: true },
})

const folded = reactive({})

const hymns = computed(() => {
  const d = props.hymnData
  if (!d) return []
  if (Array.isArray(d.hymns)) return d.hymns
  if (d.text) return [d]
  return []
})

const notes = computed(() => {
  const n = props.hymnData && props.hymnData.notes
  return Array.isArray(n) ? n.filter(Boolean) : []
})

const FOLD_CHARS = 480

function needsFold(h) {
  return String((h && h.text) || '').length > FOLD_CHARS
}

function toggleFold(hi) {
  // 默认折叠：undefined/true = 折叠；false = 展开
  folded[hi] = folded[hi] === false ? true : false
}

function hymnTitle(h) {
  const series = h.series_zh || h.series || '大本'
  const num = h.hymn_number != null ? h.hymn_number : ''
  const name = (h.name || h.title || '').trim()
  const head = num !== '' ? `${series}第${num}首` : series
  if (!name) return head
  // name 常已含「诗歌第N首　主题」——若重复则只显示 name
  if (name.includes(String(num)) && (name.includes('第') || name.includes(series))) {
    return name.replace(/\s*<[^>]+>[\s\S]*$/u, '').trim() || name
  }
  return `${head}　${name}`
}

watch(
  hymns,
  (list) => {
    list.forEach((h, i) => {
      if (needsFold(h) && folded[i] === undefined) folded[i] = true
    })
  },
  { immediate: true },
)
</script>

<style scoped>
.hymn-message {
  margin-top: 4px;
}
.hymn-notes {
  margin-bottom: 10px;
}
.hymn-note {
  padding: 8px 10px;
  background: #fff8f0;
  border-left: 3px solid #c80;
  color: #643;
  font-size: 14px;
  margin-bottom: 6px;
}
.hymn-card {
  margin-bottom: 14px;
}
.hymn-title-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.hymn-title-text {
  font-size: 1.15em;
  font-weight: 600;
  color: #222;
  line-height: 1.4;
}
.fold-btn {
  flex-shrink: 0;
  background: none;
  border: 1px solid #ccc;
  border-radius: 3px;
  padding: 2px 8px;
  font-size: 12px;
  color: #456;
  cursor: pointer;
}
.fold-btn:hover {
  background: #f5f5f5;
}
.hymn-body.folded {
  max-height: 14em;
  overflow: hidden;
  position: relative;
}
.hymn-body.folded::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 2.5em;
  background: linear-gradient(transparent, #fff);
  pointer-events: none;
}
.hymn-lyrics {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
  font-size: 15px;
  line-height: 1.75;
  color: #222;
}
@media (max-width: 768px) {
  .hymn-title-text { font-size: 1.05em; }
  .hymn-lyrics { font-size: 14px; line-height: 1.7; }
  .hymn-note { font-size: 13px; }
}
.ministry-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px solid #eee;
}
.ministry-title {
  font-weight: 600;
  color: #444;
  font-size: 14px;
}
.ministry-generating {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #888;
  font-size: 13px;
}
.dot-flashing {
  position: relative;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #888;
  animation: flash 1s infinite linear alternate;
}
@keyframes flash {
  0% { opacity: 0.25; }
  100% { opacity: 1; }
}
</style>

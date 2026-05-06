<template>
  <div class="bible-message">
    <!-- 单节 -->
    <template v-if="isSingle">
      <div class="verse-text">
        <span v-html="renderedVerseTextSingle"></span>
      </div>

      <div v-if="crossrefItemsSingle.length || footnoteItemsSingle.length" class="verse-toggles">
        <span
          v-if="crossrefItemsSingle.length"
          class="toggle-tag section-toggle"
          @click="showCrossrefs = !showCrossrefs"
        >
          {{ showCrossrefs ? '▼' : '▶' }} {{ labels.crossrefs }}
        </span>
        <span
          v-if="footnoteItemsSingle.length"
          class="toggle-tag section-toggle"
          @click="showFootnotes = !showFootnotes"
        >
          {{ showFootnotes ? '▼' : '▶' }} {{ labels.footnotes }}
        </span>
      </div>

      <div v-if="crossrefItemsSingle.length" class="bible-fold-block">
        <transition name="bible-collapse">
          <div v-show="showCrossrefs" class="bible-section-body bible-section-body--compact verse-crossrefs">
            <div v-for="item in crossrefItemsSingle" :key="item.label" class="bible-cross-item">
              <span class="bible-cross-label">{{ item.label }}.</span>
              <span class="bible-cross-content">
                <span v-for="(r, i) in item.refs" :key="i" class="bible-cross-ref">
                  <span class="bible-cross-ref-label">{{ r.ref }}</span>
                  {{ r.text }}
                </span>
              </span>
            </div>
          </div>
        </transition>
      </div>

      <div v-if="footnoteItemsSingle.length" class="bible-fold-block">
        <transition name="bible-collapse">
          <div v-show="showFootnotes" class="bible-section-body bible-section-body--compact verse-footnotes">
            <div v-for="item in footnoteItemsSingle" :key="item.num" class="bible-note-item">
              <template v-if="currentLang === 'en'">
                <div class="fn-en-row">
                  <span class="fn-en-prefix">{{ parseEnFootnote(item.text).prefix }}</span>
                </div>
                <div class="fn-en-body">{{ parseEnFootnote(item.text).body }}</div>
              </template>
              <template v-else>
                <span class="bible-note-num">注{{ item.num }}</span>
                <span class="bible-note-content">{{ item.text }}</span>
              </template>
            </div>
          </div>
        </transition>
      </div>
    </template>

    <!-- 多节：范围 / 整章 -->
    <template v-else-if="isMulti">
      <div v-for="(v, i) in versesList" :key="verseRowKey(v, i)" class="verse-item">
        <div class="verse-row">
          <span class="verse-num">{{ v.verse }}</span>
          <span class="verse-text" v-html="renderVerseText(verseTextFor(v))"></span>
        </div>

        <div v-if="hasCrossrefs(v) || hasFootnotes(v)" class="verse-toggles">
          <span
            v-if="hasCrossrefs(v)"
            class="toggle-tag section-toggle"
            @click="toggleCrossrefs(i)"
          >
            {{ showCrossrefsByVerse[i] ? '▼' : '▶' }} {{ labels.crossrefs }}
          </span>
          <span
            v-if="hasFootnotes(v)"
            class="toggle-tag section-toggle"
            @click="toggleFootnotes(i)"
          >
            {{ showFootnotesByVerse[i] ? '▼' : '▶' }} {{ labels.footnotes }}
          </span>
        </div>

        <div v-if="hasCrossrefs(v)" class="bible-fold-block">
          <transition name="bible-collapse">
            <div v-show="showCrossrefsByVerse[i]" class="bible-section-body bible-section-body--compact verse-crossrefs">
              <div
                v-for="item in crossrefItemsFor(v)"
                :key="item.label + '-' + (v.verse ?? i)"
                class="bible-cross-item"
              >
                <span class="bible-cross-label">{{ item.label }}.</span>
                <span class="bible-cross-content">
                  <span v-for="(r, ri) in item.refs" :key="ri" class="bible-cross-ref">
                    <span class="bible-cross-ref-label">{{ r.ref }}</span>
                    {{ r.text }}
                  </span>
                </span>
              </div>
            </div>
          </transition>
        </div>

        <div v-if="hasFootnotes(v)" class="bible-fold-block">
          <transition name="bible-collapse">
            <div v-show="showFootnotesByVerse[i]" class="bible-section-body bible-section-body--compact verse-footnotes">
              <div v-for="item in footnoteItemsFor(v)" :key="String(item.num) + '-' + i" class="bible-note-item">
                <template v-if="currentLang === 'en'">
                  <div class="fn-en-row">
                    <span class="fn-en-prefix">{{ parseEnFootnote(item.text).prefix }}</span>
                  </div>
                  <div class="fn-en-body">{{ parseEnFootnote(item.text).body }}</div>
                </template>
                <template v-else>
                  <span class="bible-note-num">注{{ item.num }}</span>
                  <span class="bible-note-content">{{ item.text }}</span>
                </template>
              </div>
            </div>
          </transition>
        </div>
      </div>
    </template>

    <div class="ministry-header">
      <span class="ministry-title">{{ labels.ministry }}</span>
      <span v-if="generating" class="ministry-generating">
        <span class="dot-flashing"></span>
        {{ labels.generating }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  verse: { type: Object, default: null },
  verses: { type: Array, default: null },
  queryType: { type: String, default: 'verse' },
  lang: { type: String, default: 'gb' },
  generating: { type: Boolean, default: false },
})

const textKeyMap = {
  gb: 'text_gb',
  big5: 'text_big5',
  en: 'text_en',
}
const fnKeyMap = {
  gb: 'zh',
  big5: 'zh_big5',
  en: 'en',
}
const crossTextKeyMap = {
  gb: 'text_gb',
  big5: 'text_big5',
  en: 'text_en',
}
const crossRefKeyMap = {
  gb: 'ref_gb',
  big5: 'ref_big5',
  en: 'ref_en',
}

const showCrossrefs = ref(true)
const showFootnotes = ref(true)
const showCrossrefsByVerse = ref([])
const showFootnotesByVerse = ref([])

const isMulti = computed(
  () =>
    (props.queryType === 'range' || props.queryType === 'chapter') &&
    Array.isArray(props.verses) &&
    props.verses.length > 0,
)
const isSingle = computed(() => !isMulti.value && props.queryType === 'verse')

const versesList = computed(() => (Array.isArray(props.verses) ? props.verses : []))

watch(
  versesList,
  (list) => {
    const n = list.length
    showCrossrefsByVerse.value = Array.from({ length: n }, () => false)
    showFootnotesByVerse.value = Array.from({ length: n }, () => false)
  },
  { immediate: true, deep: true },
)

function toggleCrossrefs(i) {
  const next = showCrossrefsByVerse.value.slice()
  next[i] = !next[i]
  showCrossrefsByVerse.value = next
}

function toggleFootnotes(i) {
  const next = showFootnotesByVerse.value.slice()
  next[i] = !next[i]
  showFootnotesByVerse.value = next
}

function verseRowKey(v, i) {
  return v?.verse != null ? `v-${v.verse}` : `i-${i}`
}

const currentLang = computed(() => {
  const l = props.lang
  if (l === 'zh' || l === 'gb') return 'gb'
  if (l === 'zh_tw' || l === 'big5') return 'big5'
  if (l === 'en') return 'en'
  return 'gb'
})

const labels = computed(() => {
  const l = currentLang.value
  if (l === 'big5') {
    return {
      crossrefs: '串珠',
      footnotes: '注解',
      ministry: '相關職事信息',
      generating: '生成中',
    }
  }
  if (l === 'en') {
    return {
      crossrefs: 'Cross References',
      footnotes: 'Footnotes',
      ministry: 'Related Ministry Messages',
      generating: 'Generating',
    }
  }
  return {
    crossrefs: '串珠',
    footnotes: '注解',
    ministry: '相关职事信息',
    generating: '生成中',
  }
})

function renderVerseText(text) {
  if (!text) return ''
  return String(text)
    .replace(/\[Fn(\d+)\]/g, '<sup class="fn-mark">$1</sup>')
    .replace(/\[Cr([a-z])\]/g, '<sup class="cr-mark">$1</sup>')
}

function parseEnFootnote(text) {
  if (!text) return { prefix: null, body: text }
  // Match "chapter:verse index " at the start, e.g. "1:20 1 "
  const m = text.match(/^(\d+:\d+\s+\d+)\s+(.+)$/s)
  if (m) return { prefix: m[1], body: m[2] }
  return { prefix: null, body: text }
}

function verseTextFor(v) {
  const key = textKeyMap[currentLang.value]
  return String(v?.[key] || v?.text_gb || '').trim()
}

const renderedVerseTextSingle = computed(() => {
  const key = textKeyMap[currentLang.value]
  const text = String(props.verse?.[key] || props.verse?.text_gb || '').trim()
  return renderVerseText(text)
})

function crossrefItemsFor(verse) {
  if (!Array.isArray(verse?.crossrefs)) return []
  const groups = []
  const seen = {}
  const textKey = crossTextKeyMap[currentLang.value]
  const refKey = crossRefKeyMap[currentLang.value]
  for (const item of verse.crossrefs) {
    const label = String(item?.label || '?').trim() || '?'
    if (!seen[label]) {
      seen[label] = { label, refs: [] }
      groups.push(seen[label])
    }
    for (const r of item?.refs || []) {
      seen[label].refs.push({
        ref: String(r?.[refKey] || r?.ref_gb || '').trim(),
        text: String(r?.[textKey] || r?.text_gb || '').trim(),
      })
    }
  }
  return groups
}

const crossrefItemsSingle = computed(() => crossrefItemsFor(props.verse || {}))

function footnoteItemsFor(verse) {
  const fnKey = fnKeyMap[currentLang.value] || 'zh'
  return (verse?.footnotes || [])
    .filter(fn => {
      const content = fn?.[fnKey]
      return content && content.trim().length > 0
    })
    .map(fn => ({
      num: fn.num,
      text: fn[fnKey],
    }))
}

const footnoteItemsSingle = computed(() => footnoteItemsFor(props.verse || {}))

function hasCrossrefs(v) {
  return crossrefItemsFor(v).length > 0
}

function hasFootnotes(v) {
  const fnKey = fnKeyMap[currentLang.value] || 'zh'
  return (v?.footnotes || []).some(fn => fn?.[fnKey] && fn[fnKey].trim().length > 0)
}
</script>

<style scoped>
.bible-message {
  color: var(--color-text);
}

.verse-text {
  font-size: 16px;
  font-weight: 600;
  line-height: 2.2;
  color: var(--color-text);
}

.verse-item {
  padding: 6px 0;
  border-bottom: none;
  margin-bottom: 4px;
}

.verse-item:last-child {
  margin-bottom: 0;
}

.verse-toggles {
  display: flex;
  gap: 12px;
  margin-top: 4px;
}

/* 多节：与 .verse-row 内正文左缘对齐（.verse-num min-width 20px + gap 8px） */
.verse-item .verse-toggles {
  padding-left: 28px;
}

.verse-crossrefs,
.verse-footnotes {
  padding-left: 0;
}

.verse-item .verse-crossrefs,
.verse-item .verse-footnotes {
  padding-left: 28px;
}

.toggle-tag {
  font-size: 12px;
  color: var(--color-text-secondary);
  cursor: pointer;
  user-select: none;
}

.toggle-tag:hover {
  color: var(--color-primary);
}

.section-toggle {
  font-size: 12px;
  margin-top: 4px;
  margin-bottom: 2px;
  color: var(--color-text-secondary);
  cursor: pointer;
  user-select: none;
}

.verse-toggles .section-toggle {
  margin-top: 0;
  margin-bottom: 0;
}

.bible-fold-block {
  margin-top: 2px;
}

.bible-section-body--compact .bible-cross-item,
.bible-section-body--compact .bible-note-item {
  margin-bottom: 4px;
}

.verse-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.verse-num {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-primary);
  min-width: 20px;
  flex-shrink: 0;
}

.verse-row .verse-text {
  flex: 1;
  min-width: 0;
}

.bible-section-body {
  overflow: hidden;
}

.bible-cross-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 14px;
  line-height: 1.8;
  margin-bottom: 4px;
}

.bible-cross-label {
  color: var(--color-primary);
  font-weight: 600;
  flex-shrink: 0;
}

.bible-cross-content {
  display: flex;
  flex-direction: column;
}

.bible-cross-ref {
  display: block;
}

.bible-cross-ref-label {
  color: var(--color-primary);
  font-weight: 600;
  margin-right: 4px;
}

.bible-note-item {
  font-size: 14px;
  line-height: 1.8;
  margin-bottom: 8px;
}

.bible-note-num {
  color: var(--color-primary);
  font-weight: 600;
  margin-right: 6px;
}

.fn-en-prefix {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-primary);
  display: block;
  margin-bottom: 2px;
}

.fn-en-body {
  font-size: 14px;
  line-height: 1.8;
  color: var(--color-text);
  padding-left: 12px;
  margin-bottom: 8px;
}

.verse-text :deep(.fn-mark) {
  vertical-align: super;
  font-size: 9px;
  font-weight: 600;
  color: var(--color-primary);
  line-height: 0;
  margin-right: 1px;
}

.verse-text :deep(.cr-mark) {
  vertical-align: super;
  font-size: 9px;
  color: var(--color-text-secondary);
  line-height: 0;
  margin-right: 1px;
}

.ministry-header {
  display: flex;
  align-items: center;
  gap: 8px;
  border-top: 1px solid var(--color-border);
  margin: 12px 0 8px;
  padding-top: 12px;
}

.ministry-title {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.ministry-generating {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.dot-flashing {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-primary);
  animation: dotFlashing 1s infinite alternate;
}

@keyframes dotFlashing {
  0% {
    opacity: 0.2;
  }
  100% {
    opacity: 1;
  }
}

.bible-collapse-enter-active,
.bible-collapse-leave-active {
  transition: all 0.2s ease;
}

.bible-collapse-enter-from,
.bible-collapse-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

@media (max-width: 768px) {
  .verse-text {
    font-size: 15px;
  }

  .bible-cross-item,
  .bible-note-item {
    font-size: 13px;
  }
}
</style>

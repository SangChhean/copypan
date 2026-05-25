<template>
  <div class="bible-message">
    <div v-if="verseTitle" class="verse-title-row">
      <span class="verse-title-text">{{ verseTitle }}</span>
    </div>
    <!-- 单节 -->
    <template v-if="isSingle">
      <div class="verse-text">
        <span v-html="renderedVerseTextSingle"></span>
      </div>

      <div
        v-if="crossrefItemsSingle.length || footnoteItemsSingle.length || (SHOW_BIBLE_EXTRA_LINKS && verse && BIBLEHUB_MAP[verse.book])"
        class="verse-toggles"
      >
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
        <a
          v-if="SHOW_BIBLE_EXTRA_LINKS && verse && BIBLEHUB_MAP[verse.book]"
          :href="biblehubUrl(verse.book, verse.chapter, verse.verse)"
          target="_blank"
          rel="noopener"
          class="toggle-tag biblehub-link"
        >🔗 {{ labels.biblehub }}</a>
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
      <!-- 整章模式：生命读经按钮，放在所有经文之前 -->
      <div v-if="SHOW_BIBLE_EXTRA_LINKS && queryType === 'chapter' && versesList.length" class="chapter-header">
        <span ref="lsmRootRef" class="toggle-tag lsm-btn" style="position:relative">
          <span @click.stop="toggleLsmDropdown">📖 {{ labels.lsm }}</span>
          <div v-if="showLsmDropdown" class="lsm-dropdown">
            <template v-if="getLsmMessages(versesList[0].book, versesList[0].chapter).length">
              <a
                v-for="msg in getLsmMessages(versesList[0].book, versesList[0].chapter)"
                :key="msg.index"
                :href="lsmPdfUrl(LSM_MAP[versesList[0].book], msg.index)"
                target="_blank"
                rel="noopener"
                class="lsm-dropdown-item"
                @click="showLsmDropdown = false"
              ><span style="white-space:nowrap">{{ msg.label }}</span><span class="lsm-ref">{{ msg.reference }}</span></a>
            </template>
            <span v-else class="lsm-dropdown-item lsm-empty">暂无对应篇目</span>
          </div>
        </span>
      </div>
      <div v-for="(v, i) in versesList" :key="verseRowKey(v, i)" class="verse-item">
        <div class="verse-row">
          <span class="verse-num">{{ v.verse }}</span>
          <span class="verse-text" v-html="renderVerseText(verseTextFor(v))"></span>
        </div>

        <div
          v-if="hasCrossrefs(v) || hasFootnotes(v) || (SHOW_BIBLE_EXTRA_LINKS && v.book && BIBLEHUB_MAP[v.book])"
          class="verse-toggles"
        >
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
          <a
            v-if="SHOW_BIBLE_EXTRA_LINKS && v.book && BIBLEHUB_MAP[v.book]"
            :href="biblehubUrl(v.book, v.chapter, v.verse)"
            target="_blank"
            rel="noopener"
            class="toggle-tag biblehub-link"
          >🔗 {{ labels.biblehub }}</a>
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
import { computed, onMounted, ref, watch } from 'vue'

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

// book编号 → BibleHub interlinear路径名
const BIBLEHUB_MAP = {
  1: 'genesis', 2: 'exodus', 3: 'leviticus', 4: 'numbers', 5: 'deuteronomy',
  6: 'joshua', 7: 'judges', 8: 'ruth', 9: '1_samuel', 10: '2_samuel',
  11: '1_kings', 12: '2_kings', 13: '1_chronicles', 14: '2_chronicles',
  15: 'ezra', 16: 'nehemiah', 17: 'esther', 18: 'job', 19: 'psalms',
  20: 'proverbs', 21: 'ecclesiastes', 22: 'songs', 23: 'isaiah',
  24: 'jeremiah', 25: 'lamentations', 26: 'ezekiel', 27: 'daniel',
  28: 'hosea', 29: 'joel', 30: 'amos', 31: 'obadiah', 32: 'jonah',
  33: 'micah', 34: 'nahum', 35: 'habakkuk', 36: 'zephaniah', 37: 'haggai',
  38: 'zechariah', 39: 'malachi', 40: 'matthew', 41: 'mark', 42: 'luke',
  43: 'john', 44: 'acts', 45: 'romans', 46: '1_corinthians', 47: '2_corinthians',
  48: 'galatians', 49: 'ephesians', 50: 'philippians', 51: 'colossians',
  52: '1_thessalonians', 53: '2_thessalonians', 54: '1_timothy', 55: '2_timothy',
  56: 'titus', 57: 'philemon', 58: 'hebrews', 59: 'james', 60: '1_peter',
  61: '2_peter', 62: '1_john', 63: '2_john', 64: '3_john', 65: 'jude', 66: 'revelation',
}

// book编号 → LSM PDF前缀
const LSM_MAP = {
  1: 'genesis', 2: 'exodus', 3: 'leviticus', 4: 'numbers', 5: 'deuteronomy',
  6: 'joshua', 7: 'judges', 8: 'ruth', 9: 'samuel', 10: 'samuel',
  11: 'kings', 12: 'kings', 13: 'chronicles', 14: 'chronicles',
  15: 'ezra', 16: 'nehemiah', 17: 'esther', 18: 'job', 19: 'psalms',
  20: 'proverbs', 21: 'ecclesiastes', 22: 'song-of-songs', 23: 'isaiah',
  24: 'jeremiah', 25: 'lamentations', 26: 'ezekiel', 27: 'daniel',
  28: 'hosea', 29: 'joel', 30: 'amos', 31: 'obadiah', 32: 'jonah',
  33: 'micah', 34: 'nahum', 35: 'habakkuk', 36: 'zephaniah', 37: 'haggai',
  38: 'zechariah', 39: 'malachi', 40: 'matthew', 41: 'mark', 42: 'luke',
  43: 'john', 44: 'acts', 45: 'romans', 46: '1-corinthians', 47: '2-corinthians',
  48: 'galatians', 49: 'ephesians', 50: 'philippians', 51: 'colossians',
  52: '1-thessalonians', 53: '2-thessalonians', 54: '1-timothy', 55: '2-timothy',
  56: 'titus', 57: 'philemon', 58: 'hebrews', 59: 'james', 60: '1-peter',
  61: '2-peter', 62: '1-john', 63: '2-john', 64: '3-john', 65: 'jude', 66: 'revelation',
}

/** 经文问答：暂时隐藏生命读经、原文对照入口（仅前端） */
const SHOW_BIBLE_EXTRA_LINKS = false

const LSM_BASE_URL = '/lsm/'

function biblehubUrl(book, chapter, verse) {
  const name = BIBLEHUB_MAP[book]
  if (!name) return null
  return `https://biblehub.com/interlinear/${name}/${chapter}-${verse}.htm`
}

function lsmPdfUrl(prefix, index) {
  return `${LSM_BASE_URL}${prefix}-${String(index).padStart(3, '0')}.pdf`
}

const lsmData = ref(null)
async function loadLsmData() {
  if (lsmData.value) return
  try {
    const res = await fetch('/lsm_mapping.json')
    lsmData.value = await res.json()
  } catch (e) {
    console.warn('LSM mapping load failed', e)
  }
}

function getLsmMessages(book, chapter) {
  if (!lsmData.value) return []
  const allBooks = [
    ...(lsmData.value.oldTestament || []),
    ...(lsmData.value.newTestament || []),
  ]
  const bookEntry = allBooks.find(b => b.order === book)
  if (!bookEntry) return []
  return bookEntry.chapters?.[String(chapter)]?.messages || []
}

const showLsmDropdown = ref(false)
const lsmRootRef = ref(null)

function toggleLsmDropdown() {
  showLsmDropdown.value = !showLsmDropdown.value
}

watch(showLsmDropdown, (open) => {
  if (!open) return
  const onPointerDown = (e) => {
    if (lsmRootRef.value && !lsmRootRef.value.contains(e.target)) {
      showLsmDropdown.value = false
    }
  }
  const timer = setTimeout(() => {
    document.addEventListener('mousedown', onPointerDown)
  }, 0)
  return () => {
    clearTimeout(timer)
    document.removeEventListener('mousedown', onPointerDown)
  }
})

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

const refKeyMap = { gb: 'ref_gb', big5: 'ref_big5', en: 'ref_en' }
const nameKeyMap = { gb: 'name_gb', big5: 'name_big5', en: 'name_en' }

// 中文章序数汉字转换
const chapterChinese = (n) => {
  const nums = ['一','二','三','四','五','六','七','八','九','十',
    '十一','十二','十三','十四','十五','十六','十七','十八','十九','二十',
    '二十一','二十二','二十三','二十四','二十五','二十六','二十七','二十八','二十九','三十',
    '三十一','三十二','三十三','三十四','三十五','三十六','三十七','三十八','三十九','四十',
    '四十一','四十二','四十三','四十四','四十五','四十六','四十七','四十八','四十九','五十']
  return nums[n - 1] || String(n)
}

const verseTitle = computed(() => {
  const lang = currentLang.value
  const nKey = nameKeyMap[lang] || 'name_gb'
  const rKey = refKeyMap[lang] || 'ref_gb'

  if (props.queryType === 'verse' && props.verse) {
    const v = props.verse
    const name = v[nKey] || v.name_gb || ''
    const ch = chapterChinese(v.chapter)
    const vs = v.verse
    if (lang === 'en') return `${name} ${v.chapter}:${vs}`
    return `${name}第${ch}章第${vs}节`
  }

  if ((props.queryType === 'range' || props.queryType === 'chapter') && props.verses?.length) {
    const first = props.verses[0]
    const last = props.verses[props.verses.length - 1]
    const name = first[nKey] || first.name_gb || ''
    const ch = chapterChinese(first.chapter)

    if (props.queryType === 'chapter') {
      if (lang === 'en') return `${name} Chapter ${first.chapter}`
      return `${name}第${ch}章`
    }
    // range
    if (lang === 'en') return `${name} ${first.chapter}:${first.verse}–${last.verse}`
    return `${name}第${ch}章第${first.verse}～${last.verse}节`
  }
  return ''
})

const labels = computed(() => {
  const l = currentLang.value
  if (l === 'big5') {
    return {
      crossrefs: '串珠',
      footnotes: '註解',
      ministry: '相關職事信息',
      generating: '生成中',
      biblehub: '原文對照',
      lsm: '相關生命讀經',
    }
  }
  if (l === 'en') {
    return {
      crossrefs: 'Cross References',
      footnotes: 'Footnotes',
      ministry: 'Related Ministry Messages',
      generating: 'Generating',
      biblehub: 'Interlinear',
      lsm: 'Related Life-Study',
    }
  }
  return {
    crossrefs: '串珠',
    footnotes: '注解',
    ministry: '相关职事信息',
    generating: '生成中',
    biblehub: '原文对照',
    lsm: '相关生命读经',
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

onMounted(() => {
  if (SHOW_BIBLE_EXTRA_LINKS) {
    loadLsmData()
  }
})
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

.chapter-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.biblehub-link {
  text-decoration: none;
  color: var(--color-link);
  transition: color 0.15s;
}
.biblehub-link:hover {
  color: var(--color-link-hover);
}
.lsm-btn {
  font-size: 15px;
  color: var(--color-link);
  cursor: pointer;
  user-select: none;
}
.lsm-btn:hover {
  color: var(--color-link-hover);
}
.lsm-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 100;
  background: var(--color-bg-elevated, #fff);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  min-width: 220px;
  max-width: 320px;
  padding: 4px 0;
  display: flex;
  flex-direction: column;
  color: var(--color-text);
}
.lsm-dropdown-item {
  padding: 7px 14px;
  font-size: 13px;
  color: var(--color-text);
  text-decoration: none;
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 6px;
  cursor: pointer;
}
.lsm-dropdown-item:hover,
.lsm-dropdown-item:visited {
  color: var(--color-text);
  background: var(--color-bg-hover, rgba(0, 0, 0, 0.04));
}
.lsm-ref {
  color: var(--color-text-secondary);
  font-size: 11px;
  margin-left: 4px;
  flex-basis: 100%;
}
.lsm-empty {
  color: var(--color-text-secondary);
  font-style: italic;
  cursor: default;
}

.verse-title-row {
  margin-bottom: 10px;
}
.verse-title-text {
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text-primary);
}
</style>

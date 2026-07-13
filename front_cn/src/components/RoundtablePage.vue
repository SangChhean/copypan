<template>
  <div class="roundtable-root">
    <div class="cn-page-head">
      <button type="button" class="cn-back" @click="goHome">‹‹ 返回</button>
      <span class="cn-page-title">小排生命读经材料制作</span>
    </div>

    <div class="cn-content-wrap">
      <div class="cn-content-card">
        <section class="section">
          <div class="roundtable-row">
            <div class="roundtable-row-label">周数</div>
            <div class="roundtable-row-content">
              <a-input
                v-model:value="weekNumber"
                addon-before="第"
                addon-after="周"
                :disabled="!useWeekNumber"
                placeholder="三 / 十五"
                style="width: 160px"
              />
              <a-checkbox
                v-model:checked="useWeekNumber"
                class="roundtable-emphasis-text"
                style="margin-left: 16px"
              >标注周数</a-checkbox>
            </div>
          </div>

          <div class="roundtable-row">
            <div class="roundtable-row-label">生命读经</div>
            <div class="roundtable-row-content">
              <a-select
                v-model:value="selectedBook"
                placeholder="请选择生命读经书卷"
                style="width: 260px"
                :options="bookOptions"
                :disabled="!lsmMapping"
                show-search
                :filter-option="filterBookOption"
                @change="onBookChange"
              />
              <a-select
                v-model:value="startIssue"
                placeholder="起始篇"
                style="width: 200px; margin-left: 16px"
                :options="startIssueOptions"
                :disabled="!lsmMapping || !selectedBook"
                show-search
                :filter-option="filterIssueOption"
                @change="onStartIssueChange"
              />
            </div>
          </div>

          <div class="roundtable-row">
            <div class="roundtable-row-label">篇数</div>
            <div class="roundtable-row-content roundtable-row-content--wrap">
              <a-select
                v-model:value="issueCount"
                placeholder="篇数"
                style="width: 140px"
                :options="countOptions"
                :disabled="!lsmMapping || !startIssue"
              />
              <div v-if="willGenerateText" class="roundtable-hint">{{ willGenerateText }}</div>
            </div>
          </div>

          <div class="roundtable-row">
            <div class="roundtable-row-label">生成版本</div>
            <div class="roundtable-row-content">
              <a-checkbox-group
                v-model:value="selectedVersions"
                class="roundtable-emphasis-text"
              >
                <a-checkbox value="truth">真理加强版</a-checkbox>
                <a-checkbox value="gospel">福音加强版</a-checkbox>
                <a-checkbox value="life">生命加强版</a-checkbox>
                <a-checkbox value="elderly">年长放大版</a-checkbox>
              </a-checkbox-group>
            </div>
          </div>

          <a-button
            type="primary"
            class="roundtable-gen-btn"
            :loading="generating"
            :disabled="!canGenerate"
            @click="onGenerate"
          >
            生成
          </a-button>

          <div v-if="generating" class="roundtable-progress">
            <a-spin />
            <span>{{ progressText }}</span>
          </div>

          <div v-if="result" class="roundtable-result">
            <a-tabs v-model:activeKey="activeTab">
              <a-tab-pane
                v-for="(v, key) in result.versions"
                :key="key"
                :tab="`${v.label}（${v.word_count}字）`"
              >
                <div
                  class="roundtable-preview-html cn-result"
                  v-html="v.preview_html"
                ></div>
              </a-tab-pane>
            </a-tabs>
            <a-button type="primary" class="roundtable-confirm-btn" @click="onConfirm">
              确认，生成最终文档
            </a-button>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import http from '@/utils/http.js'

const router = useRouter()

const lsmMapping = ref(null)
const useWeekNumber = ref(true)
const weekNumber = ref('')
const selectedBook = ref(null)
const startIssue = ref(null)
const issueCount = ref(1)
const selectedVersions = ref(['truth', 'gospel', 'life', 'elderly'])
const generating = ref(false)
const progressText = ref('')
const result = ref(null)
const activeTab = ref('truth')

const allBooks = computed(() => {
  if (!lsmMapping.value) return []
  return [
    ...(lsmMapping.value.oldTestament || []),
    ...(lsmMapping.value.newTestament || []),
  ]
})

const bookOptions = computed(() =>
  allBooks.value.map((b) => ({
    value: b.order,
    label: `${b.order}. ${b.name}`,
  })),
)

/** 当前卷去重后的篇号集合与选项 */
const bookMessageIndexSet = computed(() => {
  if (!selectedBook.value || !lsmMapping.value) return new Set()
  const book = allBooks.value.find((b) => b.order === selectedBook.value)
  if (!book?.chapters) return new Set()
  const set = new Set()
  for (const ch of Object.values(book.chapters)) {
    for (const m of ch.messages || []) {
      set.add(m.index)
    }
  }
  return set
})

const startIssueOptions = computed(() => {
  if (!selectedBook.value || !lsmMapping.value) return []
  const book = allBooks.value.find((b) => b.order === selectedBook.value)
  if (!book?.chapters) return []
  const byIndex = new Map()
  for (const ch of Object.values(book.chapters)) {
    for (const m of ch.messages || []) {
      if (!byIndex.has(m.index)) byIndex.set(m.index, m)
    }
  }
  return [...byIndex.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([index, m]) => ({
      value: index,
      label: m.label,
    }))
})

/** 篇数选项：仅当 start..start+n-1 全部存在于本卷时才可选，从结构上杜绝跳选 */
const countOptions = computed(() => {
  const start = startIssue.value
  const set = bookMessageIndexSet.value
  if (start == null) {
    return [
      { value: 1, label: '1 篇', disabled: true },
      { value: 2, label: '2 篇', disabled: true },
      { value: 3, label: '3 篇', disabled: true },
    ]
  }
  const can2 = set.has(start + 1)
  const can3 = can2 && set.has(start + 2)
  return [
    { value: 1, label: '1 篇' },
    { value: 2, label: '2 篇', disabled: !can2 },
    { value: 3, label: '3 篇', disabled: !can3 },
  ]
})

const selectedIssues = computed(() => {
  const start = startIssue.value
  const count = issueCount.value
  if (start == null || !count) return []
  return Array.from({ length: count }, (_, i) => start + i)
})

const willGenerateText = computed(() => {
  if (!selectedIssues.value.length) return ''
  const issuesPart = `第 ${selectedIssues.value.join('、')} 篇（连续）`
  if (useWeekNumber.value && weekNumber.value.trim()) {
    return `将生成：第${weekNumber.value.trim()}周 · ${issuesPart}`
  }
  return `将生成：${issuesPart}`
})

const canGenerate = computed(
  () =>
    selectedBook.value &&
    selectedIssues.value.length >= 1 &&
    selectedIssues.value.length <= 3 &&
    selectedIssues.value.every((n) => bookMessageIndexSet.value.has(n)) &&
    selectedVersions.value.length >= 1 &&
    (!useWeekNumber.value || weekNumber.value.trim().length > 0),
)

watch([startIssue, countOptions], () => {
  const opts = countOptions.value
  const current = opts.find((o) => o.value === issueCount.value)
  if (!current || current.disabled) {
    issueCount.value = 1
  }
})

function filterBookOption(input, option) {
  return String(option.label || '')
    .toLowerCase()
    .includes(String(input || '').toLowerCase())
}

function filterIssueOption(input, option) {
  return String(option.label || '')
    .toLowerCase()
    .includes(String(input || '').toLowerCase())
}

function onBookChange() {
  startIssue.value = null
  issueCount.value = 1
  result.value = null
}

function onStartIssueChange() {
  issueCount.value = 1
  result.value = null
}

async function loadLsmMapping() {
  try {
    const res = await fetch('/lsm_mapping.json')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    lsmMapping.value = await res.json()
  } catch (e) {
    message.error('生命读经篇目映射加载失败')
    console.error(e)
  }
}

async function onGenerate() {
  const issues = selectedIssues.value
  if (!issues.length) {
    message.warning('请选择起始篇与篇数')
    return
  }
  for (let i = 1; i < issues.length; i++) {
    if (issues[i] !== issues[i - 1] + 1) {
      message.error('篇号必须连续')
      return
    }
  }
  if (useWeekNumber.value && !weekNumber.value.trim()) {
    message.warning('请填写周数，或取消勾选「标注周数」')
    return
  }
  if (!selectedVersions.value.length) {
    message.warning('请至少选择一个版本')
    return
  }
  generating.value = true
  result.value = null
  progressText.value = '正在读取原文…'
  try {
    progressText.value = '正在生成，预计需要 3–8 分钟，请耐心等待…'
    const body = {
      book: selectedBook.value,
      issues,
      versions: selectedVersions.value,
    }
    if (useWeekNumber.value) {
      body.week_number = weekNumber.value.trim()
    }
    const res = await http.post('/api/cn/roundtable/generate', body, {
      timeout: 600000,
    })
    result.value = res.data
    activeTab.value = selectedVersions.value[0]
    message.success('生成完成，请预览确认')
  } catch (e) {
    const status = e?.response?.status
    const detail = e.response?.data?.detail
    const detailText =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((d) => d.msg || JSON.stringify(d)).join('；')
          : '生成失败，请稍后重试'
    if (status === 429) {
      message.warning(detailText || '今日次数已达上限')
    } else if (status === 422 || status === 400) {
      message.error(detailText)
    } else {
      message.error(detailText)
    }
  } finally {
    generating.value = false
  }
}

function onConfirm() {
  message.info('排版下载功能即将上线，敬请期待')
}

function goHome() {
  router.push('/')
}

onMounted(() => {
  loadLsmMapping()
})
</script>

<style scoped>
.roundtable-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 20px;
}

.roundtable-row-label {
  width: 120px;
  flex-shrink: 0;
  padding-top: 5px;
  font-size: 15px;
  font-weight: 600;
  color: #1b6ca8;
}

.roundtable-row-content {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.roundtable-row-content--wrap {
  align-items: flex-start;
}

.roundtable-hint {
  width: 100%;
  margin-top: 4px;
  font-size: 13px;
  color: var(--cn-text-secondary, #4a6a84);
}

.roundtable-emphasis-text {
  font-size: 15px;
}

.roundtable-emphasis-text :deep(.ant-checkbox-wrapper),
.roundtable-emphasis-text :deep(.ant-checkbox + span) {
  font-size: 15px;
}

.roundtable-row-content :deep(.ant-checkbox-group) {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
}

.roundtable-gen-btn {
  display: block !important;
  margin: 4px auto 0 !important;
  padding: 14px 56px !important;
  height: auto !important;
  font-size: 16px !important;
  font-weight: 700 !important;
  letter-spacing: 0.04em;
  border-radius: 10px !important;
}

.roundtable-progress {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 20px;
  color: var(--cn-text-secondary);
}

.roundtable-result {
  margin-top: 20px;
}

.roundtable-preview-html {
  word-break: break-word;
  font-size: 14px;
  line-height: 1.7;
  max-height: 560px;
  overflow: auto;
  padding: 4px 0;
}

.roundtable-preview-html :deep(p) {
  white-space: pre-wrap;
}

.roundtable-confirm-btn {
  display: block !important;
  margin: 16px auto 0 !important;
}
</style>

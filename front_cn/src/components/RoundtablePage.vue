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
                :disabled="!bookList.length"
                show-search
                :filter-option="filterBookOption"
                @change="onBookChange"
              />
              <a-select
                v-model:value="startIssue"
                placeholder="起始篇"
                style="width: 200px; margin-left: 16px"
                :options="startIssueOptions"
                :disabled="!selectedBook || bookIssuesLoading || !bookIssues.length"
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
                :disabled="!startIssue"
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
                :disabled="generating"
              >
                <a-checkbox value="truth" :disabled="generating">真理加强版</a-checkbox>
                <a-checkbox value="gospel" :disabled="generating">福音加强版</a-checkbox>
                <a-checkbox value="life" :disabled="generating">生命加强版</a-checkbox>
                <a-checkbox value="elderly" :disabled="generating">年长放大版</a-checkbox>
              </a-checkbox-group>
            </div>
          </div>

          <a-button
            type="primary"
            class="roundtable-gen-btn"
            :loading="generating"
            :disabled="!canGenerate || generating"
            @click="onGenerate"
          >
            生成
          </a-button>

          <div
            v-if="generating || generatingVersions.length"
            class="roundtable-versions-grid"
          >
            <div
              v-for="v in generatingVersions"
              :key="v"
              class="roundtable-version-card"
            >
              <div class="roundtable-version-title">{{ VERSION_LABELS[v] }}</div>
              <template v-if="versionResults[v]">
                <a-tag color="success">
                  已完成
                </a-tag>
                <a-progress :percent="100" size="small" :show-info="false" />
              </template>
              <template v-else-if="versionErrors[v]">
                <a-tag color="error">生成失败</a-tag>
                <div class="roundtable-version-error">{{ versionErrors[v] }}</div>
              </template>
              <template v-else>
                <a-progress
                  :percent="versionProgressPercent(v)"
                  :show-info="false"
                  size="small"
                />
                <span class="roundtable-version-stage">
                  {{ versionProgress[v]?.stage || '等待中' }}
                  {{ versionProgressPercent(v) }}%
                </span>
              </template>
            </div>
          </div>

          <div v-if="hasAnyVersionResult" class="roundtable-result">
            <a-tabs v-model:activeKey="activeTab">
              <a-tab-pane
                v-for="(v, key) in versionResults"
                :key="key"
                :tab="v.label"
              >
                <div
                  class="roundtable-preview-html cn-result"
                  v-html="v.preview_html"
                ></div>
              </a-tab-pane>
            </a-tabs>
            <a-button
              type="primary"
              class="roundtable-confirm-btn"
              :loading="currentFinalizeStatus === 'running'"
              :disabled="!canFinalizeCurrent"
              @click="onFinalizeOne"
            >
              生成Word文档
            </a-button>
            <div
              v-if="currentFinalFile"
              class="roundtable-download-list"
            >
              <div class="roundtable-download-item">
                <span>{{ currentFinalFile.label }}</span>
                <a-button
                  type="primary"
                  size="small"
                  @click="downloadFile(currentFinalFile)"
                >
                  下载 Word
                </a-button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import http from '@/utils/http.js'

const router = useRouter()

const VERSION_LABELS = {
  truth: '真理加强版',
  gospel: '福音加强版',
  life: '生命加强版',
  elderly: '年长放大版',
}

const bookList = ref([])
const bookIssues = ref([])
const bookIssuesLoading = ref(false)
const useWeekNumber = ref(true)
const weekNumber = ref('')
const selectedBook = ref(null)
const startIssue = ref(null)
const issueCount = ref(1)
const selectedVersions = ref(['truth', 'gospel', 'life', 'elderly'])
/** 点击生成那一刻锁定的版本列表，供进度卡片使用，避免生成中勾选变化影响展示 */
const generatingVersions = ref([])
const generating = ref(false)
const unifiedFields = ref(null)
const versionProgress = ref({})
const versionResults = ref({})
const versionErrors = ref({})
const activeTab = ref('')
const currentTaskId = ref('')
const finalizeStatus = ref({})
const finalizeErrors = ref({})
const finalFiles = ref({})
let pollTimer = null

/** 预览接口结果：实际会用到的篇 */
const selectionPreview = ref(null)
const selectionPreviewError = ref('')
const selectionPreviewLoading = ref(false)
let previewTimer = null

const bookOptions = computed(() =>
  bookList.value.map((b) => ({
    value: b.book_id,
    label: b.name,
  })),
)

/** 从完整标题中取出「第X篇」，与旧下拉简短样式一致 */
function shortIssueLabel(title) {
  const m = String(title || '').match(/^第[一二三四五六七八九十百零〇两\d]+篇/)
  return m ? m[0] : String(title || '')
}

const startIssueOptions = computed(() =>
  bookIssues.value.map((item) => ({
    value: item.issue,
    label: shortIssueLabel(item.title),
  })),
)

/** 篇数：跨卷可续接，不再按本卷剩余篇数禁用 2/3 篇 */
const countOptions = [
  { value: 1, label: '1 篇' },
  { value: 2, label: '2 篇' },
  { value: 3, label: '3 篇' },
]

function shortBookName(name) {
  return String(name || '').replace(/生命读经$/, '')
}

function formatSelectionRange(items) {
  if (!items?.length) return ''
  const groups = []
  for (const item of items) {
    const name = shortBookName(item.book_name)
    if (groups.length && groups[groups.length - 1].book === item.book) {
      groups[groups.length - 1].issues.push(item.issue)
    } else {
      groups.push({ book: item.book, name, issues: [item.issue] })
    }
  }
  return groups
    .map((g) => {
      if (g.issues.length === 1) return `${g.name}第${g.issues[0]}篇`
      return `${g.name}第${g.issues[0]}~${g.issues[g.issues.length - 1]}篇`
    })
    .join(' → ')
}

const willGenerateText = computed(() => {
  if (selectionPreviewError.value) return selectionPreviewError.value
  if (!selectionPreview.value?.selection?.length) return ''
  const range = formatSelectionRange(selectionPreview.value.selection)
  const cross = selectionPreview.value.crosses_book ? '（跨卷）' : ''
  if (useWeekNumber.value && weekNumber.value.trim()) {
    return `将生成：第${weekNumber.value.trim()}周 · ${range}${cross}`
  }
  return `将生成：${range}${cross}`
})

const hasAnyVersionResult = computed(
  () => Object.keys(versionResults.value).length > 0,
)

const hasAnyVersionOutcome = computed(
  () =>
    hasAnyVersionResult.value || Object.keys(versionErrors.value).length > 0,
)

const currentFinalizeStatus = computed(
  () => finalizeStatus.value[activeTab.value] || 'idle',
)

const currentFinalFile = computed(
  () => finalFiles.value[activeTab.value] || null,
)

const canFinalizeCurrent = computed(
  () =>
    !!currentTaskId.value &&
    !!activeTab.value &&
    !!unifiedFields.value &&
    !!versionResults.value[activeTab.value]?.raw_data &&
    currentFinalizeStatus.value !== 'running',
)

const canGenerate = computed(
  () =>
    selectedBook.value &&
    startIssue.value != null &&
    issueCount.value >= 1 &&
    issueCount.value <= 3 &&
    !!selectionPreview.value?.selection?.length &&
    !selectionPreviewError.value &&
    !selectionPreviewLoading.value &&
    selectedVersions.value.length >= 1 &&
    (!useWeekNumber.value || weekNumber.value.trim().length > 0),
)

function versionProgressPercent(key) {
  if (versionResults.value[key]) return 100
  const attempt = versionProgress.value[key]?.attempt || 0
  return Math.min(attempt * 12, 90)
}

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

async function loadBookIssues(bookId) {
  bookIssues.value = []
  if (!bookId) return
  bookIssuesLoading.value = true
  try {
    // 须走鉴权 http，裸 fetch 不会带 JWT
    const res = await http.get(`/api/cn/roundtable/book_issues/${bookId}`)
    bookIssues.value = res.data.issues || []
  } catch (e) {
    const status = e.response?.status
    const detail = e.response?.data?.detail
    message.error(
      `该卷篇目加载失败（状态码 ${status || '未知'}：${detail || e.message}）`,
    )
    console.error('loadBookIssues error:', status, detail, e)
    bookIssues.value = []
  } finally {
    bookIssuesLoading.value = false
  }
}

async function onBookChange() {
  startIssue.value = null
  issueCount.value = 1
  unifiedFields.value = null
  versionResults.value = {}
  versionErrors.value = {}
  versionProgress.value = {}
  selectionPreview.value = null
  selectionPreviewError.value = ''
  await loadBookIssues(selectedBook.value)
}

function onStartIssueChange() {
  issueCount.value = 1
  unifiedFields.value = null
  versionResults.value = {}
  versionErrors.value = {}
  versionProgress.value = {}
}

async function loadBookList() {
  try {
    const res = await http.get('/api/cn/roundtable/books')
    bookList.value = res.data.books || []
  } catch (e) {
    const status = e.response?.status
    const detail = e.response?.data?.detail
    message.error(
      `书卷列表加载失败（状态码 ${status || '未知'}：${detail || e.message}）`,
    )
    console.error('loadBookList error:', status, detail, e)
  }
}

async function fetchSelectionPreview() {
  if (!selectedBook.value || startIssue.value == null || !issueCount.value) {
    selectionPreview.value = null
    selectionPreviewError.value = ''
    return
  }
  selectionPreviewLoading.value = true
  try {
    const res = await http.post('/api/cn/roundtable/preview_selection', {
      book: selectedBook.value,
      start_issue: startIssue.value,
      count: issueCount.value,
    })
    selectionPreview.value = res.data
    selectionPreviewError.value = ''
  } catch (e) {
    selectionPreview.value = null
    const detail = e.response?.data?.detail
    const detailText =
      typeof detail === 'string'
        ? detail
        : '已经是全集最后一卷，篇数不足，请减少篇数'
    selectionPreviewError.value = detailText
  } finally {
    selectionPreviewLoading.value = false
  }
}

watch([selectedBook, startIssue, issueCount], () => {
  if (previewTimer) clearTimeout(previewTimer)
  previewTimer = setTimeout(() => {
    fetchSelectionPreview()
  }, 300)
})

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function pollTask(taskId = currentTaskId.value) {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const res = await http.get(`/api/cn/roundtable/task/${taskId}`)
      const task = res.data

      if (task.unified_fields) {
        unifiedFields.value = task.unified_fields
      }

      let allSettled = true
      let anyFinalizeRunning = false
      const nextProgress = { ...versionProgress.value }
      const nextResults = { ...versionResults.value }
      const nextErrors = { ...versionErrors.value }
      const nextFinalizeStatus = { ...finalizeStatus.value }
      const nextFinalizeErrors = { ...finalizeErrors.value }
      const nextFinalFiles = { ...finalFiles.value }

      for (const [key, v] of Object.entries(task.versions || {})) {
        if (v.status === 'done' && v.result) {
          nextResults[key] = v.result
          delete nextProgress[key]
          delete nextErrors[key]
          if (!activeTab.value) {
            activeTab.value = key
          }
        } else if (v.status === 'error') {
          nextErrors[key] = v.error || '生成失败，请重试'
          delete nextProgress[key]
        } else {
          nextProgress[key] = {
            stage: v.stage || '等待中',
            attempt: v.attempt || 0,
          }
          allSettled = false
        }

        const finalize = v.finalize || { status: 'idle' }
        nextFinalizeStatus[key] = finalize.status || 'idle'
        if (finalize.status === 'running') {
          anyFinalizeRunning = true
          delete nextFinalizeErrors[key]
          delete nextFinalFiles[key]
        } else if (finalize.status === 'done' && finalize.file) {
          const prev = nextFinalFiles[key]
          if (!prev || prev.token !== finalize.file.token) {
            message.success(`${v.result?.label || VERSION_LABELS[key]} Word文档已生成`)
          }
          nextFinalFiles[key] = finalize.file
          delete nextFinalizeErrors[key]
        } else if (finalize.status === 'error') {
          const error = finalize.error || 'Word文档生成失败，请重试'
          if (nextFinalizeErrors[key] !== error) {
            message.error(error)
          }
          nextFinalizeErrors[key] = error
          delete nextFinalFiles[key]
        }
      }

      versionProgress.value = nextProgress
      versionResults.value = nextResults
      versionErrors.value = nextErrors
      finalizeStatus.value = nextFinalizeStatus
      finalizeErrors.value = nextFinalizeErrors
      finalFiles.value = nextFinalFiles

      if (allSettled && generating.value) {
        generating.value = false
        const okCount = Object.keys(nextResults).length
        const errCount = Object.keys(nextErrors).length
        if (okCount && !errCount) {
          message.success('全部版本生成完成，请预览确认')
        } else if (okCount && errCount) {
          message.warning('部分版本生成完成，部分失败')
        } else if (errCount) {
          message.error('生成失败')
        }
      }
      if (allSettled && !anyFinalizeRunning) {
        stopPolling()
      }
    } catch (e) {
      stopPolling()
      generating.value = false
      if (e.response?.status === 404) {
        message.error('任务已丢失（可能是服务重启），请重新点击生成')
      } else {
        message.error('查询进度失败，请重试')
      }
    }
  }, 3000)
}

async function cleanupCurrentTask() {
  const taskId = currentTaskId.value
  if (!taskId) return
  try {
    await http.post(`/api/cn/roundtable/cleanup_task/${taskId}`)
  } catch {
    // 离开页面时的清理失败不影响返回
  }
}

async function onGenerate() {
  if (!selectedBook.value || startIssue.value == null) {
    message.warning('请选择起始篇与篇数')
    return
  }
  if (selectionPreviewError.value) {
    message.error(selectionPreviewError.value)
    return
  }
  if (useWeekNumber.value && !weekNumber.value.trim()) {
    message.warning('请填写周数，或取消勾选「标注周数」')
    return
  }
  if (!selectedVersions.value.length) {
    message.warning('请至少选择一个版本')
    return
  }

  stopPolling()
  await cleanupCurrentTask()
  generating.value = true
  generatingVersions.value = [...selectedVersions.value]
  unifiedFields.value = null
  versionResults.value = {}
  versionErrors.value = {}
  versionProgress.value = Object.fromEntries(
    generatingVersions.value.map((k) => [k, { stage: '等待中', attempt: 0 }]),
  )
  activeTab.value = ''
  currentTaskId.value = ''
  finalizeStatus.value = Object.fromEntries(
    generatingVersions.value.map((k) => [k, 'idle']),
  )
  finalizeErrors.value = {}
  finalFiles.value = {}

  try {
    const body = {
      book: selectedBook.value,
      start_issue: startIssue.value,
      count: issueCount.value,
      versions: generatingVersions.value,
    }
    if (useWeekNumber.value) {
      body.week_number = weekNumber.value.trim()
    }
    const res = await http.post('/api/cn/roundtable/generate', body, {
      timeout: 60000,
    })
    currentTaskId.value = res.data.task_id
    if (!currentTaskId.value) {
      throw new Error('未返回 task_id')
    }
    pollTask(currentTaskId.value)
  } catch (e) {
    generating.value = false
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
    } else {
      message.error(detailText)
    }
  }
}

async function onFinalizeOne() {
  const versionKey = activeTab.value
  if (!canFinalizeCurrent.value || !versionKey) {
    message.warning('当前版本尚未生成完成')
    return
  }

  finalizeStatus.value = {
    ...finalizeStatus.value,
    [versionKey]: 'running',
  }
  const nextFiles = { ...finalFiles.value }
  delete nextFiles[versionKey]
  finalFiles.value = nextFiles

  try {
    await http.post(
      '/api/cn/roundtable/finalize_one',
      {
        task_id: currentTaskId.value,
        version_key: versionKey,
      },
      { timeout: 60000 },
    )
    pollTask(currentTaskId.value)
  } catch (e) {
    finalizeStatus.value = {
      ...finalizeStatus.value,
      [versionKey]: 'idle',
    }
    message.error(e.response?.data?.detail || 'Word文档生成失败，请稍后重试')
  }
}

async function downloadFile(file) {
  // 带 Authorization 的 blob 下载（window.open 不会带 JWT，会被鉴权拦住）
  try {
    const res = await http.get(`/api/cn/roundtable/download/${file.token}`, {
      responseType: 'blob',
      timeout: 120000,
    })
    const blob = new Blob([res.data])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = file.filename || 'download'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    let detail = '下载失败，请重新生成'
    const data = e.response?.data
    if (data instanceof Blob) {
      try {
        const parsed = JSON.parse(await data.text())
        if (typeof parsed?.detail === 'string') detail = parsed.detail
      } catch {
        /* ignore */
      }
    } else if (typeof data?.detail === 'string') {
      detail = data.detail
    }
    message.error(detail)
  }
}

async function goHome() {
  stopPolling()
  await cleanupCurrentTask()
  router.push('/')
}

onMounted(() => {
  loadBookList()
})

onUnmounted(() => {
  stopPolling()
  if (previewTimer) clearTimeout(previewTimer)
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

.roundtable-download-list {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.roundtable-download-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  background: #f5f8fb;
  border-radius: 8px;
}

.roundtable-versions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  margin-top: 20px;
}

.roundtable-version-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  background: #f5f8fb;
  border-radius: 8px;
}

.roundtable-version-title {
  font-size: 14px;
  font-weight: 600;
  color: #1b6ca8;
}

.roundtable-version-stage {
  font-size: 12px;
  color: var(--cn-text-secondary, #4a6a84);
}

.roundtable-version-error {
  font-size: 12px;
  color: #cf1322;
  word-break: break-word;
}
</style>

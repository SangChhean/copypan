<template>
  <div class="roundtable-root">
    <div class="cn-page-head">
      <button type="button" class="cn-back" @click="goToolbox">‹‹ 返回</button>
      <span class="cn-page-title">职事书报追求材料制作</span>
    </div>

    <div class="cn-content-wrap">
      <div class="cn-content-card">
        <section class="section">
          <div class="roundtable-row roundtable-row--week">
            <div class="roundtable-row-label">周数</div>
            <div class="roundtable-row-content">
              <a-input
                v-model:value="weekNumber"
                class="roundtable-week-input"
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
            <div class="roundtable-row-label">纲要题目</div>
            <div class="roundtable-row-content">
              <a-input
                v-model:value="outlineTitle"
                placeholder="请输入纲要标题"
                style="max-width: 480px"
              />
            </div>
          </div>

          <div class="roundtable-row">
            <div class="roundtable-row-label">书名</div>
            <div class="roundtable-row-content">
              <a-input
                v-model:value="bookName"
                placeholder="如：灵与灵的事奉"
                style="max-width: 320px"
              />
            </div>
          </div>

          <div class="roundtable-row">
            <div class="roundtable-row-label">篇章信息</div>
            <div class="roundtable-row-content">
              <a-input
                v-model:value="chapterInfo"
                placeholder="第一篇 / 第一~二篇 / 第三章"
                style="max-width: 320px"
              />
            </div>
          </div>

          <div class="roundtable-row">
            <div class="roundtable-row-label">职事信息</div>
            <div class="roundtable-row-content roundtable-row-content--wrap">
              <a-textarea
                v-model:value="ministryText"
                :rows="14"
                placeholder="请粘贴职事信息原文（1500～30000字）"
                :maxlength="TEXT_MAX_LEN"
                show-count
                style="width: 100%; max-width: 720px"
              />
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

          <div v-if="generating || hasResult || hasError" class="roundtable-version-card ministry-progress-card">
            <div class="roundtable-version-head">
              <div class="roundtable-version-title">职事书报追求纲要</div>
              <div
                class="roundtable-version-cost"
                :class="{ 'roundtable-version-cost--done': showCost }"
              >
                <span class="roundtable-version-cost-icon">💰</span>
                <span v-if="showCost" class="roundtable-version-cost-value">
                  ${{ formatCostUsd(versionCostUsd) }}
                </span>
              </div>
            </div>
            <template v-if="hasResult">
              <a-tag color="success">已完成</a-tag>
              <a-progress :percent="100" size="small" :show-info="false" />
            </template>
            <template v-else-if="hasError">
              <a-tag color="error">生成失败</a-tag>
              <div class="roundtable-version-error">{{ errorMessage }}</div>
            </template>
            <template v-else>
              <a-progress :percent="progressPercent" :show-info="false" size="small" />
              <span class="roundtable-version-stage">
                {{ progressStage }} {{ progressPercent }}%
              </span>
            </template>
          </div>

          <div v-if="showCostTotal" class="roundtable-cost-total">
            <span class="roundtable-cost-total-label">本次总计</span>
            <span class="roundtable-cost-total-icon">💰</span>
            <span class="roundtable-cost-total-value">${{ formatCostUsd(totalCostUsd) }}</span>
          </div>

          <div v-if="hasResult" class="roundtable-result">
            <div
              class="roundtable-preview-html cn-result"
              v-html="previewHtml"
            ></div>
            <a-button
              type="primary"
              class="roundtable-confirm-btn"
              :loading="finalizeStatus === 'running'"
              :disabled="!canFinalize"
              @click="onFinalize"
            >
              生成Word文档
            </a-button>
            <div v-if="finalFile" class="roundtable-download-list">
              <div class="roundtable-download-item">
                <span>{{ finalFile.filename }}</span>
                <a-button type="primary" size="small" @click="downloadFile">
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
import { computed, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import http from '@/utils/http.js'

const router = useRouter()

const TEXT_MIN_LEN = 1500
const TEXT_MAX_LEN = 30000
const VERSION_KEY = 'truth'

const useWeekNumber = ref(true)
const weekNumber = ref('')
const outlineTitle = ref('')
const bookName = ref('')
const chapterInfo = ref('')
const ministryText = ref('')

const generating = ref(false)
const currentTaskId = ref('')
const progressStage = ref('等待中')
const progressAttempt = ref(0)
const previewHtml = ref('')
const errorMessage = ref('')
const step1CostUsd = ref(null)
const versionCostUsd = ref(null)
const finalizeStatus = ref('idle')
const finalFile = ref(null)

let pollTimer = null

const textLen = computed(() => ministryText.value.trim().length)

const canGenerate = computed(
  () =>
    outlineTitle.value.trim().length > 0 &&
    textLen.value >= TEXT_MIN_LEN &&
    textLen.value <= TEXT_MAX_LEN &&
    (!useWeekNumber.value || weekNumber.value.trim().length > 0),
)

const hasResult = computed(() => !!previewHtml.value)
const hasError = computed(() => !!errorMessage.value && !hasResult.value)

const progressPercent = computed(() => {
  if (hasResult.value) return 100
  return Math.min((progressAttempt.value || 0) * 12, 90)
})

const showCost = computed(
  () => hasResult.value && versionCostUsd.value != null,
)

const showCostTotal = computed(
  () => hasResult.value && (step1CostUsd.value != null || versionCostUsd.value != null),
)

const totalCostUsd = computed(() => {
  const step1 = Number(step1CostUsd.value) || 0
  const ver = Number(versionCostUsd.value) || 0
  return step1 + ver
})

const canFinalize = computed(
  () =>
    !!currentTaskId.value &&
    hasResult.value &&
    finalizeStatus.value !== 'running',
)

function formatCostUsd(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '0.00'
  return n.toFixed(2)
}

function goToolbox() {
  router.push('/toolbox')
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function cleanupCurrentTask() {
  const taskId = currentTaskId.value
  if (!taskId) return
  try {
    await http.post(`/api/cn/ministry/cleanup_task/${taskId}`)
  } catch {
    // 离开页面时的清理失败不影响返回
  }
}

function pollTask(taskId) {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const res = await http.get(`/api/cn/ministry/task/${taskId}`)
      const task = res.data
      const version = task.versions?.[VERSION_KEY]

      if (task.step1_cost_usd != null) {
        step1CostUsd.value = task.step1_cost_usd
      }
      if (version?.cost_usd != null) {
        versionCostUsd.value = version.cost_usd
      }

      if (version?.status === 'done' && version.result) {
        previewHtml.value = version.result.preview_html || ''
        errorMessage.value = ''
        generating.value = false
        progressStage.value = '已完成'
        progressAttempt.value = 8

        const finalize = version.finalize || { status: 'idle' }
        finalizeStatus.value = finalize.status || 'idle'
        if (finalize.status === 'done' && finalize.file) {
          finalFile.value = finalize.file
        } else if (finalize.status === 'error') {
          message.error(finalize.error || 'Word文档生成失败，请重试')
        }

        if (!pollTimer) return
        if (finalize.status !== 'running') {
          stopPolling()
        }
        if (!hasAnnouncedDone) {
          hasAnnouncedDone = true
          message.success('纲要生成完成，请预览确认')
        }
        return
      }

      if (version?.status === 'error') {
        errorMessage.value = version.error || '生成失败，请重试'
        previewHtml.value = ''
        generating.value = false
        stopPolling()
        message.error(errorMessage.value)
        return
      }

      progressStage.value = version?.stage || '等待中'
      progressAttempt.value = version?.attempt || 0

      const finalize = version?.finalize || {}
      finalizeStatus.value = finalize.status || 'idle'
      if (finalize.status === 'done' && finalize.file) {
        finalFile.value = finalize.file
        message.success('Word文档已生成')
        stopPolling()
      } else if (finalize.status === 'error') {
        message.error(finalize.error || 'Word文档生成失败，请重试')
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

let hasAnnouncedDone = false

async function onGenerate() {
  if (!outlineTitle.value.trim()) {
    message.warning('请填写纲要题目')
    return
  }
  if (textLen.value < TEXT_MIN_LEN) {
    message.warning(`职事信息至少需要 ${TEXT_MIN_LEN} 字`)
    return
  }
  if (textLen.value > TEXT_MAX_LEN) {
    message.warning(`职事信息不能超过 ${TEXT_MAX_LEN} 字`)
    return
  }
  if (useWeekNumber.value && !weekNumber.value.trim()) {
    message.warning('请填写周数，或取消勾选「标注周数」')
    return
  }

  stopPolling()
  await cleanupCurrentTask()
  generating.value = true
  hasAnnouncedDone = false
  previewHtml.value = ''
  errorMessage.value = ''
  step1CostUsd.value = null
  versionCostUsd.value = null
  finalizeStatus.value = 'idle'
  finalFile.value = null
  progressStage.value = '等待中'
  progressAttempt.value = 0
  currentTaskId.value = ''

  try {
    const body = {
      text: ministryText.value.trim(),
      outline_title: outlineTitle.value.trim(),
      book_name: bookName.value.trim(),
      chapter_info: chapterInfo.value.trim(),
    }
    if (useWeekNumber.value) {
      body.week_number = weekNumber.value.trim()
    }
    const res = await http.post('/api/cn/ministry/generate', body, {
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

async function onFinalize() {
  if (!canFinalize.value) {
    message.warning('请等待纲要生成完成')
    return
  }
  finalizeStatus.value = 'running'
  finalFile.value = null
  try {
    await http.post('/api/cn/ministry/finalize', {
      task_id: currentTaskId.value,
    })
    pollTask(currentTaskId.value)
  } catch (e) {
    finalizeStatus.value = 'idle'
    const detail = e.response?.data?.detail
    message.error(typeof detail === 'string' ? detail : 'Word文档生成失败，请重试')
  }
}

async function downloadFile() {
  if (!finalFile.value?.token) return
  try {
    const res = await http.get(`/api/cn/ministry/download/${finalFile.value.token}`, {
      responseType: 'blob',
    })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = finalFile.value.filename || '纲要.docx'
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    message.error('下载失败，请重新生成 Word 文档')
  }
}

onUnmounted(() => {
  stopPolling()
  cleanupCurrentTask()
})
</script>

<style lang="less" scoped>
.roundtable-row {
  display: flex;
  align-items: flex-start;
  margin-bottom: 20px;
  gap: 16px;
}

.roundtable-row-label {
  flex: 0 0 88px;
  padding-top: 6px;
  color: var(--cn-text-secondary);
  font-size: 14px;
}

.roundtable-row-content {
  flex: 1;
  min-width: 0;
}

.roundtable-row-content--wrap {
  flex-wrap: wrap;
}

.roundtable-emphasis-text {
  font-size: 14px;
}

.roundtable-emphasis-text :deep(.ant-checkbox-wrapper),
.roundtable-emphasis-text :deep(.ant-checkbox + span) {
  font-size: 14px;
}

.roundtable-gen-btn {
  margin-top: 8px;
  margin-bottom: 24px;
  min-width: 120px;
}

.ministry-progress-card {
  margin-bottom: 16px;
}

.roundtable-result {
  margin-top: 8px;
}

.roundtable-preview-html {
  max-height: 70vh;
  overflow: auto;
  padding: 16px;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  background: #fff;
  margin-bottom: 16px;
}

.roundtable-preview-html :deep(p) {
  margin: 0 0 0.35em 0;
}

.roundtable-confirm-btn {
  margin-bottom: 16px;
}

.roundtable-download-list {
  margin-top: 8px;
}

.roundtable-download-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  background: #f7fbff;
  border: 1px solid #cce4f5;
  border-radius: 8px;
}

.roundtable-version-card {
  padding: 16px;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  background: #fafafa;
}

.roundtable-version-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.roundtable-version-title {
  font-weight: 500;
  color: var(--cn-text-primary);
}

.roundtable-version-cost {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #999;
  font-size: 13px;
}

.roundtable-version-cost--done {
  color: #1b6ca8;
}

.roundtable-version-stage {
  display: inline-block;
  margin-top: 8px;
  font-size: 13px;
  color: var(--cn-text-secondary);
}

.roundtable-version-error {
  margin-top: 8px;
  color: #cf1322;
  font-size: 13px;
}

.roundtable-cost-total {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  padding: 10px 14px;
  background: #f0f7fc;
  border-radius: 8px;
  font-size: 14px;
}

.roundtable-cost-total-value {
  font-weight: 600;
  color: #1b6ca8;
}

.roundtable-row--week :deep(.roundtable-week-input .ant-input) {
  text-align: center;
}
</style>

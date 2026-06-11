<template>
  <div class="rough-wrap">
    <ToolsHeader title="毛胚纲目" />

    <!-- 配置加载失败提示 -->
    <a-alert
      v-if="configError"
      type="error"
      message="配置加载失败，请刷新页面"
      show-icon
      style="margin-bottom:8px"
    />

    <!-- 类型选择 -->
    <a-card size="small" class="input-card">
      <div class="check-row">
        <a-checkbox v-model:checked="checkPolish"   class="chk chk-polish"   :class="{ active: checkPolish }">润色版</a-checkbox>
        <a-checkbox v-model:checked="checkBeginner" class="chk chk-beginner" :class="{ active: checkBeginner }">初信版</a-checkbox>
        <a-checkbox v-model:checked="checkYouth"    class="chk chk-youth"    :class="{ active: checkYouth }">青少年版</a-checkbox>
        <a-checkbox v-model:checked="checkTruth"    class="chk chk-truth"    :class="{ active: checkTruth }">真理加强版</a-checkbox>
        <a-checkbox v-model:checked="checkSharing"  class="chk chk-sharing"  :class="{ active: checkSharing }">三分钟分享</a-checkbox>
      </div>
    </a-card>

    <!-- 前三行 -->
    <a-card size="small" class="input-card">
      <a-row :gutter="[12,12]">
        <a-col :span="8">
          <div class="param-label"><span class="lbl lbl-title">总题（必填）</span></div>
          <a-input v-model:value="line1" placeholder="第一行 · 总题" allow-clear />
        </a-col>
        <a-col :span="8">
          <div class="param-label"><span class="lbl lbl-title">系列题（必填）</span></div>
          <a-input v-model:value="line2" placeholder="第二行 · 系列题" allow-clear />
        </a-col>
        <a-col :span="8">
          <div class="param-label"><span class="lbl lbl-title">篇题（必填）</span></div>
          <a-input v-model:value="line3" placeholder="第三行 · 篇题" allow-clear />
        </a-col>
      </a-row>
    </a-card>

    <!-- 输入区 + 生成按钮 -->
    <a-card size="small" class="input-card">
      <a-row :gutter="[12,12]">
        <a-col :span="24">
          <div class="param-label"><span class="lbl lbl-outline">原始纲目内容</span></div>
          <a-textarea
            v-model:value="inputContent"
            :auto-size="{ minRows: 6, maxRows: 20 }"
            placeholder="粘贴原始纲目内容"
          />
        </a-col>
        <a-col :span="24">
          <a-button
            type="primary"
            class="gen-btn"
            :loading="isLoading"
            @click="generateAll"
          >
            生成毛胚纲目
          </a-button>
        </a-col>
      </a-row>
    </a-card>

    <!-- 结果区：有结果才显示 -->
    <div v-if="results.length > 0" style="margin-top:16px">

      <!-- 顶部计数 + 进度条 -->
      <div class="result-topbar">
        <span class="result-title">{{ allDone ? '毛胚纲目' : '生成中…' }}</span>
        <span class="result-counter">{{ doneCount }} / {{ totalCount }} 完成</span>
      </div>
      <div class="progress-wrap">
        <div class="progress-fill" :style="{ width: progressWidth + '%' }"></div>
      </div>

      <!-- 结果卡片 -->
      <a-row :gutter="[12,12]">
        <a-col v-for="(item, idx) in results" :key="idx" :span="24">
          <a-card size="small" class="result-card" :class="`card-type-${item.type}`">
            <template #title>{{ item.typeName }}</template>
            <template #extra>
              <span class="ai-model-name">{{ item.ai_model }}</span>
            </template>
            <div v-if="item.loading" class="loading-row">
              <a-spin size="small" /><span>生成中…</span>
            </div>
            <pre v-if="!item.loading && item.content" class="outline-text">{{ item.line1 && item.line2 && item.line3 ? item.line1 + '\n' + item.line2 + '\n' + item.line3 + '\n──────\n' + item.content : item.content }}</pre>
            <a-alert v-if="!item.loading && item.error" type="error" :message="item.error" show-icon />
            <template #actions>
              <span v-if="!item.loading && item.content" @click="copyResult(idx, item.line1 && item.line2 && item.line3 ? item.line1 + '\n' + item.line2 + '\n' + item.line3 + '\n──────\n' + item.content : item.content)" style="cursor:pointer">
                {{ copiedIndex === idx ? '已复制！' : '复制' }}
              </span>
            </template>
          </a-card>
        </a-col>
      </a-row>

      <!-- 完成栏 -->
      <div v-if="allDone" class="done-bar">
        ✓ 全部完成，共 {{ totalCount }} 份纲目
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import ToolsHeader from './ToolsHeader.vue'

const apiBase = ''

const TYPE_NAMES = {
  polish:   '润色版',
  beginner: '初信版',
  youth:    '青少年版',
  truth:    '真理加强版',
  sharing:  '三分钟分享',
}

// 前三行
const line1 = ref('')   // 总题
const line2 = ref('')   // 系列题
const line3 = ref('')   // 篇题

// 类型勾选
const checkPolish   = ref(false)
const checkBeginner = ref(false)
const checkYouth    = ref(false)
const checkTruth    = ref(false)
const checkSharing  = ref(false)

const selectedTypes = computed(() => {
  const result = []
  if (checkPolish.value)   result.push('polish')
  if (checkBeginner.value) result.push('beginner')
  if (checkYouth.value)    result.push('youth')
  if (checkTruth.value)    result.push('truth')
  if (checkSharing.value)  result.push('sharing')
  return result
})

// 输入
const inputContent = ref('')
const config       = ref({})
const configError  = ref(false)
const isLoading    = ref(false)

// 结果
const results    = ref([])
const doneCount  = ref(0)
const totalCount = ref(0)
const copiedIndex = ref(-1)

const progressWidth = computed(() =>
  totalCount.value > 0 ? (doneCount.value / totalCount.value * 100) : 0
)

const allDone = computed(() =>
  totalCount.value > 0 && doneCount.value === totalCount.value
)

onMounted(async () => {
  try {
    const res = await fetch(`${apiBase}/api/testb/rough_outline/config`)
    config.value = await res.json()
  } catch {
    configError.value = true
  }
})

function validate() {
  if (!line1.value.trim() || !line2.value.trim() || !line3.value.trim()) {
    alert('请填写总题、系列题和篇题'); return false
  }
  if (!inputContent.value.trim()) {
    alert('请填写原始纲目内容'); return false
  }
  if (selectedTypes.value.length === 0) {
    alert('请至少选择一种类型'); return false
  }
  return true
}

async function generateAll() {
  if (!validate()) return

  const fullContent = inputContent.value

  // 展开任务
  const tasks = []
  for (const type of selectedTypes.value) {
    const count = config.value[type] || 1
    for (let i = 0; i < count; i++) {
      tasks.push({ type, ai_index: i })
    }
  }

  // 初始化占位
  results.value = tasks.map(t => ({
    type:     t.type,
    typeName: TYPE_NAMES[t.type],
    ai_model: '',
    ai_index: t.ai_index,
    content:  '',
    error:    null,
    loading:  true,
    line1: line1.value,
    line2: line2.value,
    line3: line3.value,
  }))

  totalCount.value = tasks.length
  doneCount.value  = 0
  isLoading.value  = true

  await Promise.allSettled(
    tasks.map(async (task, idx) => {
      try {
        const res = await fetch(`${apiBase}/api/testb/rough_outline/generate`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            outline_type: task.type,
            content:      fullContent,
            ai_index:     task.ai_index,
            line1: line1.value,
            line2: line2.value,
            line3: line3.value,
          }),
        })
        const data = await res.json()
        results.value.splice(idx, 1, {
          ...results.value[idx],
          content:  data.content || '',
          ai_model: data.ai_model || '',
          error:    data.error || null,
          loading:  false,
        })
      } catch (e) {
        results.value.splice(idx, 1, {
          ...results.value[idx],
          error:   e.message || '请求失败',
          loading: false,
        })
      } finally {
        doneCount.value++
        if (doneCount.value === totalCount.value) {
          isLoading.value = false
        }
      }
    })
  )
}

function copyResult(idx, text) {
  navigator.clipboard.writeText(text).then(() => {
    copiedIndex.value = idx
    setTimeout(() => { copiedIndex.value = -1 }, 1500)
  }).catch(() => message.error('复制失败'))
}
</script>

<style scoped>
.rough-wrap { padding: 4px 0; }
.input-card { margin-bottom: 8px; }
.check-row  { display: flex; gap: 12px; flex-wrap: wrap; }
.param-label { font-size: 13px; color: #555; margin-bottom: 6px; }

.lbl {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid transparent;
  font-size: 13px;
}
.lbl-title   { background: #fff7e6; border-color: #ffd591; }
.lbl-outline { background: #f9f0ff; border-color: #d3adf7; }

.chk {
  padding: 5px 12px;
  border-radius: 6px;
  border: 1px solid transparent;
  transition: background 0.2s, border-color 0.2s;
}
.chk-polish   { background: #e6f4ff; border-color: #91caff; }
.chk-beginner { background: #f6ffed; border-color: #b7eb8f; }
.chk-youth    { background: #fff7e6; border-color: #ffd591; }
.chk-truth    { background: #f9f0ff; border-color: #d3adf7; }
.chk-sharing  { background: #fff1f0; border-color: #ffa39e; }

.chk-polish.active   { background: #bae0ff; border-color: #69b1ff; }
.chk-beginner.active { background: #d9f7be; border-color: #95de64; }
.chk-youth.active    { background: #ffe7ba; border-color: #ffc53d; }
.chk-truth.active    { background: #efdbff; border-color: #b37feb; }
.chk-sharing.active  { background: #ffccc7; border-color: #ff7875; }

.gen-btn { background: #722ed1; border-color: #722ed1; }
.gen-btn:hover { background: #9254de !important; border-color: #9254de !important; }

.result-topbar {
  display: flex; align-items: center; gap: 12px;
  margin-bottom: 12px;
}
.result-title   { font-size: 15px; font-weight: bold; color: #333; }
.result-counter { margin-left: auto; font-size: 13px; color: #888; }

.progress-wrap {
  height: 4px; background: #f0f0f0;
  border-radius: 2px; margin-bottom: 16px; overflow: hidden;
}
.progress-fill {
  height: 4px; background: #722ed1;
  border-radius: 2px; transition: width 0.4s ease;
}

.result-card { height: 100%; }
.card-type-polish   :deep(.ant-card-head) { background: #bae0ff; color: #0958d9; }
.card-type-beginner :deep(.ant-card-head) { background: #d9f7be; color: #237804; }
.card-type-youth    :deep(.ant-card-head) { background: #ffe7ba; color: #ad4e00; }
.card-type-truth    :deep(.ant-card-head) { background: #efdbff; color: #531dab; }
.card-type-sharing  :deep(.ant-card-head) { background: #ffccc7; color: #a8071a; }
.ai-model-name { font-size: 12px; color: #888; }

.outline-text {
  font-size: 13px; line-height: 1.8;
  white-space: pre-wrap; word-break: break-word;
  font-family: inherit; margin: 0;
}
.loading-row {
  display: flex; align-items: center; gap: 8px;
  color: #999; font-size: 13px; padding: 16px 0;
}
.done-bar {
  margin-top: 16px; padding: 10px 16px;
  background: #f6ffed; border-radius: 6px;
  color: #52c41a; font-size: 14px;
}
</style>

<template>
  <div class="outline-root">
    <div class="cn-page-head">
      <button type="button" class="cn-back" @click="goHome">‹‹ 返回</button>
      <span class="cn-page-title">纲目制作</span>
    </div>

    <div class="cn-content-wrap">
      <div class="cn-content-card">
        <section class="section">
        <a-form layout="vertical">
          <a-form-item label="纲目主题" required>
            <a-input
              v-model:value="topic"
              placeholder="请输入纲目主题"
              :maxlength="500"
              allow-clear
            />
          </a-form-item>

          <a-form-item label="纲目性质">
            <a-select v-model:value="outlineNature" :options="natureOptions" />
          </a-form-item>

          <a-form-item label="负担点">
            <div v-for="(pt, idx) in burdenPoints" :key="idx" class="burden-row">
              <span class="burden-num">{{ idx + 1 }}</span>
              <a-input
                v-model:value="burdenPoints[idx]"
                :placeholder="idx === 0 ? '请输入负担点，如：祷告是生命的呼吸' : '请输入负担点'"
                :maxlength="60"
                allow-clear
              />
              <span v-if="burdenPoints[idx].length > 60" class="char-warn">超出 60 字</span>
              <button
                v-if="burdenPoints.length > 1"
                type="button"
                class="remove-btn"
                @click="removeBurdenPoint(idx)"
              >×</button>
            </div>
            <a-button
              v-if="burdenPoints.length < 5"
              type="dashed"
              block
              class="add-btn"
              @click="addBurdenPoint"
            >+ 添加负担点</a-button>
          </a-form-item>
        </a-form>

        <a-button
          type="primary"
          class="outline-gen-btn"
          :loading="outlineLoading"
          :disabled="!canGenerateOutline"
          @click="onGenerateOutline"
        >生成纲目</a-button>

        <div v-if="outlineLoading" class="outline-loading">
          <a-spin />
          <span>纲目生成中，请稍候（约 1~3 分钟）…</span>
        </div>

        <div v-if="outlineAnswer" class="result-box">
          <div class="toolbar">
            <a-button size="small" class="toolbar-btn cn-tool-btn" @click="copyOutline">复制</a-button>
            <a-button size="small" class="toolbar-btn cn-tool-btn" :loading="tradLoading" @click="toTraditional">繁体</a-button>
            <a-button size="small" class="toolbar-btn cn-tool-btn" :loading="enLoading" @click="toEnglish">英文</a-button>
            <a-button size="small" class="toolbar-btn cn-tool-btn" :loading="docxLoading" @click="downloadDocx">DOCX 下载</a-button>
          </div>

          <a-tabs v-model:activeKey="resultTab">
            <a-tab-pane key="zh" tab="简体">
              <div v-if="topic.trim()" class="outline-topic-title">{{ topic.trim() }}</div>
              <pre class="outline-text cn-result">{{ outlineAnswer }}</pre>
            </a-tab-pane>
            <a-tab-pane key="tw" tab="繁体" :disabled="!traditionalOutline">
              <div v-if="topic.trim()" class="outline-topic-title">{{ topic.trim() }}</div>
              <pre class="outline-text cn-result">{{ traditionalOutline }}</pre>
            </a-tab-pane>
            <a-tab-pane key="en" tab="英文" :disabled="!englishOutline">
              <div v-if="topic.trim()" class="outline-topic-title">{{ topic.trim() }}</div>
              <pre class="outline-text cn-result">{{ englishOutline }}</pre>
            </a-tab-pane>
          </a-tabs>

          <div v-if="outlineMeta.cached" class="meta-tag">已命中缓存</div>
        </div>
      </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import http from '@/utils/http.js'
import { getToken } from '@/utils/auth.js'
import { toastError, toastSuccess, toastWarning } from '@/utils/Dialog.js'

const router = useRouter()

const topic = ref('')
const outlineNature = ref('一般性')
const burdenPoints = ref([''])
const burdenDescription = ref('')
const outlineLoading = ref(false)
const outlineAnswer = ref('')
const traditionalOutline = ref('')
const englishOutline = ref('')
const resultTab = ref('zh')
const tradLoading = ref(false)
const enLoading = ref(false)
const docxLoading = ref(false)
const outlineUsage = ref(null)
const outlineMeta = ref({ cached: false, cacheKey: null })

const natureOptions = [
  { value: '一般性', label: '一般性' },
  { value: '真理启示', label: '真理启示' },
  { value: '生命经历', label: '生命经历' },
  { value: '应用实行', label: '应用实行' },
]

const nonEmptyBurdenPoints = computed(() =>
  burdenPoints.value.map((p) => (p || '').trim()).filter(Boolean)
)

const canGenerateOutline = computed(() => (topic.value || '').trim().length > 0 && !outlineLoading.value)

function goHome() {
  router.push('/')
}

function addBurdenPoint() {
  if (burdenPoints.value.length < 5) burdenPoints.value.push('')
}

function removeBurdenPoint(idx) {
  if (burdenPoints.value.length > 1) burdenPoints.value.splice(idx, 1)
}

function parseApiError(err) {
  const data = err?.response?.data || {}
  let detail = data.detail
  if (Array.isArray(detail)) {
    detail = detail.map((x) => x?.msg || JSON.stringify(x)).join('；')
  }
  return detail || data.error || data.message || err?.message || '请求失败'
}

async function refreshUsage() {
  try {
    const res = await http.get('/api/cn/auth/usage')
    outlineUsage.value = res.data?.outline || { used: 0, limit: 3 }
  } catch {
    outlineUsage.value = null
  }
}

async function onGenerateOutline() {
  const q = topic.value.trim()
  if (!q) return
  if (!getToken()) {
    router.push('/login')
    return
  }
  outlineLoading.value = true
  outlineAnswer.value = ''
  traditionalOutline.value = ''
  englishOutline.value = ''
  resultTab.value = 'zh'
  outlineMeta.value = { cached: false, cacheKey: null }

  try {
    // 阶段0：自动生成负担说明（后台静默执行，用户无感知）
    if (nonEmptyBurdenPoints.value.length > 0) {
      try {
        const burdenRes = await http.post('/api/cn/panai/generate_burden', {
          query: topic.value.trim(),
          outline_nature: outlineNature.value,
          burden_points: nonEmptyBurdenPoints.value,
        })
        burdenDescription.value = burdenRes.data?.burden_description || ''
      } catch {
        // 阶段0失败不阻断，继续用空负担说明生成纲目
        burdenDescription.value = ''
      }
    }
    // 阶段1：生成纲目
    const res = await http.post(
      '/api/kg_rag/query',
      {
        query: q,
        params: {
          outline_nature: outlineNature.value,
          burden_description: burdenDescription.value.trim(),
          audience: '',
          depth: 'general',
        },
      },
      { timeout: 300000 }
    )
    const data = res.data || {}
    if (!data.answer) {
      toastError(data.error || '纲目生成失败，请稍后重试')
      return
    }
    outlineAnswer.value = data.answer
    outlineMeta.value = {
      cached: !!data.cached,
      cacheKey: data.cache_key || null,
    }
    if (data.cached && data.answer_zh_tw) {
      traditionalOutline.value = data.answer_zh_tw
    }
    if (data.cached && data.answer_en) {
      englishOutline.value = data.answer_en
    }
    toastSuccess(outlineMeta.value.cached ? '已加载缓存纲目' : '纲目生成完成')
    await refreshUsage()
  } catch (err) {
    const status = err?.response?.status
    const msg = parseApiError(err)
    if (status === 429) {
      toastWarning(msg || '今日纲目制作次数已达上限，请明天再来')
    } else {
      toastError(msg)
    }
  } finally {
    outlineLoading.value = false
  }
}

async function copyOutline() {
  const t = topic.value.trim()
  const body = resultTab.value === 'tw'
    ? traditionalOutline.value
    : resultTab.value === 'en'
      ? englishOutline.value
      : outlineAnswer.value
  const text = t ? `${t}\n\n${body}` : body
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    toastSuccess('已复制')
  } catch {
    toastError('复制失败')
  }
}

async function toTraditional() {
  if (!outlineAnswer.value) return
  tradLoading.value = true
  try {
    const res = await http.post('/api/ai_search/outline_to_traditional', {
      content: outlineAnswer.value,
    })
    const tw = res.data?.answer_zh_tw
    if (!tw) throw new Error(res.data?.error || '繁体转换失败')
    traditionalOutline.value = tw
    resultTab.value = 'tw'
    if (outlineMeta.value.cacheKey) {
      await http.post('/api/kg_rag/cache_translation', {
        cache_key: outlineMeta.value.cacheKey,
        field: 'answer_zh_tw',
        value: tw,
      })
    }
    toastSuccess('繁体转换完成')
  } catch (err) {
    toastError(parseApiError(err))
  } finally {
    tradLoading.value = false
  }
}

async function toEnglish() {
  if (!outlineAnswer.value) return
  enLoading.value = true
  try {
    const res = await http.post('/api/ai_search/translate_outline', {
      chinese_outline: outlineAnswer.value,
      outline_topic: topic.value.trim() || undefined,
    })
    const en = res.data?.answer_en
    if (!en) throw new Error(res.data?.error || '英文翻译失败')
    englishOutline.value = en
    resultTab.value = 'en'
    if (outlineMeta.value.cacheKey) {
      await http.post('/api/kg_rag/cache_translation', {
        cache_key: outlineMeta.value.cacheKey,
        field: 'answer_en',
        value: en,
      })
    }
    toastSuccess('英文纲目已生成')
  } catch (err) {
    toastError(parseApiError(err))
  } finally {
    enLoading.value = false
  }
}

async function downloadDocx() {
  let direction = 'en2zh'
  let payloadText = outlineAnswer.value
  if (resultTab.value === 'en') {
    if (!englishOutline.value) {
      toastWarning('请先生成英文纲目')
      return
    }
    direction = 'zh2en'
    payloadText = englishOutline.value
  } else if (resultTab.value === 'tw') {
    if (!traditionalOutline.value) {
      toastWarning('请先生成繁体纲目')
      return
    }
    direction = 'zh_cn2tw'
    payloadText = traditionalOutline.value
  } else if (!outlineAnswer.value) {
    toastWarning('请先生成纲目')
    return
  }

  const t = topic.value.trim()
  const fullText = t ? `${t}\n\n${payloadText}` : payloadText

  docxLoading.value = true
  try {
    const res = await http.post('/api/ai_search/format_outline_only', {
      direction,
      translated_text: fullText,
      output_format: 'docx',
      is_outline: true,
    })
    const b64 = res.data?.docx_base64
    if (!b64) throw new Error(res.data?.error || 'DOCX 生成失败')
    const filename = res.data?.filename || 'outline.docx'
    const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
    const blob = new Blob([bin], {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
    toastSuccess('DOCX 已下载')
  } catch (err) {
    toastError(parseApiError(err))
  } finally {
    docxLoading.value = false
  }
}

onMounted(() => {
  refreshUsage()
})
</script>

<style scoped>
.outline-root {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--cn-bg-page);
}

.section {
  margin-bottom: 28px;
}

.section:last-child {
  margin-bottom: 0;
}

.section h2 {
  margin: 0 0 16px;
  font-size: 17px;
  font-weight: 500;
  color: var(--cn-text-primary);
}

.burden-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.burden-num {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #1B6CA8;
  color: #ffffff;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 600;
}

.remove-btn {
  border: none;
  background: var(--cn-danger);
  color: #fff;
  width: 28px;
  height: 28px;
  border-radius: var(--cn-radius-sm);
  cursor: pointer;
  flex-shrink: 0;
}

.char-warn {
  color: var(--cn-danger);
  font-size: 12px;
  white-space: nowrap;
}

.add-btn {
  margin-top: 4px;
}

.outline-loading {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 20px;
  color: var(--cn-text-secondary);
}

.result-box {
  margin-top: 20px;
}

.outline-topic-title {
  text-align: center;
  font-size: 17px;
  font-weight: 600;
  color: var(--cn-text-primary);
  margin-bottom: 12px;
  letter-spacing: 0.05em;
}

.outline-gen-btn {
  display: block !important;
  margin: 4px auto 0 !important;
  padding: 14px 56px !important;
  height: auto !important;
  font-size: 16px !important;
  font-weight: 700 !important;
  letter-spacing: 0.04em;
  border-radius: 10px !important;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.toolbar-btn {
  border: 1px solid #CCE4F5 !important;
  background: #ffffff !important;
  color: #4A6A84 !important;
}

.toolbar-btn:hover:not(:disabled) {
  border-color: #1B6CA8 !important;
  color: #1B6CA8 !important;
}

.outline-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 14px;
  margin: 0;
  max-height: 520px;
  overflow: auto;
}

.meta-tag {
  margin-top: 8px;
  font-size: 12px;
  color: var(--cn-success);
}
</style>

<template>
  <div class="feast-wrap">
    <ToolsHeader title="节期纲目" />

    <!-- 勾选区 -->
    <a-card size="small" class="input-card">
      <div class="check-row">
        <a-checkbox v-model:checked="checkMorning" class="chk chk-morning" :class="{ active: checkMorning }">晨兴信息选读的纲目</a-checkbox>
        <a-checkbox v-model:checked="checkTranscript" class="chk chk-transcript" :class="{ active: checkTranscript }">听抄稿的纲目</a-checkbox>
        <a-checkbox v-model:checked="checkComposite" class="chk chk-composite" :class="{ active: checkComposite }">复合的纲目</a-checkbox>
      </div>
    </a-card>

    <!-- 前三行 -->
    <a-card size="small" class="input-card">
      <a-row :gutter="[12, 12]">
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

    <!-- 输入区 -->
    <a-card size="small" class="input-card">
      <a-row :gutter="[12, 12]">
        <a-col :span="24">
          <div class="param-label"><span class="lbl lbl-outline">纲目原文</span></div>
          <a-textarea
            v-model:value="inputOutline"
            :auto-size="{ minRows: 4, maxRows: 14 }"
            placeholder="粘贴纲目原文（听抄稿纲目需要）"
          />
        </a-col>
        <a-col :span="24">
          <div class="param-label"><span class="lbl lbl-morning">晨兴原文</span></div>
          <a-textarea
            v-model:value="inputMorning"
            :auto-size="{ minRows: 4, maxRows: 14 }"
            placeholder="粘贴晨兴信息选读原文（晨兴纲目需要）"
          />
        </a-col>
        <a-col :span="24">
          <div class="param-label"><span class="lbl lbl-preface">序言 <span class="optional">（可选）</span></span></div>
          <a-textarea
            v-model:value="inputPreface"
            :auto-size="{ minRows: 3, maxRows: 10 }"
            placeholder="听抄稿序言原文，可留空"
          />
        </a-col>
        <a-col :span="24">
          <div class="param-label"><span class="lbl lbl-transcript">听抄稿</span></div>
          <a-textarea
            v-model:value="inputTranscript"
            :auto-size="{ minRows: 4, maxRows: 14 }"
            placeholder="粘贴听抄稿原文（听抄稿纲目需要）"
          />
        </a-col>
        <a-col :span="24">
          <div class="param-label"><span class="lbl lbl-addendum">添言 <span class="optional">（可选）</span></span></div>
          <a-textarea
            v-model:value="inputAddendum"
            :auto-size="{ minRows: 3, maxRows: 10 }"
            placeholder="听抄稿添言原文，可留空"
          />
        </a-col>
        <a-col :span="24">
          <a-button
            type="primary"
            class="gen-btn"
            :loading="anyBusy"
            @click="generateAll"
          >
            生成
          </a-button>
        </a-col>
      </a-row>
    </a-card>

    <!-- 结果区 -->
    <a-row :gutter="12" style="margin-top:16px">
      <!-- 晨兴纲目 -->
      <a-col :span="8" v-if="checkMorning">
        <a-card size="small" class="result-card">
          <template #title>晨兴信息选读的纲目</template>
          <template #extra>
            <a-button
              v-if="morningResult.outline"
              size="small"
              @click="copyResult('morning', morningText)"
            >{{ copiedKey === 'morning' ? '已复制！' : '复制' }}</a-button>
          </template>

          <div v-if="morningResult.loading" class="loading-row">
            <a-spin size="small" /><span>生成晨兴纲目中…</span>
          </div>

          <pre v-if="morningResult.outline" class="outline-text">{{ morningText }}</pre>

          <a-alert
            v-if="morningResult.error"
            type="error"
            :message="morningResult.error"
            show-icon
            style="margin-top:10px"
          />
        </a-card>
      </a-col>

      <!-- 听抄稿纲目 -->
      <a-col :span="8" v-if="checkTranscript">
        <a-card size="small" class="result-card">
          <template #title>听抄稿的纲目</template>
          <template #extra>
            <a-button
              v-if="transcriptResult.outline"
              size="small"
              @click="copyResult('transcript', transcriptText)"
            >{{ copiedKey === 'transcript' ? '已复制！' : '复制' }}</a-button>
          </template>

          <div v-if="transcriptResult.loading" class="loading-row">
            <a-spin size="small" /><span>生成听抄稿纲目中…</span>
          </div>

          <pre v-if="transcriptResult.outline" class="outline-text">{{ transcriptText }}</pre>

          <a-alert
            v-if="transcriptResult.error"
            type="error"
            :message="transcriptResult.error"
            show-icon
            style="margin-top:10px"
          />
        </a-card>
      </a-col>

      <!-- 复合纲目 -->
      <a-col :span="8" v-if="checkComposite">
        <a-card size="small" class="result-card">
          <template #title>复合的纲目</template>
          <template #extra>
            <a-button
              v-if="compositeResult.outline"
              size="small"
              @click="copyResult('composite', compositeText)"
            >{{ copiedKey === 'composite' ? '已复制！' : '复制' }}</a-button>
          </template>

          <div v-if="compositeResult.waiting" class="loading-row">
            <a-spin size="small" /><span>等待前两项完成…</span>
          </div>
          <div v-else-if="compositeResult.loading" class="loading-row">
            <a-spin size="small" /><span>生成复合纲目中…</span>
          </div>

          <pre v-if="compositeResult.outline" class="outline-text">{{ compositeText }}</pre>

          <a-alert
            v-if="compositeResult.error"
            type="error"
            :message="compositeResult.error"
            show-icon
            style="margin-top:10px"
          />
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch } from "vue"
import { message } from "ant-design-vue"
import ToolsHeader from "./ToolsHeader.vue"

const apiBase = ""

// 勾选状态
const checkMorning = ref(false)
const checkTranscript = ref(false)
const checkComposite = ref(false)

// 前三行
const line1 = ref("")  // 总题
const line2 = ref("")  // 系列题
const line3 = ref("")  // 篇题

// 输入区
const inputOutline = ref("")        // 纲目原文
const inputMorning = ref("")        // 晨兴原文
const inputPreface = ref("")        // 序言（可选）
const inputTranscript = ref("")     // 听抄稿
const inputAddendum = ref("")       // 添言（可选）

// 结果区（各自独立）
const morningResult = reactive({ outline: "", loading: false, error: "" })
const transcriptResult = reactive({ outline: "", preface_outline: "", addendum_outline: "", loading: false, error: "" })
const compositeResult = reactive({ outline: "", loading: false, waiting: false, error: "" })

const copiedKey = ref("")

const DIVIDER = "──────"

// 勾选联动
watch(checkComposite, (val) => {
  if (val) {
    checkMorning.value = true
    checkTranscript.value = true
  }
})
watch([checkMorning, checkTranscript], ([m, t]) => {
  if ((!m || !t) && checkComposite.value) {
    checkComposite.value = false
  }
})

const anyBusy = computed(() =>
  morningResult.loading || transcriptResult.loading ||
  compositeResult.loading || compositeResult.waiting
)

const header = computed(() => `${line1.value}\n${line2.value}\n${line3.value}`)

const morningText = computed(() =>
  `${header.value}\n${DIVIDER}\n${morningResult.outline}`
)

function buildTranscriptDisplay(includeHeader = true) {
  const headerStr = [line1.value, line2.value, line3.value].join('\n')
  const separator = '\n──────\n'
  let main = transcriptResult.outline

  // 若有序言纲目，精确插入到「读经：」行之后、「壹」之前
  if (transcriptResult.preface_outline) {
    const lines = main.split('\n')
    const jingIndex = lines.findIndex(l => l.trim().startsWith('读经：') || l.trim().startsWith('读经:'))
    if (jingIndex !== -1) {
      lines.splice(jingIndex + 1, 0, '\n' + transcriptResult.preface_outline)
      main = lines.join('\n')
    } else {
      main = transcriptResult.preface_outline + '\n\n' + main
    }
  }

  // 添言纲目拼在主纲目最后
  let result = includeHeader ? (headerStr + separator + main) : main
  if (transcriptResult.addendum_outline) {
    result += separator + transcriptResult.addendum_outline
  }
  return result
}

const transcriptText = computed(() => buildTranscriptDisplay(true))

const compositeText = computed(() =>
  `${header.value}\n${DIVIDER}\n${compositeResult.outline}`
)

function validate() {
  if (!line1.value.trim() || !line2.value.trim() || !line3.value.trim()) {
    alert("请填写前三行")
    return false
  }
  if (!checkMorning.value && !checkTranscript.value && !checkComposite.value) {
    alert("请至少勾选一种纲目类型")
    return false
  }
  if (checkMorning.value && !inputMorning.value.trim()) {
    alert("勾选了晨兴纲目，请填写晨兴原文")
    return false
  }
  if (checkTranscript.value && (!inputOutline.value.trim() || !inputTranscript.value.trim())) {
    alert("勾选了听抄稿纲目，请填写纲目原文和听抄稿")
    return false
  }
  return true
}

async function callMorning() {
  morningResult.outline = ""
  morningResult.error = ""
  morningResult.loading = true
  try {
    const res = await fetch(`${apiBase}/api/testb/feast_outline/morning_revival`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: inputMorning.value }),
    })
    if (!res.ok) throw new Error(`晨兴纲目生成失败（${res.status}）`)
    morningResult.outline = (await res.json()).outline || ""
  } catch (e) {
    morningResult.error = e.message || "晨兴纲目生成失败"
  } finally {
    morningResult.loading = false
  }
}

async function callTranscript() {
  transcriptResult.outline = ""
  transcriptResult.preface_outline = ""
  transcriptResult.addendum_outline = ""
  transcriptResult.error = ""
  transcriptResult.loading = true
  try {
    const res = await fetch(`${apiBase}/api/testb/feast_outline/transcript`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        original_outline: inputOutline.value,
        transcript: inputTranscript.value,
        transcript_preface: inputPreface.value,
        transcript_addendum: inputAddendum.value,
      }),
    })
    if (!res.ok) throw new Error(`听抄稿纲目生成失败（${res.status}）`)
    const data = await res.json()
    transcriptResult.outline = data.outline || ""
    transcriptResult.preface_outline = data.preface_outline || ""
    transcriptResult.addendum_outline = data.addendum_outline || ""
  } catch (e) {
    transcriptResult.error = e.message || "听抄稿纲目生成失败"
  } finally {
    transcriptResult.loading = false
  }
}

async function callComposite() {
  compositeResult.outline = ""
  compositeResult.error = ""
  compositeResult.loading = true
  try {
    const res = await fetch(`${apiBase}/api/testb/feast_outline/composite`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        morning_revival_outline: morningResult.outline,
        transcript_outline: buildTranscriptDisplay(false),
      }),
    })
    if (!res.ok) throw new Error(`复合纲目生成失败（${res.status}）`)
    compositeResult.outline = (await res.json()).outline || ""
  } catch (e) {
    compositeResult.error = e.message || "复合纲目生成失败"
  } finally {
    compositeResult.loading = false
  }
}

async function generateAll() {
  if (!validate()) return

  const doMorning = checkMorning.value
  const doTranscript = checkTranscript.value
  const doComposite = checkComposite.value

  if (doMorning && doTranscript) {
    if (doComposite) compositeResult.waiting = true
    // Step 1：并发晨兴 + 听抄稿
    await Promise.all([callMorning(), callTranscript()])
    if (doComposite) compositeResult.waiting = false
    // Step 2：复合（依赖前两项结果）
    if (doComposite) {
      if (!morningResult.outline || !transcriptResult.outline) {
        compositeResult.error = "晨兴或听抄稿纲目生成失败，无法生成复合纲目"
        return
      }
      await callComposite()
    }
  } else if (doMorning) {
    await callMorning()
  } else if (doTranscript) {
    await callTranscript()
  }
}

function copyResult(key, text) {
  navigator.clipboard.writeText(text).then(() => {
    copiedKey.value = key
    setTimeout(() => {
      if (copiedKey.value === key) copiedKey.value = ""
    }, 1500)
  }).catch(() => message.error("复制失败"))
}
</script>

<style scoped>
.feast-wrap { padding: 4px 0; }
.input-card { margin-bottom: 8px; }
.check-row { display: flex; gap: 16px; flex-wrap: wrap; }
.param-label { font-size: 13px; color: #555; margin-bottom: 6px; }
.optional { color: #b07; font-size: 12px; }

/* 输入框标签：圆角带背景色标签 */
.lbl {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid transparent;
  font-size: 13px;
}
.lbl-title     { background: #fff7e6; border-color: #ffd591; }
.lbl-outline   { background: #e6f4ff; border-color: #91caff; }
.lbl-morning   { background: #f6ffed; border-color: #b7eb8f; }
.lbl-preface   { background: #fff1f0; border-color: #ffa39e; }
.lbl-transcript{ background: #fffbe6; border-color: #ffe58f; }
.lbl-addendum  { background: #f9f0ff; border-color: #d3adf7; }

/* 勾选框标签：带背景色 */
.chk {
  padding: 5px 12px;
  border-radius: 6px;
  border: 1px solid transparent;
  transition: background 0.2s, border-color 0.2s;
}
.chk-morning    { background: #e6f4ff; border-color: #91caff; }
.chk-transcript { background: #f6ffed; border-color: #b7eb8f; }
.chk-composite  { background: #f9f0ff; border-color: #d3adf7; }
/* 选中时背景加深一档 */
.chk-morning.active    { background: #bae0ff; border-color: #69b1ff; }
.chk-transcript.active { background: #d9f7be; border-color: #95de64; }
.chk-composite.active  { background: #efdbff; border-color: #b37feb; }
.gen-btn {
  background: #722ed1;
  border-color: #722ed1;
}
.gen-btn:hover {
  background: #9254de !important;
  border-color: #9254de !important;
}
.result-card { height: 100%; }
.result-card :deep(.ant-card-head) {
  background: #f9f0ff;
  color: #531dab;
}
.outline-text {
  font-size: 13px; line-height: 1.8; white-space: pre-wrap;
  word-break: break-word; font-family: inherit; margin: 0;
}
.loading-row {
  display: flex; align-items: center; gap: 8px;
  color: #999; font-size: 13px; padding: 16px 0;
}
</style>

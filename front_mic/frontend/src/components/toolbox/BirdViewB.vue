<template>
  <div class="bird-view-wrap">
    <ToolsHeader title="词典-鸟瞰纲目" />

    <!-- 输入区 -->
    <a-card size="small" class="input-card">
      <a-row :gutter="[12, 12]">
        <a-col :span="24">
          <div class="param-label">关键词</div>
          <a-input
            v-model:value="keyword"
            placeholder="请输入关键词，如：创造、得胜者"
            allow-clear
            style="max-width: 320px"
          />
        </a-col>
        <a-col :span="12">
          <div class="param-label">职事信息内容</div>
          <a-textarea
            v-model:value="ministryContent"
            :auto-size="{ minRows: 10, maxRows: 24 }"
            placeholder="粘贴职事信息原文"
          />
        </a-col>
        <a-col :span="12">
          <div class="param-label">节期纲目内容</div>
          <a-textarea
            v-model:value="feastContent"
            :auto-size="{ minRows: 10, maxRows: 24 }"
            placeholder="粘贴节期纲目原文"
          />
        </a-col>
        <a-col :span="24">
          <a-button
            type="primary"
            :loading="anyLoading"
            :disabled="!canRun"
            @click="generateAll"
          >
            并发生成
          </a-button>
          <span v-if="!canRun" class="hint">请填写关键词及至少一篇内容</span>
        </a-col>
      </a-row>
    </a-card>

    <!-- 结果区 -->
    <a-row :gutter="12" style="margin-top:16px">
      <!-- 职事信息鸟瞰 -->
      <a-col :span="12" v-if="ministryContent.trim()">
        <a-card size="small" class="result-card">
          <template #title>职事信息鸟瞰</template>
          <template #extra>
            <a-button
              v-if="results.ministry.outline"
              size="small"
              @click="copyText('ministry', results.ministry.skeleton_text)"
            >{{ copiedKey === 'ministry' ? '已复制！' : '复制' }}</a-button>
          </template>

          <div v-if="results.ministry.skeletonLoading" class="loading-row">
            <a-spin size="small" /><span>生成骨架中…</span>
          </div>
          <div v-else-if="results.ministry.outlineLoading" class="loading-row">
            <a-spin size="small" /><span>生成纲目中…</span>
          </div>

          <a-card
            v-if="results.ministry.skeleton_text"
            size="small"
            class="layer-card"
          >
            <template #title>骨架</template>
            <div class="skeleton-block">
              <div
                v-for="(s, i) in results.ministry.skeleton_json"
                :key="i"
                class="skeleton-step"
              >
                <span class="step-dot">{{ i + 1 }}</span>{{ s.step }}
              </div>
            </div>
          </a-card>

          <a-card
            v-if="results.ministry.outline && !results.ministry.outlineLoading"
            size="small"
            class="layer-card"
          >
            <template #title>纲目</template>
            <pre class="outline-text">{{ results.ministry.outline }}</pre>
            <a-button
              size="small"
              class="outline-copy-btn"
              @click="copyOutline('ministry', results.ministry.outline)"
            >{{ outlineCopiedKey === 'ministry' ? '已复制！' : '复制' }}</a-button>
          </a-card>

          <a-alert
            v-if="results.ministry.error"
            type="error"
            :message="results.ministry.error"
            show-icon
            style="margin-top:10px"
          />
        </a-card>
      </a-col>

      <!-- 节期纲目鸟瞰 -->
      <a-col :span="12" v-if="feastContent.trim()">
        <a-card size="small" class="result-card">
          <template #title>节期纲目鸟瞰</template>
          <template #extra>
            <a-button
              v-if="results.feast.outline"
              size="small"
              @click="copyText('feast', results.feast.skeleton_text)"
            >{{ copiedKey === 'feast' ? '已复制！' : '复制' }}</a-button>
          </template>

          <div v-if="results.feast.skeletonLoading" class="loading-row">
            <a-spin size="small" /><span>生成骨架中…</span>
          </div>
          <div v-else-if="results.feast.outlineLoading" class="loading-row">
            <a-spin size="small" /><span>生成纲目中…</span>
          </div>

          <a-card
            v-if="results.feast.skeleton_text"
            size="small"
            class="layer-card"
          >
            <template #title>骨架</template>
            <div class="skeleton-block">
              <div
                v-for="(s, i) in results.feast.skeleton_json"
                :key="i"
                class="skeleton-step"
              >
                <span class="step-dot">{{ i + 1 }}</span>{{ s.step }}
              </div>
            </div>
          </a-card>

          <a-card
            v-if="results.feast.outline && !results.feast.outlineLoading"
            size="small"
            class="layer-card"
          >
            <template #title>纲目</template>
            <pre class="outline-text">{{ results.feast.outline }}</pre>
            <a-button
              size="small"
              class="outline-copy-btn"
              @click="copyOutline('feast', results.feast.outline)"
            >{{ outlineCopiedKey === 'feast' ? '已复制！' : '复制' }}</a-button>
          </a-card>

          <a-alert
            v-if="results.feast.error"
            type="error"
            :message="results.feast.error"
            show-icon
            style="margin-top:10px"
          />
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from "vue"
import { message } from "ant-design-vue"
import ToolsHeader from "./ToolsHeader.vue"

const apiBase = ""

const keyword = ref("")
const ministryContent = ref("")
const feastContent = ref("")
const copiedKey = ref("")
const outlineCopiedKey = ref("")

const results = reactive({
  ministry: { skeletonLoading: false, outlineLoading: false,
              skeleton_json: [], skeleton_text: "", outline: "", error: "" },
  feast:    { skeletonLoading: false, outlineLoading: false,
              skeleton_json: [], skeleton_text: "", outline: "", error: "" },
})

const anyLoading = computed(() =>
  results.ministry.skeletonLoading || results.ministry.outlineLoading ||
  results.feast.skeletonLoading || results.feast.outlineLoading
)

const canRun = computed(() =>
  !!keyword.value.trim() &&
  (!!ministryContent.value.trim() || !!feastContent.value.trim())
)

function resetResult(birdType) {
  results[birdType].skeletonLoading = false
  results[birdType].outlineLoading = false
  results[birdType].skeleton_json = []
  results[birdType].skeleton_text = ""
  results[birdType].outline = ""
  results[birdType].error = ""
}

async function generateOne(birdType, content) {
  resetResult(birdType)
  // Step A：骨架
  results[birdType].skeletonLoading = true
  try {
    const skeletonRes = await fetch(`${apiBase}/api/testb/bird_view/skeleton`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keyword: keyword.value.trim(), type: birdType, content })
    })
    if (!skeletonRes.ok) throw new Error(`骨架生成失败（${skeletonRes.status}）`)
    const skeletonData = await skeletonRes.json()
    results[birdType].skeleton_json = skeletonData.skeleton_json || []
    results[birdType].skeleton_text = skeletonData.skeleton_text || ""
  } catch (e) {
    results[birdType].error = e.message || "骨架生成失败"
    results[birdType].skeletonLoading = false
    return
  }
  results[birdType].skeletonLoading = false

  // Step B：纲目（串行，用上一步的 skeleton_text）
  results[birdType].outlineLoading = true
  try {
    const outlineRes = await fetch(`${apiBase}/api/testb/bird_view/outline`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keyword: keyword.value.trim(), type: birdType,
                             content, skeleton: results[birdType].skeleton_text })
    })
    if (!outlineRes.ok) throw new Error(`纲目生成失败（${outlineRes.status}）`)
    results[birdType].outline = (await outlineRes.json()).outline || ""
  } catch (e) {
    results[birdType].error = e.message || "纲目生成失败"
  } finally {
    results[birdType].outlineLoading = false
  }
}

async function generateAll() {
  if (!canRun.value) return
  const tasks = []
  if (ministryContent.value.trim()) tasks.push(generateOne("ministry", ministryContent.value))
  if (feastContent.value.trim())    tasks.push(generateOne("feast", feastContent.value))
  await Promise.allSettled(tasks)
}

function copyText(birdType, text) {
  navigator.clipboard.writeText(text).then(() => {
    copiedKey.value = birdType
    setTimeout(() => {
      if (copiedKey.value === birdType) copiedKey.value = ""
    }, 1500)
  }).catch(() => message.error("复制失败"))
}

function copyOutline(birdType, text) {
  navigator.clipboard.writeText(text).then(() => {
    outlineCopiedKey.value = birdType
    setTimeout(() => {
      if (outlineCopiedKey.value === birdType) outlineCopiedKey.value = ""
    }, 1500)
  }).catch(() => message.error("复制失败"))
}
</script>

<style scoped>
.bird-view-wrap { padding: 4px 0; }
.input-card { margin-bottom: 4px; }
.param-label { font-size: 13px; color: #555; margin-bottom: 6px; }
.hint { margin-left: 12px; color: #999; font-size: 12px; }
.result-card { height: 100%; }
.skeleton-block { margin-bottom: 0; }
.skeleton-step {
  display: flex; align-items: flex-start; gap: 6px;
  font-size: 13px; line-height: 1.7; margin-bottom: 2px;
}
.step-dot {
  flex-shrink: 0; width: 18px; height: 18px; border-radius: 50%;
  background: #1677ff; color: #fff; font-size: 11px;
  display: flex; align-items: center; justify-content: center; margin-top: 2px;
}
.outline-text {
  font-size: 13px; line-height: 1.8; white-space: pre-wrap;
  font-family: inherit; margin: 0;
}
.outline-copy-btn { margin-top: 8px; }
.loading-row {
  display: flex; align-items: center; gap: 8px;
  color: #999; font-size: 13px; padding: 16px 0;
}
.layer-card {
  margin-top: 10px;
  border-radius: 6px;
}
.layer-card :deep(.ant-card-head) {
  min-height: 32px;
  padding: 0 10px;
  font-size: 12px;
  color: #888;
}
.layer-card :deep(.ant-card-body) {
  padding: 8px 10px;
}
</style>

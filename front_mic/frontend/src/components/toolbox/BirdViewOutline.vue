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
            @click="runAll"
          >
            并发生成
          </a-button>
          <span v-if="!canRun" class="hint">请填写关键词及至少一篇内容</span>
        </a-col>
      </a-row>
    </a-card>

    <!-- 结果区 -->
    <a-row v-if="results.ministry || results.feast" :gutter="12" style="margin-top:16px">
      <!-- 职事信息鸟瞰 -->
      <a-col :span="ministryContent ? 12 : 0" v-if="ministryContent">
        <a-card size="small" class="result-card">
          <template #title>
            <span>职事信息鸟瞰</span>
            <a-tag :color="statusColor(results.ministry)" style="margin-left:8px">
              {{ statusLabel(results.ministry) }}
            </a-tag>
            <span v-if="results.ministry?.elapsed" class="elapsed">
              {{ results.ministry.elapsed }}s
            </span>
          </template>
          <template #extra>
            <a-button
              v-if="results.ministry?.outline"
              size="small"
              @click="copyText(results.ministry.outline)"
            >复制</a-button>
          </template>

          <!-- 骨架 -->
          <div v-if="results.ministry?.skeleton_text" class="skeleton-block">
            <div class="skeleton-title">骨架</div>
            <div
              v-for="(s, i) in results.ministry.skeleton_json"
              :key="i"
              class="skeleton-step"
            >
              <span class="step-dot">{{ i + 1 }}</span>{{ s.step }}
            </div>
          </div>
          <a-divider v-if="results.ministry?.skeleton_text && results.ministry?.outline" style="margin:10px 0" />

          <!-- 纲目正文 -->
          <div v-if="results.ministry?.outlineLoading" class="loading-row">
            <a-spin size="small" /><span>生成纲目中…</span>
          </div>
          <pre v-else-if="results.ministry?.outline" class="outline-text">{{ results.ministry.outline }}</pre>
          <div v-else-if="results.ministry?.skeletonLoading" class="loading-row">
            <a-spin size="small" /><span>生成骨架中…</span>
          </div>
          <a-alert v-else-if="results.ministry?.error" type="error" :message="results.ministry.error" show-icon />
        </a-card>
      </a-col>

      <!-- 节期纲目鸟瞰 -->
      <a-col :span="feastContent ? 12 : 0" v-if="feastContent">
        <a-card size="small" class="result-card">
          <template #title>
            <span>节期纲目鸟瞰</span>
            <a-tag :color="statusColor(results.feast)" style="margin-left:8px">
              {{ statusLabel(results.feast) }}
            </a-tag>
            <span v-if="results.feast?.elapsed" class="elapsed">
              {{ results.feast.elapsed }}s
            </span>
          </template>
          <template #extra>
            <a-button
              v-if="results.feast?.outline"
              size="small"
              @click="copyText(results.feast.outline)"
            >复制</a-button>
          </template>

          <div v-if="results.feast?.skeleton_text" class="skeleton-block">
            <div class="skeleton-title">骨架</div>
            <div
              v-for="(s, i) in results.feast.skeleton_json"
              :key="i"
              class="skeleton-step"
            >
              <span class="step-dot">{{ i + 1 }}</span>{{ s.step }}
            </div>
          </div>
          <a-divider v-if="results.feast?.skeleton_text && results.feast?.outline" style="margin:10px 0" />

          <div v-if="results.feast?.outlineLoading" class="loading-row">
            <a-spin size="small" /><span>生成纲目中…</span>
          </div>
          <pre v-else-if="results.feast?.outline" class="outline-text">{{ results.feast.outline }}</pre>
          <div v-else-if="results.feast?.skeletonLoading" class="loading-row">
            <a-spin size="small" /><span>生成骨架中…</span>
          </div>
          <a-alert v-else-if="results.feast?.error" type="error" :message="results.feast.error" show-icon />
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from "vue"
import axios from "axios"
import { message } from "ant-design-vue"
import ToolsHeader from "./ToolsHeader.vue"

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || ""

function getAuthHeaders() {
  const token = localStorage.getItem("token")
  if (!token) { message.error("请先登录"); return null }
  return { Authorization: `Bearer ${token}` }
}

const keyword = ref("")
const ministryContent = ref("")
const feastContent = ref("")

const results = reactive({
  ministry: null,
  feast: null,
})

const anyLoading = computed(() =>
  results.ministry?.skeletonLoading || results.ministry?.outlineLoading ||
  results.feast?.skeletonLoading || results.feast?.outlineLoading
)

const canRun = computed(() =>
  keyword.value.trim() &&
  (ministryContent.value.trim() || feastContent.value.trim())
)

function statusColor(r) {
  if (!r) return "default"
  if (r.error) return "red"
  if (r.outline) return "green"
  if (r.skeletonLoading || r.outlineLoading) return "blue"
  return "default"
}
function statusLabel(r) {
  if (!r) return ""
  if (r.error) return "失败"
  if (r.outline) return "完成"
  if (r.outlineLoading) return "生成纲目…"
  if (r.skeletonLoading) return "生成骨架…"
  return ""
}

async function runOne(type, content) {
  const headers = getAuthHeaders()
  if (!headers) return
  const key = type === "ministry" ? "ministry" : "feast"
  const t0 = Date.now()

  results[key] = { skeletonLoading: true, outlineLoading: false, skeleton_json: [], skeleton_text: "", outline: "", error: null, elapsed: null }

  // Step A：生成骨架
  let skeletonText = ""
  let skeletonJson = []
  try {
    const res = await axios.post(
      `${apiBase}/api/kg_rag/bird_view/skeleton`,
      { keyword: keyword.value.trim(), type, content },
      { headers }
    )
    skeletonJson = res.data.skeleton_json || []
    skeletonText = res.data.skeleton_text || ""
    results[key] = { ...results[key], skeletonLoading: false, outlineLoading: true, skeleton_json: skeletonJson, skeleton_text: skeletonText }
  } catch (e) {
    results[key] = { ...results[key], skeletonLoading: false, error: e.response?.data?.detail || e.message || "骨架生成失败", elapsed: ((Date.now() - t0) / 1000).toFixed(1) }
    return
  }

  // Step B：生成纲目
  try {
    const res = await axios.post(
      `${apiBase}/api/kg_rag/bird_view/outline`,
      { keyword: keyword.value.trim(), type, content, skeleton: skeletonText },
      { headers }
    )
    results[key] = {
      ...results[key],
      outlineLoading: false,
      outline: res.data.outline || "",
      elapsed: ((Date.now() - t0) / 1000).toFixed(1),
    }
  } catch (e) {
    results[key] = { ...results[key], outlineLoading: false, error: e.response?.data?.detail || e.message || "纲目生成失败", elapsed: ((Date.now() - t0) / 1000).toFixed(1) }
  }
}

function runAll() {
  if (!canRun.value) return
  const headers = getAuthHeaders()
  if (!headers) return
  results.ministry = null
  results.feast = null
  const tasks = []
  if (ministryContent.value.trim()) tasks.push(runOne("ministry", ministryContent.value.trim()))
  if (feastContent.value.trim()) tasks.push(runOne("feast", feastContent.value.trim()))
  Promise.allSettled(tasks)
}

function copyText(text) {
  navigator.clipboard.writeText(text).then(() => message.success("已复制"))
}
</script>

<style scoped>
.bird-view-wrap { padding: 4px 0; }
.input-card { margin-bottom: 4px; }
.param-label { font-size: 13px; color: #555; margin-bottom: 6px; }
.hint { margin-left: 12px; color: #999; font-size: 12px; }
.result-card { height: 100%; }
.skeleton-block { margin-bottom: 4px; }
.skeleton-title { font-size: 11px; color: #999; margin-bottom: 6px; }
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
.loading-row {
  display: flex; align-items: center; gap: 8px;
  color: #999; font-size: 13px; padding: 16px 0;
}
.elapsed { margin-left: 6px; color: #999; font-size: 12px; }
</style>

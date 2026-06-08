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
            <a-button
              v-if="results.ministry?.outline"
              type="primary"
              ghost
              size="small"
              :loading="results.ministry?.sourceLoading"
              :disabled="results.ministry?.sourceLoading"
              @click="generateSource('ministry')"
            >{{ results.ministry?.sourceLoading ? '加出处中…' : '加出处' }}</a-button>
          </template>

          <div v-if="results.ministry?.skeletonLoading" class="loading-row">
            <a-spin size="small" /><span>生成骨架中…</span>
          </div>
          <div v-else-if="results.ministry?.outlineLoading" class="loading-row">
            <a-spin size="small" /><span>生成纲目中…</span>
          </div>

          <a-card
            v-if="results.ministry?.skeleton_text"
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
            v-if="results.ministry?.outline && !results.ministry?.outlineLoading"
            size="small"
            class="layer-card"
          >
            <template #title>纲目</template>
            <template #extra>
              <a-button
                size="small"
                @click="downloadFormat('ministry', false)"
              >下载原纲目</a-button>
            </template>
            <pre class="outline-text">{{ results.ministry.outline }}</pre>
          </a-card>

          <a-card
            v-if="results.ministry?.outline_with_source"
            size="small"
            class="layer-card layer-card--source"
          >
            <template #title>带出处版</template>
            <template #extra>
              <a-button
                size="small"
                @click="downloadFormat('ministry', true)"
              >下载带出处</a-button>
            </template>
            <pre class="outline-text">{{ results.ministry.outline_with_source }}</pre>
          </a-card>
          <div v-if="results.ministry?.sourceError" class="source-error">{{ results.ministry.sourceError }}</div>

          <a-alert v-if="results.ministry?.error" type="error" :message="results.ministry.error" show-icon />
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
            <a-button
              v-if="results.feast?.outline"
              type="primary"
              ghost
              size="small"
              :loading="results.feast?.sourceLoading"
              :disabled="results.feast?.sourceLoading"
              @click="generateSource('feast')"
            >{{ results.feast?.sourceLoading ? '加出处中…' : '加出处' }}</a-button>
          </template>

          <div v-if="results.feast?.skeletonLoading" class="loading-row">
            <a-spin size="small" /><span>生成骨架中…</span>
          </div>
          <div v-else-if="results.feast?.outlineLoading" class="loading-row">
            <a-spin size="small" /><span>生成纲目中…</span>
          </div>

          <a-card
            v-if="results.feast?.skeleton_text"
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
            v-if="results.feast?.outline && !results.feast?.outlineLoading"
            size="small"
            class="layer-card"
          >
            <template #title>纲目</template>
            <template #extra>
              <a-button
                size="small"
                @click="downloadFormat('feast', false)"
              >下载原纲目</a-button>
            </template>
            <pre class="outline-text">{{ results.feast.outline }}</pre>
          </a-card>

          <a-card
            v-if="results.feast?.outline_with_source"
            size="small"
            class="layer-card layer-card--source"
          >
            <template #title>带出处版</template>
            <template #extra>
              <a-button
                size="small"
                @click="downloadFormat('feast', true)"
              >下载带出处</a-button>
            </template>
            <pre class="outline-text">{{ results.feast.outline_with_source }}</pre>
          </a-card>
          <div v-if="results.feast?.sourceError" class="source-error">{{ results.feast.sourceError }}</div>

          <a-alert v-if="results.feast?.error" type="error" :message="results.feast.error" show-icon />
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
  const key = type === "ministry" ? "ministry" : "feast"
  const t0 = Date.now()

  results[key] = {
    skeletonLoading: true,
    outlineLoading: false,
    sourceLoading: false,
    skeleton_json: [],
    skeleton_text: "",
    outline: "",
    outline_with_source: "",
    sourceError: "",
    error: null,
    elapsed: null,
  }

  // Step A：生成骨架
  let skeletonText = ""
  let skeletonJson = []
  try {
    const res = await axios.post(
      `${apiBase}/api/testc/bird_view/skeleton`,
      { keyword: keyword.value.trim(), type, content },
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
      `${apiBase}/api/testc/bird_view/outline`,
      { keyword: keyword.value.trim(), type, content, skeleton: skeletonText },
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

async function generateSource(birdType) {
  const item = results[birdType]
  if (!item?.outline) return
  const key = birdType
  results[key].sourceLoading = true
  results[key].sourceError = ""
  try {
    const res = await axios.post(
      `${apiBase}/api/testc/bird_view/source`,
      {
        keyword: keyword.value.trim(),
        type: birdType,
        content: birdType === "ministry" ? ministryContent.value : feastContent.value,
        outline: item.outline,
      },
    )
    results[key].outline_with_source = res.data.outline_with_source || ""
  } catch (e) {
    results[key].sourceError = "加出处失败，请重试"
  } finally {
    results[key].sourceLoading = false
  }
}

async function downloadFormat(birdType, withSource) {
  const item = results[birdType];
  if (withSource) {
    if (!item?.outline_with_source) return;
  } else if (!item?.outline) {
    return;
  }
  const token = localStorage.getItem("token") || "";
  try {
    const params = new URLSearchParams();
    const typeLabel = birdType === "ministry" ? "3a 职事信息的鸟瞰" : "3b 节期纲目的鸟瞰";
    const outlineToUse = withSource ? item.outline_with_source : item.outline;
    const filenameBase = `${keyword.value.trim()}【${typeLabel}】`;
    params.append("contents", outlineToUse);
    if (withSource) params.append("with_source", "true");
    params.append("filename", withSource ? `${filenameBase}（出处）` : filenameBase);
    params.append("keyword", keyword.value.trim());
    params.append("type", birdType);
    const res = await axios.post(
      `${apiBase}/api/kg_rag/bird_view/format_download`,
      params,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout: 60000,
      }
    );
    const { docx_base64, filename } = res.data;
    const binary = atob(docx_base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const blob = new Blob([bytes], {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    message.error("下载失败：" + (err.response?.data?.detail || err.message));
  }
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
.loading-row {
  display: flex; align-items: center; gap: 8px;
  color: #999; font-size: 13px; padding: 16px 0;
}
.elapsed { margin-left: 6px; color: #999; font-size: 12px; }
.source-error {
  color: red;
  font-size: 13px;
  margin-top: 6px;
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
.layer-card--source {
  border-color: #f5a623;
}
.layer-card--source :deep(.ant-card-head) {
  color: #f5a623;
  border-bottom-color: #f5a623;
}
</style>

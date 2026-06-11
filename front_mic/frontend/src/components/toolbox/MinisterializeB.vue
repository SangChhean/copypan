<script setup>
import { ref, computed, watch, nextTick } from "vue";
import { ArrowLeftOutlined, LoadingOutlined } from "@ant-design/icons-vue";
import { diffChars } from "diff";
import { toastSuccess, toastWarning } from "../utils/Dialog";

const goToolbox = () => {
  window.location.hash = "/tools";
};

const apiBase = "";

const headerSeries = ref("");
const headerTopic = ref("");
const headerChapter = ref("");
const headerReading = ref("");
const inputText = ref("");
const loading = ref(false);
const error = ref(null);
const results = ref([]);
const copied = ref(false);
const statusFilter = ref("all");
const editingMinorKey = ref(null);

const statusTag = {
  original: { color: "#52c41a", bg: "#f6ffed", label: "原文" },
  minor: { color: "#faad14", bg: "#fffbe6", label: "微调" },
  replaced: { color: "#1890ff", bg: "#e6f4ff", label: "替换" },
  manual: { color: "#f5222d", bg: "#fff1f0", label: "需人工" },
};

const lineCount = computed(() =>
  inputText.value.split("\n").filter((l) => l.trim()).length
);

const overLimit = computed(() => lineCount.value > 200);

const canStart = computed(
  () => !!inputText.value.trim() && !overLimit.value && !loading.value
);

const statusCount = computed(() => {
  const c = { original: 0, minor: 0, replaced: 0, manual: 0 };
  results.value.forEach((r) => {
    if (c[r.status] !== undefined) c[r.status] += 1;
  });
  return c;
});

const filteredResults = computed(() => {
  if (statusFilter.value === "all") return results.value;
  return results.value.filter((r) => r.status === statusFilter.value);
});

const OUTLINE_MAX_VH = 66;

function adjustHeight(el) {
  const target = el?.target || el;
  if (!target) return;
  target.style.height = "auto";
  const scrollH = target.scrollHeight;
  if (target.classList.contains("outline-input")) {
    const maxPx = window.innerHeight * (OUTLINE_MAX_VH / 100);
    target.style.height = `${Math.min(scrollH, maxPx)}px`;
    target.style.overflowY = scrollH > maxPx ? "auto" : "hidden";
  } else {
    target.style.height = `${scrollH}px`;
    target.style.overflowY = "hidden";
  }
}

function onInputGrow(event) {
  adjustHeight(event);
}

function resizeOutlineInput() {
  nextTick(() => {
    document.querySelectorAll(".outline-input").forEach((el) => adjustHeight(el));
  });
}

function resizeResultTextareas() {
  nextTick(() => {
    document
      .querySelectorAll(".results-section .result-textarea")
      .forEach((el) => adjustHeight(el));
  });
}

watch(inputText, resizeOutlineInput);
watch(statusFilter, resizeResultTextareas);

function clearAll() {
  headerSeries.value = "";
  headerTopic.value = "";
  headerChapter.value = "";
  headerReading.value = "";
  inputText.value = "";
  results.value = [];
  error.value = null;
  copied.value = false;
  statusFilter.value = "all";
  resizeOutlineInput();
}

async function startMinisterialize() {
  const lines = inputText.value.split("\n").filter((l) => l.trim());
  if (!lines.length) {
    error.value = "请先粘贴纲目，每行一条";
    return;
  }
  if (lines.length > 200) {
    error.value = "最多处理 200 行";
    return;
  }

  loading.value = true;
  error.value = null;
  results.value = [];
  statusFilter.value = "all";

  try {
    const res = await fetch(`${apiBase}/api/testb/ministerialize/process`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lines }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      error.value = data.detail || data.error || "职事化失败";
      return;
    }
    results.value = (data.results || []).map((r, i) => ({
      ...r,
      _key: i,
      result: r.status === "manual" ? "" : (r.result || ""),
    }));
    editingMinorKey.value = null;
    if (!results.value.length) {
      error.value = "没有可处理的非空条目";
    }
  } catch (err) {
    error.value = err.message || "网络错误，请稍后重试";
  } finally {
    loading.value = false;
    if (results.value.length) {
      resizeResultTextareas();
    }
  }
}

function formatReadingLine(text) {
  const t = (text || "").trim();
  if (!t) return "";
  return t.startsWith("读经") ? t : `读经：${t}`;
}

function buildCopyText() {
  const parts = [];
  const series = headerSeries.value.trim();
  const topic = headerTopic.value.trim();
  const chapter = headerChapter.value.trim();
  const reading = formatReadingLine(headerReading.value);

  if (series) parts.push(series);
  if (topic) parts.push(topic);
  if (chapter) parts.push(chapter);
  if (reading) parts.push(reading);

  results.value.forEach((item) => {
    let line = (item.result || "").trim();
    if (!line && item.status === "manual") {
      line = (item.original || "").trim();
    }
    if (line) parts.push(line);
  });

  return parts.join("\n");
}

async function copyAllResults() {
  const text = buildCopyText();
  if (!text) {
    toastWarning("没有可复制的内容");
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    copied.value = true;
    toastSuccess("已复制");
    setTimeout(() => {
      copied.value = false;
    }, 2000);
  } catch {
    toastWarning("复制失败");
  }
}

function showSource(item) {
  return (
    (item.status === "replaced" || item.status === "minor") &&
    !!(item.source || "").trim()
  );
}

function diffParts(item) {
  return diffChars(item.original || "", item.result || "");
}

function startMinorEdit(item) {
  editingMinorKey.value = item._key;
  nextTick(() => {
    const el = document.querySelector(`[data-minor-edit="${item._key}"]`);
    if (el) {
      adjustHeight(el);
      el.focus();
    }
  });
}

function endMinorEdit() {
  editingMinorKey.value = null;
  resizeResultTextareas();
}
</script>

<template>
  <div class="ministerialize-wrap">
    <div class="page-header">
      <div class="back-btn" title="返回工具箱" @click="goToolbox">
        <ArrowLeftOutlined />
        <span>返回</span>
      </div>
      <h1 class="page-title">纲目职事化测试</h1>
      <span class="page-tag">test_B · 端口 8031</span>
    </div>

    <a-card class="input-card">
      <div class="header-fields">
        <div class="header-row">
          <span class="field-label lbl-series">总题</span>
          <a-input
            v-model:value="headerSeries"
            placeholder="可选"
            :disabled="loading"
            allow-clear
          />
        </div>
        <div class="header-row">
          <span class="field-label lbl-topic">系列题</span>
          <a-input
            v-model:value="headerTopic"
            placeholder="可选"
            :disabled="loading"
            allow-clear
          />
        </div>
        <div class="header-row">
          <span class="field-label lbl-chapter">篇题</span>
          <a-input
            v-model:value="headerChapter"
            placeholder="可选"
            :disabled="loading"
            allow-clear
          />
        </div>
        <div class="header-row">
          <span class="field-label lbl-reading">读经</span>
          <a-input
            v-model:value="headerReading"
            placeholder="可选"
            :disabled="loading"
            allow-clear
          />
        </div>
      </div>
      <p class="header-hint">可填可不填，不参与职事化</p>

      <div class="textarea-wrap">
        <span class="line-count">当前 {{ lineCount }} 行</span>
        <textarea
          v-model="inputText"
          class="outline-input auto-grow"
          placeholder="每行一条纲目，最多 200 行"
          :disabled="loading"
          @input="onInputGrow"
        />
      </div>

      <p v-if="overLimit" class="limit-warn">超过 200 行，请删减后再处理</p>

      <div class="actions">
        <a-button
          type="primary"
          class="primary-btn"
          :loading="loading"
          :disabled="!canStart"
          @click="startMinisterialize"
        >
          <template v-if="loading"><LoadingOutlined /> 处理中…</template>
          <template v-else>开始职事化</template>
        </a-button>
        <a-button class="secondary-btn clear-btn" :disabled="loading" @click="clearAll">
          清空
        </a-button>
      </div>

      <div v-if="loading" class="loading-hint">
        <a-spin size="small" />
        <span>职事化处理中，请稍候…（约 10～20 秒）</span>
      </div>

      <a-alert v-if="error" type="error" :message="error" show-icon class="err-alert" />
    </a-card>

    <div v-if="results.length > 0" class="results-section">
      <div class="filter-bar">
        <button
          type="button"
          class="filter-btn"
          :class="{ active: statusFilter === 'all' }"
          @click="statusFilter = 'all'"
        >
          全部 {{ results.length }}
        </button>
        <button
          type="button"
          class="filter-btn filter-original"
          :class="{ active: statusFilter === 'original' }"
          @click="statusFilter = 'original'"
        >
          原文 {{ statusCount.original }}
        </button>
        <button
          type="button"
          class="filter-btn filter-minor"
          :class="{ active: statusFilter === 'minor' }"
          @click="statusFilter = 'minor'"
        >
          微调 {{ statusCount.minor }}
        </button>
        <button
          type="button"
          class="filter-btn filter-replaced"
          :class="{ active: statusFilter === 'replaced' }"
          @click="statusFilter = 'replaced'"
        >
          替换 {{ statusCount.replaced }}
        </button>
        <button
          type="button"
          class="filter-btn filter-manual"
          :class="{ active: statusFilter === 'manual' }"
          @click="statusFilter = 'manual'"
        >
          需人工 {{ statusCount.manual }}
        </button>
      </div>

      <div class="result-list">
        <a-card
          v-for="(item, idx) in filteredResults"
          :key="idx"
          size="small"
          class="result-card"
          :class="{ 'result-card-manual': item.status === 'manual' }"
        >
          <div class="result-row">
            <span
              class="status-tag"
              :style="{
                color: statusTag[item.status]?.color || '#666',
                background: statusTag[item.status]?.bg || '#f5f5f5',
              }"
            >
              {{ statusTag[item.status]?.label || item.status }}
            </span>
          </div>

          <div class="result-row">
            <label class="row-label" :class="{ 'label-manual': item.status === 'manual' }">
              {{ item.status === "manual" ? "原句（请人工修改）" : "原句" }}
            </label>
            <textarea
              v-model="item.original"
              class="result-textarea auto-grow"
              rows="1"
              @input="onInputGrow"
            />
          </div>

          <div class="result-row">
            <template v-if="item.status === 'minor'">
              <label class="row-label">职事化结果（点击编辑）</label>
              <div
                v-if="editingMinorKey !== item._key"
                class="result-diff-box"
                @click="startMinorEdit(item)"
              >
                <template v-for="(part, di) in diffParts(item)" :key="di">
                  <span v-if="part.added" class="diff-added">{{ part.value }}</span>
                  <span v-else-if="part.removed" class="diff-removed">{{ part.value }}</span>
                  <span v-else class="diff-equal">{{ part.value }}</span>
                </template>
              </div>
              <textarea
                v-else
                v-model="item.result"
                class="result-textarea auto-grow"
                rows="1"
                :data-minor-edit="item._key"
                @input="onInputGrow"
                @blur="endMinorEdit"
              />
            </template>
            <template v-else>
              <label class="row-label" :class="{ 'label-manual': item.status === 'manual' }">
                {{ item.status === "manual" ? "职事化结果（请人工修改）" : "职事化结果（可编辑）" }}
              </label>
              <textarea
                v-model="item.result"
                class="result-textarea auto-grow"
                rows="1"
                :placeholder="
                  item.status === 'manual'
                    ? '找不到合适替换，请在此输入人工修改后的内容'
                    : undefined
                "
                @input="onInputGrow"
              />
            </template>
          </div>

          <div v-if="showSource(item)" class="source-line">
            出处：{{ item.source }}
          </div>
        </a-card>
      </div>

      <div class="bottom-actions">
        <a-button class="secondary-btn copy-all-btn" @click="copyAllResults">
          {{ copied ? "已复制" : "复制全部结果" }}
        </a-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ministerialize-wrap {
  padding: 1em;
  max-width: 1200px;
  margin: 0 auto;
  color: #085041;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border-radius: 6px;
  background: #e1f5ee;
  border: 1px solid #a8e6cf;
  color: #1d9e75;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.back-btn:hover {
  background: #c8ebe0;
  border-color: #7ecdb0;
  color: #085041;
}

.page-title {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  color: #085041;
}

.page-tag {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 12px;
  background: #e1f5ee;
  color: #1d9e75;
  border: 1px solid #a8e6cf;
}

.input-card {
  background: #fafdfb;
  border-color: #c8ebe0;
}

.header-fields {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.header-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.field-label {
  flex: 0 0 4em;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 6px;
  text-align: center;
  font-size: 13px;
}

.lbl-series {
  color: #085041;
  background: #e1f5ee;
}

.lbl-topic {
  color: #1d4e89;
  background: #e6f4ff;
}

.lbl-chapter {
  color: #613400;
  background: #fff7e6;
}

.lbl-reading {
  color: #531dab;
  background: #f9f0ff;
}

.header-row :deep(.ant-input) {
  flex: 1;
}

.header-hint {
  margin: 8px 0 12px;
  font-size: 12px;
  color: #5a9e8f;
}

.textarea-wrap {
  position: relative;
}

.line-count {
  position: absolute;
  top: 8px;
  right: 12px;
  font-size: 12px;
  color: #1d9e75;
  z-index: 1;
  background: rgba(225, 245, 238, 0.9);
  padding: 2px 8px;
  border-radius: 4px;
}

.outline-input {
  width: 100%;
  min-height: 50vh;
  max-height: 66vh;
  padding: 12px 14px;
  padding-top: 32px;
  font-size: 14px;
  line-height: 1.6;
  border: 1px solid #b8e0d2;
  border-radius: 6px;
  resize: none;
  overflow: hidden;
  font-family: inherit;
  color: #085041;
  background: #fff;
  box-sizing: border-box;
}

.outline-input:focus {
  outline: none;
  border-color: #1d9e75;
  box-shadow: 0 0 0 2px rgba(29, 158, 117, 0.15);
}

.outline-input:disabled {
  background: #f5f5f5;
  cursor: not-allowed;
}

.limit-warn {
  margin: 8px 0 0;
  color: #f5222d;
  font-size: 13px;
}

.actions {
  margin-top: 16px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.primary-btn {
  background: #1d9e75;
  border-color: #1d9e75;
}

.primary-btn:hover:not(:disabled) {
  background: #178f6a !important;
  border-color: #178f6a !important;
}

.primary-btn:disabled {
  background: #a8d5c8;
  border-color: #a8d5c8;
  color: #fff;
}

.secondary-btn {
  background: #e1f5ee !important;
  border-color: #a8e6cf !important;
  color: #085041 !important;
}

.secondary-btn:hover:not(:disabled) {
  background: #c8ebe0 !important;
  border-color: #7ecdb0 !important;
  color: #085041 !important;
}

.clear-btn {
  background: #fff7e6 !important;
  border-color: #ffd591 !important;
  color: #613400 !important;
}

.clear-btn:hover:not(:disabled) {
  background: #ffe7ba !important;
  border-color: #ffc53d !important;
}

.copy-all-btn {
  background: #e6f7ff !important;
  border-color: #91d5ff !important;
  color: #0958d9 !important;
}

.copy-all-btn:hover:not(:disabled) {
  background: #bae7ff !important;
  border-color: #69c0ff !important;
}

.loading-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  color: #1d9e75;
  font-size: 13px;
}

.err-alert {
  margin-top: 12px;
}

.results-section {
  margin-top: 20px;
}

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 12px;
  background: #e1f5ee;
  border-radius: 6px;
  margin-bottom: 12px;
}

.filter-btn {
  padding: 4px 12px;
  border-radius: 6px;
  border: 1px solid #b8e0d2;
  background: #fff;
  color: #085041;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.filter-btn:hover {
  border-color: #1d9e75;
}

.filter-btn.active {
  background: #085041;
  border-color: #085041;
  color: #fff;
  font-weight: 600;
}

.filter-original:not(.active) {
  color: #389e0d;
  border-color: #b7eb8f;
  background: #f6ffed;
}

.filter-minor:not(.active) {
  color: #d48806;
  border-color: #ffe58f;
  background: #fffbe6;
}

.filter-replaced:not(.active) {
  color: #096dd9;
  border-color: #91caff;
  background: #e6f4ff;
}

.filter-manual:not(.active) {
  color: #cf1322;
  border-color: #ffa39e;
  background: #fff1f0;
}

.result-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.result-card {
  border-color: #d4ede4;
}

.result-card-manual {
  background: #fff1f0;
  border-color: #ffccc7;
}

.result-row {
  margin-bottom: 10px;
}

.result-row:last-child {
  margin-bottom: 0;
}

.status-tag {
  display: inline-block;
  padding: 2px 12px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 500;
}

.row-label {
  display: block;
  font-size: 13px;
  color: #085041;
  margin-bottom: 4px;
  font-weight: 500;
}

.label-manual {
  color: #f5222d;
}

.result-textarea {
  width: 100%;
  padding: 6px 10px;
  font-size: 14px;
  line-height: 1.6;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  resize: none;
  overflow: hidden;
  font-family: inherit;
  color: #333;
  background: #fff;
  box-sizing: border-box;
}

.result-textarea:focus {
  outline: none;
  border-color: #1d9e75;
  box-shadow: 0 0 0 2px rgba(29, 158, 117, 0.12);
}

.result-card-manual .result-textarea {
  border-color: #ffccc7;
}

.result-diff-box {
  width: 100%;
  padding: 6px 10px;
  font-size: 14px;
  line-height: 1.6;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  background: #fff;
  word-break: break-word;
  white-space: pre-wrap;
  box-sizing: border-box;
  cursor: pointer;
  min-height: 32px;
}

.result-diff-box:hover {
  border-color: #1d9e75;
  box-shadow: 0 0 0 2px rgba(29, 158, 117, 0.12);
}

.diff-added {
  background: #e1f5ee;
  color: #085041;
}

.diff-removed {
  color: #f5222d;
  text-decoration: line-through;
}

.diff-equal {
  color: #666;
}

.source-line {
  margin-top: 6px;
  font-size: 12px;
  color: #1d9e75;
}

.bottom-actions {
  margin-top: 16px;
}
</style>

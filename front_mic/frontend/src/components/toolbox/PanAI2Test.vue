<script setup>
import ToolsHeader from "./ToolsHeader.vue";
import { ref, computed } from "vue";
import { LoadingOutlined, CopyOutlined } from "@ant-design/icons-vue";

const NATURE_OPTIONS = ["一般性", "真理启示", "生命经历", "应用实行"];

const query = ref("");
const outlineNature = ref("");
const burdenDescription = ref("");

const loading = ref(false);
const error = ref(null);
const answer = ref(null);
const chunksUsed = ref(0);
const chunks = ref([]);
const showChunks = ref(false);
const copied = ref(false);
const downloading = ref(false);

const canGenerate = computed(
  () => !!query.value.trim() && !!outlineNature.value && !loading.value
);

function selectNature(nature) {
  outlineNature.value = nature;
}

async function generate() {
  if (!query.value.trim() || !outlineNature.value) return;
  loading.value = true;
  error.value = null;
  answer.value = null;
  chunksUsed.value = 0;
  chunks.value = [];
  showChunks.value = false;
  try {
    const res = await fetch("/api/panai2/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query.value,
        outline_nature: outlineNature.value,
        burden_description: burdenDescription.value,
      }),
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      let detail = errorData.detail;
      if (Array.isArray(detail)) {
        detail = detail.map((x) => x?.msg || JSON.stringify(x)).join("；");
      }
      error.value = detail || errorData.error || "生成失败，请稍后重试";
      return;
    }
    const data = await res.json();
    answer.value = data.answer;
    chunksUsed.value = data.chunks_used || 0;
    chunks.value = data.chunks || [];
  } catch (err) {
    error.value = (err && err.message) || "网络错误，请稍后重试";
  } finally {
    loading.value = false;
  }
}

function copyAnswer() {
  if (!answer.value) return;
  navigator.clipboard.writeText(answer.value).then(() => {
    copied.value = true;
    setTimeout(() => {
      copied.value = false;
    }, 2000);
  });
}

function parseFilename(disposition, fallback) {
  if (!disposition) return fallback;
  const m = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (m && m[1]) {
    try {
      return decodeURIComponent(m[1]);
    } catch (e) {
      return fallback;
    }
  }
  const m2 = /filename="?([^";]+)"?/i.exec(disposition);
  return m2 && m2[1] ? m2[1] : fallback;
}

async function downloadFormat() {
  const text = answer.value;
  if (!text || downloading.value) return;
  downloading.value = true;
  try {
    const res = await fetch("/api/testb/format/zh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error("下载失败");
    const filename = parseFilename(
      res.headers.get("Content-Disposition"),
      "纲目.docx"
    );
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (e) {
    alert("下载失败，请重试");
  } finally {
    downloading.value = false;
  }
}
</script>

<template>
  <ToolsHeader title="AI 纲目制作" />
  <div class="box">
    <a-card>
      <p class="hint">
        输入纲目主题、选择纲目性质（可填负担说明），点击「生成纲目」即可。
      </p>
      <a-divider :style="{ margin: '12px 0' }" />

      <div class="field">
        <span class="label">主题：</span>
        <input
          v-model="query"
          type="text"
          class="query-input"
          placeholder="输入纲目主题"
          :disabled="loading"
        />
      </div>

      <div class="field">
        <span class="label">纲目性质：</span>
        <div class="nature-row">
          <button
            v-for="n in NATURE_OPTIONS"
            :key="n"
            type="button"
            class="nature-btn"
            :class="{ active: outlineNature === n }"
            :disabled="loading"
            @click="selectNature(n)"
          >
            {{ n }}
          </button>
        </div>
      </div>

      <div class="field field-col">
        <span class="label">负担说明：</span>
        <textarea
          v-model="burdenDescription"
          class="burden-area"
          placeholder="可选"
          rows="4"
          :disabled="loading"
        />
      </div>

      <div class="action-row">
        <button
          type="button"
          class="action-btn"
          :disabled="!canGenerate"
          @click="generate"
        >
          <LoadingOutlined v-if="loading" class="btn-icon btn-spin" />
          <span v-if="loading">生成中...</span>
          <span v-else>生成纲目</span>
        </button>
      </div>
      <p v-if="loading" class="loading-hint">请耐心等待 1～2 分钟</p>
    </a-card>

    <div v-if="error" class="error">{{ error }}</div>

    <a-card v-if="answer" class="result-card">
      <template #title>
        <span>参考了 {{ chunksUsed }} 条段落</span>
        <div class="result-head-actions">
          <button type="button" class="copy-btn" @click="copyAnswer">
            <CopyOutlined /> {{ copied ? "已复制" : "复制" }}
          </button>
          <button type="button" class="format-btn"
            :disabled="downloading" @click="downloadFormat">
            <LoadingOutlined v-if="downloading" class="btn-spin" />
            {{ downloading ? "下载中…" : "⬇ 刷格式下载" }}
          </button>
        </div>
      </template>
      <pre class="result-body">{{ answer }}</pre>

      <div v-if="chunks.length" class="chunks-section">
        <div class="chunks-head" @click="showChunks = !showChunks">
          <span>检索段落（共 {{ chunksUsed }} 条）</span>
          <button type="button" class="toggle-btn">
            {{ showChunks ? "收起" : "展开" }}
          </button>
        </div>
        <div v-if="showChunks" class="chunks-list">
          <div v-for="(c, idx) in chunks" :key="idx" class="chunk-item">
            <div class="chunk-meta">
              [{{ c.chunk_id }}] {{ c.book_title }}
              <template v-if="c.message_number">第{{ c.message_number }}篇</template>
              <template v-if="c.message_title"> {{ c.message_title }}</template>
            </div>
            <div class="chunk-text">{{ c.text }}</div>
          </div>
        </div>
      </div>
    </a-card>
  </div>
</template>

<style scoped>
.box {
  padding: 1em;
  max-width: 720px;
  margin: 0 auto;
}

.box :deep(.ant-card) {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.06);
}

.hint {
  color: #555;
  margin: 0;
  font-size: 0.95em;
  line-height: 1.5;
}

.field {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.field-col {
  align-items: flex-start;
}

.field .label {
  font-weight: 600;
  color: #333;
  font-size: 1em;
  flex-shrink: 0;
}

.query-input {
  flex: 1;
  min-width: 220px;
  padding: 8px 12px;
  font-size: 15px;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  outline: none;
}
.query-input:focus {
  border-color: #1890ff;
}
.query-input:disabled {
  background: #fafafa;
  cursor: not-allowed;
}

.nature-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.nature-btn {
  padding: 8px 20px;
  font-weight: 500;
  font-size: 15px;
  border: 2px solid #d9d9d9;
  border-radius: 6px;
  background: #fafafa;
  cursor: pointer;
}
.nature-btn:hover:not(:disabled) {
  border-color: #52c41a;
  color: #389e0d;
}
.nature-btn.active {
  background: #52c41a;
  border-color: #52c41a;
  color: #fff;
}
.nature-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.burden-area {
  flex: 1;
  min-width: 100%;
  box-sizing: border-box;
  padding: 10px;
  font-family: inherit;
  font-size: 14px;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  resize: vertical;
  outline: none;
}
.burden-area:focus {
  border-color: #1890ff;
}
.burden-area:disabled {
  background: #fafafa;
  cursor: not-allowed;
}

.action-row {
  margin-top: 4px;
  padding: 12px 0;
  border-top: 1px solid #f0f0f0;
  display: flex;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 24px;
  font-size: 16px;
  border-radius: 6px;
  border: none;
  background: #1890ff;
  color: #fff;
  cursor: pointer;
}
.action-btn .btn-icon {
  font-size: 18px;
}
.action-btn .btn-spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.action-btn:hover:not(:disabled) {
  background: #40a9ff;
}
.action-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.loading-hint {
  margin: 8px 0 0;
  color: #8c8c8c;
  font-size: 0.9em;
  text-align: center;
}

.error {
  margin-top: 12px;
  color: #cf1322;
  font-size: 0.95em;
}

.result-card {
  margin-top: 20px;
}

.result-card :deep(.ant-card-head) {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}

.result-head-actions {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.copy-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: 13px;
  border-radius: 4px;
  border: 1px solid #d9d9d9;
  background: #fff;
  cursor: pointer;
  color: #555;
}
.copy-btn:hover {
  color: #1890ff;
  border-color: #1890ff;
}

.format-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: 13px;
  border-radius: 4px;
  border: 1px solid #52c41a;
  background: #fff;
  color: #389e0d;
  cursor: pointer;
}
.format-btn:hover:not(:disabled) {
  background: #52c41a;
  color: #fff;
}
.format-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.result-body {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-size: 0.95em;
  line-height: 1.6;
  max-height: 60vh;
  overflow-y: auto;
  tab-size: 4;
  -moz-tab-size: 4;
}

.chunks-section {
  margin-top: 16px;
  border-top: 1px solid #f0f0f0;
  padding-top: 12px;
}
.chunks-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  font-weight: 600;
  color: #333;
}
.toggle-btn {
  padding: 4px 12px;
  font-size: 13px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: #fff;
  color: #555;
  cursor: pointer;
}
.toggle-btn:hover {
  color: #1890ff;
  border-color: #1890ff;
}
.chunks-list {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
}
.chunk-item {
  padding: 10px 0;
  border-bottom: 1px solid #f0f0f0;
}
.chunk-item:last-child {
  border-bottom: none;
}
.chunk-meta {
  color: #555;
  font-size: 0.82em;
  font-weight: 700;
  margin-bottom: 6px;
  padding: 4px 8px;
  background: #e6f4ff;
  border-radius: 4px;
  display: inline-block;
}
.chunk-text {
  color: #333;
  font-size: 0.92em;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>

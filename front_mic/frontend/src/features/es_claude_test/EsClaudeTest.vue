<script setup>
import { reactive, ref } from "vue";
import { message } from "ant-design-vue";
import { LoadingOutlined } from "@ant-design/icons-vue";
import ToolsHeader from "@/components/toolbox/ToolsHeader.vue";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";

const keyword = ref("");
const keywords = ref([]);
const newKeyword = ref("");

const isExpanding = ref(false);
const isSearching = ref(false);
const isGenerating = ref(false);

const expandDone = ref(false);
const searchDone = ref(false);
const generateDone = ref(false);

const searchResult = ref(null);
const generateResult = ref(null);
const errorMsg = ref("");

const stageOrder = ["nee", "lee_1", "lee_2", "lee_3", "lee_4", "lee_peak"];
const openStages = reactive({
  nee: false,
  lee_1: false,
  lee_2: false,
  lee_3: false,
  lee_4: false,
  lee_peak: false,
});

function authHeaders(json = true) {
  const token = localStorage.getItem("token");
  if (!token) {
    window.location.hash = "/login";
    return null;
  }
  const h = { Authorization: `Bearer ${token}` };
  if (json) h["Content-Type"] = "application/json";
  return h;
}

function parseApiError(res, data) {
  let detail = data?.detail;
  if (Array.isArray(detail)) {
    detail = detail.map((x) => x?.msg || x?.message || JSON.stringify(x)).join("；");
  }
  return detail || data?.error || data?.message || `请求失败（${res.status}）`;
}

function toggleStage(key) {
  openStages[key] = !openStages[key];
}

function addKeyword() {
  const kw = newKeyword.value.trim();
  if (kw && !keywords.value.includes(kw)) {
    keywords.value.push(kw);
  }
  newKeyword.value = "";
}

function removeKeyword(i) {
  keywords.value.splice(i, 1);
}

function doReset() {
  keyword.value = "";
  keywords.value = [];
  newKeyword.value = "";
  expandDone.value = false;
  searchDone.value = false;
  generateDone.value = false;
  searchResult.value = null;
  generateResult.value = null;
  errorMsg.value = "";
  Object.keys(openStages).forEach((k) => {
    openStages[k] = false;
  });
}

async function doExpand() {
  const kw = keyword.value.trim();
  if (!kw || isExpanding.value) return;
  const headers = authHeaders();
  if (!headers) return;

  isExpanding.value = true;
  errorMsg.value = "";
  searchDone.value = false;
  generateDone.value = false;
  searchResult.value = null;
  generateResult.value = null;

  try {
    const res = await fetch(`${apiBase}/api/es_claude_test/expand`, {
      method: "POST",
      headers,
      body: JSON.stringify({ keyword: kw }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(parseApiError(res, data));
    const list = Array.isArray(data.keywords) ? [...data.keywords] : [];
    if (!list.includes(kw)) list.unshift(kw);
    keywords.value = list;
    expandDone.value = true;
  } catch (e) {
    errorMsg.value = "生成同义词失败：" + e.message;
  } finally {
    isExpanding.value = false;
  }
}

async function doSearch() {
  if (!keywords.value.length || isSearching.value) return;
  const headers = authHeaders();
  if (!headers) return;

  isSearching.value = true;
  errorMsg.value = "";
  searchDone.value = false;
  generateDone.value = false;
  generateResult.value = null;
  Object.keys(openStages).forEach((k) => {
    openStages[k] = false;
  });

  try {
    const res = await fetch(`${apiBase}/api/es_claude_test/search`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        keyword: keyword.value.trim(),
        keywords: keywords.value,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(parseApiError(res, data));
    searchResult.value = data;
    searchDone.value = true;
  } catch (e) {
    errorMsg.value = "检索失败：" + e.message;
  } finally {
    isSearching.value = false;
  }
}

async function doGenerate() {
  if (!searchResult.value || isGenerating.value) return;
  const headers = authHeaders();
  if (!headers) return;

  isGenerating.value = true;
  generateDone.value = false;
  errorMsg.value = "";
  generateResult.value = {
    concise: { text: "", error: null },
    rich: { text: "", error: null },
    total_input_tokens: 0,
    total_output_tokens: 0,
    estimated_cost_usd: 0,
  };

  try {
    const res = await fetch(`${apiBase}/api/es_claude_test/generate`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        keyword: keyword.value.trim(),
        stages: searchResult.value.stages,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(parseApiError(res, data));
    generateResult.value = data;
    generateDone.value = true;
  } catch (e) {
    errorMsg.value = "生成文章失败：" + e.message;
    generateResult.value = null;
  } finally {
    isGenerating.value = false;
  }
}

async function doCopy(version) {
  const text = generateResult.value?.[version]?.text;
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    message.success("已复制");
  } catch {
    message.error("复制失败");
  }
}

async function doDownload(version) {
  const text = generateResult.value?.[version]?.text;
  if (!text) return;
  const headers = authHeaders();
  if (!headers) return;

  try {
    const res = await fetch(`${apiBase}/api/es_claude_test/download`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        keyword: keyword.value.trim(),
        text,
        version,
      }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(parseApiError(res, data));
    }
    const blob = await res.blob();
    const suffix = version === "concise" ? "精简版" : "丰富版";
    let filename = `${keyword.value.trim()}_进展_${suffix}.docx`;
    const disp = res.headers.get("Content-Disposition") || "";
    const m = disp.match(/filename\*=UTF-8''(.+)/i) || disp.match(/filename="([^"]+)"/i);
    if (m) filename = decodeURIComponent(m[1]);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    errorMsg.value = "下载失败：" + e.message;
  }
}
</script>

<template>
  <div class="es-claude-test">
    <ToolsHeader title="ES + Claude 测试" />
    <div class="box">
      <a-card class="section-card">
        <div class="label">主题关键词</div>
        <a-textarea
          v-model:value="keyword"
          :auto-size="{ minRows: 1, maxRows: 3 }"
          placeholder="例：神的经纶、基督的身体、圣灵"
          class="content-area"
          :disabled="isExpanding || isSearching || isGenerating"
        />
        <div class="action-row">
          <button
            type="button"
            class="action-btn"
            :disabled="!keyword.trim() || isExpanding || isSearching || isGenerating"
            @click="doExpand"
          >
            {{ isExpanding ? "生成中…" : "生成同义词" }}
          </button>
          <button type="button" class="clear-btn" @click="doReset">清空</button>
        </div>

        <template v-if="expandDone">
          <a-divider />
          <div class="label">
            同义词 / 相关词
            <span class="label-hint">（可增删编辑，回车添加）</span>
          </div>
          <div class="tag-editor">
            <span v-for="(kw, i) in keywords" :key="i" class="keyword-tag">
              {{ kw }}
              <span class="remove" @click="removeKeyword(i)">×</span>
            </span>
            <input
              v-model="newKeyword"
              class="tag-input"
              placeholder="输入后回车添加"
              @keydown.enter.prevent="addKeyword"
            />
          </div>
          <div class="action-row" style="margin-top: 12px">
            <button
              type="button"
              class="action-btn"
              :disabled="keywords.length === 0 || isSearching || isGenerating"
              @click="doSearch"
            >
              {{ isSearching ? "检索中…" : "开始检索" }}
            </button>
          </div>
        </template>
      </a-card>

      <a-card v-if="searchDone && searchResult" class="section-card">
        <div class="stats-row">
          共检索 <b>{{ searchResult.total_retrieved }}</b> 条， 去重后
          <b>{{ searchResult.total_deduped }}</b> 条， Rerank 保留
          <b>{{ searchResult.total_reranked }}</b> 条
        </div>
        <div class="stage-stats">
          <span
            v-for="stageKey in stageOrder"
            :key="stageKey"
            :class="[
              'stage-tag',
              searchResult.stages[stageKey].count > 0 ? 'has-data' : 'no-data',
            ]"
          >
            {{ searchResult.stages[stageKey].label }}
            （{{ searchResult.stages[stageKey].count }} 条）
          </span>
        </div>

        <div class="stage-list">
          <template v-for="stageKey in stageOrder" :key="stageKey">
            <div
              v-if="searchResult.stages[stageKey].count > 0"
              class="collapse-item"
            >
              <div class="collapse-head" @click="toggleStage(stageKey)">
                <span>{{ searchResult.stages[stageKey].label }}</span>
                <span class="collapse-arrow">{{ openStages[stageKey] ? "▲" : "▼" }}</span>
              </div>
              <div v-if="openStages[stageKey]" class="collapse-body">
                <div
                  v-for="(doc, di) in searchResult.stages[stageKey].docs"
                  :key="di"
                  class="doc-item"
                >
                  <div class="doc-text">{{ doc.text }}</div>
                  <div class="doc-source">{{ doc.source_zh }}</div>
                </div>
              </div>
            </div>
          </template>
        </div>

        <div class="action-row" style="margin-top: 12px">
          <button
            type="button"
            class="action-btn"
            :disabled="isGenerating"
            @click="doGenerate"
          >
            {{ isGenerating ? "生成中…" : "生成文章" }}
          </button>
        </div>
      </a-card>

      <div v-if="generateDone || isGenerating" class="result-columns">
        <a-card class="result-card">
          <div class="result-title-row">
            <span>精简版</span>
            <div class="result-actions">
              <button
                type="button"
                class="copy-btn"
                :disabled="!generateResult?.concise?.text"
                @click="doCopy('concise')"
              >
                复制
              </button>
              <button
                type="button"
                class="download-btn"
                :disabled="!generateResult?.concise?.text"
                @click="doDownload('concise')"
              >
                下载 DOCX
              </button>
            </div>
          </div>
          <div v-if="!isGenerating" class="result-scroll">
            <div v-if="generateResult?.concise?.error" class="panel-error">
              {{ generateResult.concise.error }}
            </div>
            <template v-else>{{ generateResult?.concise?.text }}</template>
          </div>
          <div v-else class="panel-loading">
            <LoadingOutlined class="btn-spin" /> 生成中…
          </div>
        </a-card>

        <a-card class="result-card">
          <div class="result-title-row">
            <span>丰富版</span>
            <div class="result-actions">
              <button
                type="button"
                class="copy-btn"
                :disabled="!generateResult?.rich?.text"
                @click="doCopy('rich')"
              >
                复制
              </button>
              <button
                type="button"
                class="download-btn"
                :disabled="!generateResult?.rich?.text"
                @click="doDownload('rich')"
              >
                下载 DOCX
              </button>
            </div>
          </div>
          <div v-if="!isGenerating" class="result-scroll">
            <div v-if="generateResult?.rich?.error" class="panel-error">
              {{ generateResult.rich.error }}
            </div>
            <template v-else>{{ generateResult?.rich?.text }}</template>
          </div>
          <div v-else class="panel-loading">
            <LoadingOutlined class="btn-spin" /> 生成中…
          </div>
        </a-card>
      </div>

      <div v-if="generateDone && generateResult" class="gen-cost">
        总 token：输入 {{ generateResult.total_input_tokens }} / 输出
        {{ generateResult.total_output_tokens }} ｜估算费用：${{
          generateResult.estimated_cost_usd
        }}
      </div>

      <a-alert
        v-if="errorMsg"
        type="error"
        :message="errorMsg"
        class="error-alert"
        show-icon
        closable
        @close="errorMsg = ''"
      />
    </div>
  </div>
</template>

<style scoped>
.es-claude-test {
  min-height: 100vh;
  background: #f5f6fa;
}

.box {
  max-width: 960px;
  margin: 0 auto;
  padding: 0 16px 32px;
}

.box :deep(.ant-card) {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.06);
}

.section-card {
  margin-bottom: 16px;
}

.label {
  font-size: 13px;
  color: #666;
  margin-bottom: 8px;
}

.label-hint {
  color: #999;
  font-size: 12px;
  font-weight: normal;
}

.content-area :deep(.ant-input) {
  border-radius: 8px;
  font-family: inherit;
  font-size: 0.95em;
  line-height: 1.6;
}

.tag-editor {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  padding: 10px;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  background: #fafafa;
  min-height: 44px;
}

.keyword-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: #e6f4ff;
  color: #1677ff;
  border: 1px solid #91caff;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 13px;
}

.keyword-tag .remove {
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  color: #999;
}

.keyword-tag .remove:hover {
  color: #ff4d4f;
}

.tag-input {
  flex: 1;
  min-width: 120px;
  border: none;
  outline: none;
  background: transparent;
  font-size: 14px;
  padding: 4px;
}

.stats-row {
  font-size: 14px;
  color: #444;
  margin-bottom: 12px;
}

.stage-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.stage-tag {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 4px;
  border: 1px solid #d9d9d9;
}

.stage-tag.has-data {
  background: #f6ffed;
  border-color: #b7eb8f;
  color: #389e0d;
}

.stage-tag.no-data {
  background: #fafafa;
  color: #bbb;
}

.stage-list {
  margin-top: 8px;
}

.collapse-item {
  border-bottom: 1px solid #f0f0f0;
}

.collapse-head {
  padding: 10px 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  color: #444;
}

.collapse-head:hover {
  background: #f5f5f5;
}

.collapse-arrow {
  color: #999;
  font-size: 12px;
}

.collapse-body {
  padding: 0 8px 12px 20px;
  font-size: 13px;
  line-height: 1.8;
}

.doc-item {
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px dashed #f0f0f0;
}

.doc-item:last-child {
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}

.doc-text {
  white-space: pre-wrap;
  color: #333;
  margin-bottom: 4px;
}

.doc-source {
  font-size: 12px;
  color: #888;
}

.result-columns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 12px;
}

.result-card {
  margin-bottom: 0;
}

.result-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  font-weight: 600;
  margin-bottom: 12px;
}

.result-actions {
  display: flex;
  gap: 8px;
}

.result-scroll {
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 16px;
  max-height: 480px;
  overflow: auto;
  white-space: pre-wrap;
  font-size: 14px;
  line-height: 1.7;
}

.copy-btn,
.download-btn {
  background: #fff;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  padding: 4px 10px;
  font-size: 13px;
  color: #555;
  cursor: pointer;
  transition: all 0.2s;
}

.copy-btn:hover:not(:disabled),
.download-btn:hover:not(:disabled) {
  color: #1677ff;
  border-color: #1677ff;
}

.copy-btn:disabled,
.download-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.gen-cost {
  font-size: 13px;
  color: #1677ff;
  text-align: right;
  margin-bottom: 16px;
}

.action-row {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.action-btn {
  background: #1677ff;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 8px 20px;
  font-size: 14px;
  cursor: pointer;
}

.action-btn:hover:not(:disabled) {
  background: #4096ff;
}

.action-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.clear-btn {
  background: #fff;
  color: #666;
  border: 1px solid #d9d9d9;
  padding: 6px 16px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.clear-btn:hover {
  color: #ff4d4f;
  border-color: #ff4d4f;
  background: #fff1f0;
}

.panel-loading {
  color: #8c8c8c;
  padding: 24px 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.panel-error {
  color: #cf1322;
  padding: 8px 0;
  font-size: 0.95em;
}

.error-alert {
  margin-top: 8px;
}

.btn-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 600px) {
  .box {
    padding: 0 12px 24px;
  }

  .result-columns {
    grid-template-columns: 1fr;
  }

  .result-title-row {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
}
</style>

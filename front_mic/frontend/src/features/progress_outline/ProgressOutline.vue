<script setup>
import ToolsHeader from "@/components/toolbox/ToolsHeader.vue";
import { computed, onMounted, ref } from "vue";
import { DownloadOutlined } from "@ant-design/icons-vue";
import { toastError } from "@/components/utils/Dialog.js";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";

const stages = [
  { no: 1, short: "壹　倪柝声" },
  { no: 2, short: "贰　李 1932-1960" },
  { no: 3, short: "叁　李 1961-1973" },
  { no: 4, short: "肆　李 1974-1984" },
  { no: 5, short: "伍　李 1984-1990" },
  { no: 6, short: "陆　李 1990-1997" },
];

const tab = ref("pano");
const seriesList = ref([]);
const seriesListLoaded = ref(false);
const seriesNo = ref(null);
const loadingSeries = ref(false);
const term = ref("基督");
const topK = ref(80);
const searching = ref(false);
const activeStage = ref(null);
const articles = ref([]);
const items = ref([]);
const expanded = ref({});
const count = ref(0);
const estimatedTokens = ref(0);
const outputLength = ref(3000);
const plainText = ref("");
const sourceGroupLabel = ref("");
const statsVisible = ref(false);
const generatedText = ref("");
const genUsage = ref(null);
const generating = ref(false);
const formatting = ref(false);
const error = ref("");
const fileInput = ref(null);

const indentMap = {
  bible_reading: 0,
  ot1: 0,
  ot2: 1,
  ot3: 2,
  ot4: 3,
  ot5: 4,
  ot6: 4,
  ot7: 4,
};
const indentEm = (type) => `${(indentMap[type] ?? 1) * 1.5}em`;

const hasResults = computed(() =>
  tab.value === "pano" ? articles.value.length > 0 : items.value.length > 0
);

const showSeriesEmptyHint = computed(
  () =>
    tab.value === "pano" &&
    seriesListLoaded.value &&
    !loadingSeries.value &&
    seriesList.value.length === 0
);

const countLabel = computed(() =>
  tab.value === "pano" ? `共${count.value}篇` : `共${count.value}条`
);

const busy = computed(() => searching.value || generating.value || formatting.value);

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

function clearResults() {
  articles.value = [];
  items.value = [];
  expanded.value = {};
  count.value = 0;
  estimatedTokens.value = 0;
  plainText.value = "";
  sourceGroupLabel.value = "";
  statsVisible.value = false;
  generatedText.value = "";
  genUsage.value = null;
  activeStage.value = null;
  error.value = "";
}

function onTabChange(key) {
  if (generating.value) return;
  if (tab.value === key) return;
  tab.value = key;
  clearResults();
}

function toggle(idx) {
  expanded.value[idx] = !expanded.value[idx];
}

function applySearchResult(data) {
  if (tab.value === "pano") {
    articles.value = data.articles || [];
  } else {
    items.value = data.items || [];
  }
  count.value = data.count || 0;
  estimatedTokens.value = data.estimated_tokens || 0;
  outputLength.value = data.default_output_length || 3000;
  plainText.value = data.plain_text || "";
  sourceGroupLabel.value = data.source_group_label || "";
  statsVisible.value = true;
  expanded.value = {};
  generatedText.value = "";
  genUsage.value = null;
}

function formatCost(v) {
  return Number(v || 0).toFixed(4);
}

onMounted(async () => {
  const headers = authHeaders();
  if (!headers) return;
  loadingSeries.value = true;
  try {
    const res = await fetch(`${apiBase}/api/progress/series-list`, { headers });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(parseApiError(res, data));
    seriesList.value = data.series || [];
    seriesListLoaded.value = true;
    if (seriesList.value.length) {
      seriesNo.value = seriesList.value[0].series_no;
    }
  } catch (e) {
    error.value = "加载系列列表失败：" + e.message;
    toastError(error.value);
  } finally {
    loadingSeries.value = false;
  }
});

async function onStageClick(stageNo) {
  if (tab.value === "pano") {
    if (seriesNo.value == null) {
      error.value = "请先选择系列编号";
      return;
    }
  } else if (!term.value.trim()) {
    error.value = "请输入词条名称";
    return;
  }

  const headers = authHeaders();
  if (!headers) return;

  error.value = "";
  searching.value = true;
  activeStage.value = stageNo;

  try {
    const url =
      tab.value === "pano"
        ? `${apiBase}/api/progress/pano/search`
        : `${apiBase}/api/progress/entry/search`;
    const body =
      tab.value === "pano"
        ? { series_no: seriesNo.value, source_group_no: stageNo }
        : { term: term.value.trim(), source_group_no: stageNo, top_k: topK.value };

    const res = await fetch(url, { method: "POST", headers, body: JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(parseApiError(res, data));
    applySearchResult(data);
  } catch (e) {
    error.value = "检索失败：" + e.message;
    toastError(error.value);
  } finally {
    searching.value = false;
  }
}

function triggerUpload() {
  fileInput.value?.click();
}

async function onFileSelected(ev) {
  const file = ev.target.files?.[0];
  if (!file) return;
  const headers = authHeaders(false);
  if (!headers) return;

  error.value = "";
  searching.value = true;
  activeStage.value = "overview";

  try {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${apiBase}/api/progress/upload-text`, {
      method: "POST",
      headers,
      body: fd,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(parseApiError(res, data));

    articles.value = [];
    items.value = [];
    count.value = 0;
    estimatedTokens.value = data.estimated_tokens || 0;
    outputLength.value = data.default_output_length || 3000;
    plainText.value = data.text || "";
    sourceGroupLabel.value = "鸟瞰（上传文件）";
    statsVisible.value = true;
    generatedText.value = "";
    expanded.value = {};
  } catch (e) {
    error.value = "文件解析失败：" + e.message;
    toastError(error.value);
  } finally {
    searching.value = false;
    ev.target.value = "";
  }
}

async function generate(kind) {
  if (!plainText.value || generating.value) return;
  const headers = authHeaders();
  if (!headers) return;

  generating.value = true;
  generatedText.value = "";
  genUsage.value = null;

  const base =
    tab.value === "pano"
      ? `${apiBase}/api/progress/pano/generate`
      : `${apiBase}/api/progress/entry/generate`;
  const path = kind === "segment" ? `${base}/segment` : `${base}/overview`;

  try {
    const body = { content: plainText.value, output_length: outputLength.value };
    if (tab.value === "entry") body.term = term.value.trim();

    const res = await fetch(path, { method: "POST", headers, body: JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(parseApiError(res, data));
    generatedText.value = data.text || "";
    genUsage.value = data.usage || null;
  } catch (e) {
    error.value = "生成失败：" + e.message;
    toastError(error.value);
  } finally {
    generating.value = false;
  }
}

async function formatDownload() {
  if (!generatedText.value) return;
  const headers = authHeaders();
  if (!headers) return;

  formatting.value = true;
  try {
    const res = await fetch(`${apiBase}/api/progress/format_download`, {
      method: "POST",
      headers,
      body: JSON.stringify({ text: generatedText.value }),
    });
    if (!res.ok) throw new Error("下载失败");
    const blob = await res.blob();
    const disp = res.headers.get("Content-Disposition") || "";
    let filename = "纲目.docx";
    const m = disp.match(/filename\*=UTF-8''(.+)/i);
    if (m) filename = decodeURIComponent(m[1]);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    error.value = e.message;
    toastError(error.value);
  } finally {
    formatting.value = false;
  }
}
</script>

<template>
  <div class="progress-outline">
    <ToolsHeader title="主恢复的神圣启示进展" />

    <div class="box">
      <a-spin :spinning="busy">
        <a-tabs :active-key="tab" @change="onTabChange">
          <a-tab-pane key="pano" tab="进展75系列" />
          <a-tab-pane key="entry" tab="新增词条" />
        </a-tabs>

        <a-card class="section-card" :class="{ locked: generating }">
          <div class="input-row">
            <template v-if="tab === 'pano'">
              <div class="field">
                <span class="label">系列编号</span>
                <a-select
                  v-model:value="seriesNo"
                  :loading="loadingSeries"
                  :disabled="generating"
                  style="min-width: 280px"
                  placeholder="选择系列"
                >
                  <a-select-option
                    v-for="s in seriesList"
                    :key="s.series_no"
                    :value="s.series_no"
                  >
                    {{ s.series_no }} — {{ s.series_title }}
                  </a-select-option>
                </a-select>
              </div>
              <div v-if="showSeriesEmptyHint" class="series-empty-hint">
                系列数据暂不可用，请确认索引已导入
              </div>
            </template>
            <template v-else>
              <div class="field grow">
                <span class="label">词条名称</span>
                <a-input
                  v-model:value="term"
                  placeholder="输入词条"
                  :disabled="generating"
                  @press-enter="onStageClick(1)"
                />
              </div>
              <div class="field field-sm">
                <span class="label">top_k</span>
                <a-input-number
                  v-model:value="topK"
                  :min="1"
                  :max="200"
                  :disabled="generating"
                  style="width: 88px"
                />
              </div>
            </template>
          </div>

          <div class="stage-row">
            <a-button
              v-for="st in stages"
              :key="st.no"
              size="small"
              class="stage-btn"
              :type="activeStage === st.no ? 'primary' : 'default'"
              :disabled="searching || generating"
              @click="onStageClick(st.no)"
            >
              {{ st.short }}
            </a-button>
            <a-button
              size="small"
              class="stage-btn"
              :type="activeStage === 'overview' ? 'primary' : 'default'"
              :disabled="searching || generating"
              @click="triggerUpload"
            >
              鸟瞰
            </a-button>
            <input ref="fileInput" type="file" accept=".docx,.txt" hidden @change="onFileSelected" />
          </div>

          <div v-if="statsVisible" class="meta-row">
            <span class="token-text">Token: {{ estimatedTokens }}</span>
            <div class="field-inline">
              <span class="label">输出长度</span>
              <a-input-number
                v-model:value="outputLength"
                :min="500"
                :max="20000"
                :disabled="generating"
                style="width: 110px"
              />
            </div>
          </div>

          <div class="gen-row">
            <button
              type="button"
              class="action-btn"
              :disabled="!plainText || generating"
              @click="generate('segment')"
            >
              生成分段纲目
            </button>
            <button
              type="button"
              class="action-btn"
              :disabled="!plainText || generating"
              @click="generate('overview')"
            >
              生成鸟瞰纲目
            </button>
          </div>
        </a-card>

        <a-card v-if="generatedText || generating" class="section-card" title="生成结果">
          <template #extra>
            <span v-if="genUsage" class="gen-cost">
              约 ${{ formatCost(genUsage.cost_usd) }}
              （in {{ genUsage.input_tokens }} / out {{ genUsage.output_tokens }}）
            </span>
          </template>
          <div class="stream-box">
            <p v-if="generating" class="generating-hint">正在生成纲目，请稍候…</p>
            <pre v-else>{{ generatedText }}</pre>
          </div>
          <button
            type="button"
            class="action-btn download-btn"
            :disabled="!generatedText || generating || formatting"
            @click="formatDownload"
          >
            <DownloadOutlined /> 刷格式下载
          </button>
        </a-card>

        <a-card v-if="hasResults" class="section-card" :class="{ locked: generating }">
          <template #title>
            <span>检索结果</span>
            <a-tag class="count-tag">{{ countLabel }}</a-tag>
            <a-tag v-if="sourceGroupLabel" color="blue">{{ sourceGroupLabel }}</a-tag>
          </template>

          <template v-if="tab === 'pano'">
            <div v-for="(art, idx) in articles" :key="art.id || idx" class="collapse-item">
              <div class="collapse-head" @click="toggle(idx)">
                <span class="chevron" :class="{ open: expanded[idx] }">›</span>
                <span>{{ art.title || `第${art.article_no}篇` }}</span>
              </div>
              <div v-show="expanded[idx]" class="collapse-body">
                <div v-for="(line, li) in art.outline || []" :key="li" class="outline-line">
                  <span :style="{ paddingLeft: indentEm(line.type) }">{{ line.text }}</span>
                </div>
                <p v-for="(para, pi) in art.ministry_excerpt || []" :key="'m' + pi" class="excerpt">
                  {{ typeof para === "string" ? para : para.text }}
                </p>
              </div>
            </div>
          </template>

          <template v-else>
            <div v-for="(it, idx) in items" :key="it.chunk_id || idx" class="collapse-item">
              <div class="collapse-head" @click="toggle(idx)">
                <span class="chevron" :class="{ open: expanded[idx] }">›</span>
                <span>{{ it.source_zh || it.book_title || it.chunk_id }}</span>
              </div>
              <div v-show="expanded[idx]" class="collapse-body">
                <p class="detail-text">{{ it.text }}</p>
              </div>
            </div>
          </template>
        </a-card>

        <a-alert v-if="error" type="error" :message="error" show-icon class="error-alert" />
      </a-spin>
    </div>
  </div>
</template>

<style scoped>
.progress-outline {
  min-height: 100vh;
  background: #f5f6fa;
}

.box {
  max-width: 720px;
  margin: 0 auto;
  padding: 0 16px 32px;
}

.section-card {
  margin-bottom: 16px;
}

.section-card.locked {
  pointer-events: none;
  opacity: 0.55;
}

.input-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 16px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field.grow {
  flex: 1;
  min-width: 200px;
}

.field-sm {
  flex-shrink: 0;
}

.label {
  font-size: 13px;
  color: #666;
}

.stage-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.stage-btn {
  flex: 1;
  min-width: 0;
}

.meta-row {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.token-text {
  font-size: 13px;
  color: #888;
}

.field-inline {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gen-row {
  display: flex;
  gap: 12px;
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

.download-btn {
  margin-top: 12px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.gen-cost {
  font-size: 13px;
  color: #1677ff;
}

.stream-box {
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 16px;
  max-height: 400px;
  overflow: auto;
  line-height: 1.7;
}

.generating-hint {
  margin: 0;
  color: #1677ff;
  text-align: center;
  padding: 24px 0;
}

.stream-box pre {
  margin: 0;
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 14px;
}

.count-tag {
  margin-left: 8px;
}

.collapse-item {
  border-bottom: 1px solid #f0f0f0;
}

.collapse-head {
  padding: 10px 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #444;
}

.collapse-head:hover {
  background: #f5f5f5;
}

.chevron {
  transition: transform 0.2s;
  color: #999;
}

.chevron.open {
  transform: rotate(90deg);
}

.collapse-body {
  padding: 0 8px 12px 20px;
  font-size: 13px;
  line-height: 1.8;
}

.excerpt,
.detail-text {
  margin: 8px 0 0;
  white-space: pre-wrap;
}

.error-alert {
  margin-top: 8px;
}

.series-empty-hint {
  margin-top: 8px;
  padding: 0.65rem 0.85rem;
  background: #fffbe6;
  border: 1px solid #ffe58f;
  border-radius: 8px;
  color: #ad6800;
  font-size: 0.9em;
  line-height: 1.5;
}
</style>

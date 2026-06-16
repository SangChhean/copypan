<template>
  <div class="app-shell">
    <header class="navbar">
      <div class="layout-inner navbar-inner">主恢复的神圣启示进展</div>
    </header>

    <nav class="tabs">
      <div class="layout-inner tabs-inner">
        <button
          class="tab"
          :class="{ active: tab === 'pano' }"
          :disabled="generating"
          @click="switchTab('pano')"
        >
          进展75系列
        </button>
        <button
          class="tab"
          :class="{ active: tab === 'entry' }"
          :disabled="generating"
          @click="switchTab('entry')"
        >
          新增词条
        </button>
      </div>
    </nav>

    <main class="content">
      <!-- 输入区 -->
      <section class="card input-card layout-panel" :class="{ locked: generating }">
        <div class="input-row">
          <template v-if="tab === 'pano'">
            <label class="field">
              <span class="label series-label">系列编号</span>
              <select
                v-model.number="seriesNo"
                :disabled="loadingSeries || generating"
                class="input select"
              >
                <option v-for="s in seriesList" :key="s.series_no" :value="s.series_no">
                  {{ s.series_no }} — {{ s.series_title }}
                </option>
              </select>
            </label>
          </template>
          <template v-else>
            <label class="field">
              <span class="label">词条名称</span>
              <input
                v-model="term"
                type="text"
                class="input"
                placeholder="输入词条"
                :disabled="generating"
                @keydown.enter="onEnterSearch"
              />
            </label>
            <label class="field field-sm">
              <span class="label">top_k</span>
              <input
                v-model.number="topK"
                type="number"
                min="1"
                max="200"
                class="input input-topk"
                :disabled="generating"
              />
            </label>
          </template>
        </div>

        <div class="stage-row">
          <button
            v-for="st in stages"
            :key="st.no"
            class="stage-btn"
            :class="{ active: activeStage === st.no }"
            :disabled="searching || generating"
            @click="onStageClick(st.no)"
          >
            {{ st.short }}
          </button>
          <button
            class="stage-btn"
            :class="{ active: activeStage === 'overview' }"
            :disabled="searching || generating"
            @click="triggerUpload"
          >
            鸟瞰
          </button>
          <input ref="fileInput" type="file" accept=".docx,.txt" hidden @change="onFileSelected" />
        </div>

        <div v-if="statsVisible" class="meta-row">
          <span class="token-text">Token: {{ estimatedTokens }}</span>
          <label class="field-inline">
            <span class="label">输出长度</span>
            <input
              v-model.number="outputLength"
              type="number"
              min="500"
              max="20000"
              class="input input-outlen"
              :disabled="generating"
            />
          </label>
        </div>

        <div class="gen-row">
          <button class="btn-generate" :disabled="!plainText || generating" @click="generate('segment')">
            生成分段纲目
          </button>
          <button class="btn-generate" :disabled="!plainText || generating" @click="generate('overview')">
            生成鸟瞰纲目
          </button>
        </div>
      </section>

      <!-- 生成结果区 -->
      <section v-if="generatedText || generating" class="card result-card layout-panel">
        <h3 class="card-title result-card-title">
          <span>生成结果</span>
          <span v-if="genUsage" class="gen-cost">
            生成费用：约 ${{ formatCost(genUsage.cost_usd) }}
            <span class="gen-cost-detail">
              （输入 {{ genUsage.input_tokens }} / 输出 {{ genUsage.output_tokens }} tokens）
            </span>
          </span>
        </h3>
        <div class="stream-box">
          <p v-if="generating" class="generating-hint">正在生成纲目，请稍候…</p>
          <pre v-else>{{ generatedText }}</pre>
        </div>
        <button
          class="btn-download"
          :disabled="!generatedText || generating || formatting"
          @click="formatDownload"
        >
          刷格式下载
        </button>
      </section>

      <!-- 检索结果区 -->
      <section v-if="hasResults" class="card search-card layout-panel" :class="{ locked: generating }">
        <h3 class="card-title search-card-title">
          <span class="search-result-title">检索结果</span>
          <span class="count-badge">{{ countLabel }}</span>
          <span v-if="sourceGroupLabel" class="stage-label">{{ sourceGroupLabel }}</span>
        </h3>

        <template v-if="tab === 'pano'">
          <div v-for="(art, idx) in articles" :key="art.id || idx" class="collapse-item">
            <div class="collapse-head" @click="toggle(idx)">
              <span class="chevron" :class="{ open: expanded[idx] }">
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                  <path
                    d="M3.5 2.5L6.5 5L3.5 7.5"
                    stroke="#9b8ee8"
                    stroke-width="1.2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </span>
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
              <span class="chevron" :class="{ open: expanded[idx] }">
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                  <path
                    d="M3.5 2.5L6.5 5L3.5 7.5"
                    stroke="#9b8ee8"
                    stroke-width="1.2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </span>
              <span>{{ it.source_zh || it.book_title || it.chunk_id }}</span>
            </div>
            <div v-show="expanded[idx]" class="collapse-body">
              <p class="detail-text">{{ it.text }}</p>
            </div>
          </div>
        </template>
      </section>

      <p v-if="error" class="error-msg layout-panel">{{ error }}</p>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";

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
const seriesNo = ref(null);
const loadingSeries = ref(false);
const term = ref("圣经");
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

const indentMap = { bible_reading: 0, ot1: 0, ot2: 1, ot3: 2, ot4: 3, ot5: 4, ot6: 4, ot7: 4 };
const indentEm = (type) => `${(indentMap[type] ?? 1) * 1.5}em`;

const hasResults = computed(() =>
  tab.value === "pano" ? articles.value.length > 0 : items.value.length > 0
);

const countLabel = computed(() =>
  tab.value === "pano" ? `共${count.value}篇` : `共${count.value}条`
);

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

function switchTab(name) {
  if (generating.value) return;
  if (tab.value === name) return;
  tab.value = name;
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
  loadingSeries.value = true;
  try {
    const res = await fetch("/api/pano/series-list");
    const data = await res.json();
    seriesList.value = data.series || [];
    if (seriesList.value.length) {
      seriesNo.value = seriesList.value[0].series_no;
    }
  } catch (e) {
    error.value = "加载系列列表失败：" + e.message;
  } finally {
    loadingSeries.value = false;
  }
});

function onEnterSearch() {
  if (activeStage.value && typeof activeStage.value === "number") {
    onStageClick(activeStage.value);
  } else if (tab.value === "entry") {
    onStageClick(1);
  }
}

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

  error.value = "";
  searching.value = true;
  activeStage.value = stageNo;

  try {
    let res;
    if (tab.value === "pano") {
      res = await fetch("/api/pano/articles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ series_no: seriesNo.value, source_group_no: stageNo }),
      });
    } else {
      res = await fetch("/api/entry/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          term: term.value.trim(),
          source_group_no: stageNo,
          top_k: topK.value,
        }),
      });
    }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    applySearchResult(data);
  } catch (e) {
    error.value = "检索失败：" + e.message;
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
  error.value = "";
  searching.value = true;
  activeStage.value = "overview";

  try {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/progress/upload-text", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);

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
  } finally {
    searching.value = false;
    ev.target.value = "";
  }
}

async function generate(kind) {
  if (!plainText.value || generating.value) return;
  generating.value = true;
  generatedText.value = "";
  genUsage.value = null;

  const base = tab.value === "pano" ? "/api/progress/pano/generate" : "/api/progress/entry/generate";
  const path = kind === "segment" ? `${base}/segment` : `${base}/overview`;

  try {
    const body = { content: plainText.value, output_length: outputLength.value };
    if (tab.value === "entry") body.term = term.value.trim();

    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    generatedText.value = data.text || "";
    genUsage.value = data.usage || null;
  } catch (e) {
    error.value = "生成失败：" + e.message;
  } finally {
    generating.value = false;
  }
}

async function formatDownload() {
  if (!generatedText.value) return;
  formatting.value = true;
  try {
    const res = await fetch("/api/progress/format_download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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
  } finally {
    formatting.value = false;
  }
}
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.layout-inner {
  width: 75%;
  margin: 0 auto;
}

.layout-panel {
  width: 75%;
  margin-left: auto;
  margin-right: auto;
}

.navbar {
  background: #6b5ce7;
  color: white;
  width: 100%;
  padding: 16px 0;
  font-size: 18px;
  font-weight: bold;
  letter-spacing: 0.02em;
}

.navbar-inner {
  text-align: center;
}

.tabs {
  width: 100%;
  background: white;
  border-bottom: 2px solid #e8e8e8;
}

.tabs-inner {
  display: flex;
}

.tab {
  padding: 12px 24px;
  border: none;
  background: transparent;
  color: #888;
  font-size: 15px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: color 0.15s, border-color 0.15s;
}

.tab.active {
  color: #5b4cc4;
  font-weight: bold;
  border-bottom-color: #6b5ce7;
}

.tab:hover:not(.active):not(:disabled) {
  color: #555;
}

.tab:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.card.locked {
  pointer-events: none;
  opacity: 0.55;
}

.content {
  flex: 1;
  background: #f5f6fa;
  padding: 24px 0;
  width: 100%;
}

.card {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  padding: 24px;
  margin-bottom: 16px;
}

.card-title {
  margin: 0 0 16px;
  font-size: 15px;
  font-weight: 600;
  color: #333;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.count-badge {
  font-size: 13px;
  font-weight: normal;
  color: #888;
  background: #f5f6fa;
  padding: 2px 10px;
  border-radius: 10px;
}

.stage-label {
  font-size: 12px;
  font-weight: normal;
  color: #aaa;
}

.input-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 20px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-sm {
  flex-shrink: 0;
}

.label {
  font-size: 13px;
  color: #666;
}

.series-label {
  font-family: "楷体", "KaiTi", "STKaiti", serif;
  font-size: 15px;
  font-weight: bold;
  color: #000000;
}

.input {
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 14px;
  color: #333;
  outline: none;
  transition: border-color 0.15s;
}

.input:focus {
  border-color: #6b5ce7;
}

.select {
  min-width: 300px;
}

.input-topk {
  width: 80px;
}

.input-outlen {
  width: 100px;
}

.stage-row {
  display: flex;
  flex-wrap: nowrap;
  gap: 8px;
  margin-bottom: 20px;
}

.stage-btn {
  flex: 1;
  white-space: nowrap;
  text-align: center;
  border: 1px solid #c4b5fd;
  border-radius: 6px;
  padding: 6px 8px;
  background: #ede9fe;
  color: #5b4cc4;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.stage-btn:hover:not(:disabled):not(.active) {
  background: #ddd6fe;
  border-color: #6b5ce7;
  color: #4c3d9e;
}

.stage-btn.active {
  background: #6b5ce7;
  color: white;
  border-color: #6b5ce7;
}

.stage-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.meta-row {
  display: flex;
  align-items: center;
  gap: 24px;
  margin-bottom: 20px;
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

.btn-generate {
  font-family: "楷体", "KaiTi", "STKaiti", serif;
  font-weight: 900;
  font-size: 17px;
  color: #000000;
  background: #ede9fe;
  border: 1px solid #c4b5fd;
  border-radius: 8px;
  padding: 10px 24px;
  cursor: pointer;
  transition: background 0.15s;
  -webkit-font-smoothing: antialiased;
  text-shadow: 0 0 0.4px #000000;
}

.btn-generate:hover:not(:disabled) {
  background: #ddd6fe;
  color: #000000;
}

.btn-generate:disabled {
  opacity: 0.45;
  cursor: not-allowed;
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
  color: #6b5ce7;
  font-size: 14px;
  text-align: center;
  padding: 24px 0;
}

.stream-box pre {
  margin: 0;
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 14px;
  color: #333;
}

.btn-download {
  margin-top: 16px;
  background: #ede9fe;
  color: #5b4cc4;
  border: 1px solid #c4b5fd;
  border-radius: 8px;
  padding: 10px 24px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.btn-download:hover:not(:disabled) {
  background: #6b5ce7;
  color: white;
  border-color: #6b5ce7;
}

.btn-download:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.collapse-item {
  border-bottom: 1px solid #f0f0f0;
}

.collapse-head {
  padding: 10px 16px;
  border-radius: 6px;
  cursor: pointer;
  color: #555;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  user-select: none;
}

.collapse-head:hover {
  background: #ede9fe;
}

.search-result-title {
  font-family: "楷体", "KaiTi", "STKaiti", serif;
  font-size: 15px;
  font-weight: bold;
  color: #374151;
}

.result-card-title {
  align-items: baseline;
}

.gen-cost {
  font-size: 13px;
  font-weight: normal;
  color: #6b5ce7;
}

.gen-cost-detail {
  color: #888;
  font-size: 12px;
}

.chevron {
  flex-shrink: 0;
  display: inline-flex;
  transition: transform 0.2s ease;
}

.chevron.open {
  transform: rotate(90deg);
}

.collapse-body {
  padding: 0 16px 12px 16px;
  color: #000000;
  line-height: 1.9;
  font-size: 13px;
}

.outline-line {
  margin: 2px 0;
}

.excerpt,
.detail-text {
  margin: 8px 0 0;
  white-space: pre-wrap;
}

.error-msg {
  color: #cf1322;
  font-size: 14px;
  margin: 0;
  padding: 0 12px;
}
</style>

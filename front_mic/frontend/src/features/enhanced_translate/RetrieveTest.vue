<script setup>
import { ref, computed } from "vue";
import { toastError } from "@/components/utils/Dialog.js";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";
const MAX_CONTENT_CHARS = 100_000;

const content = ref("");
const loading = ref(false);
const error = ref(null);
const refs = ref([]);
const summary = ref(null);
const warnings = ref([]);

const canRetrieve = computed(() => !!(content.value || "").trim());

const lineRefGroups = computed(() => {
  const raw = refs.value || [];
  if (!raw.length) return [];
  if (raw[0]?.original_line != null) return raw;
  return [];
});

const totalDedupedCount = computed(() =>
  lineRefGroups.value.reduce((n, g) => n + (g.deduped_refs || []).length, 0)
);

function parseApiError(res, data) {
  let detail = data.detail;
  if (Array.isArray(detail)) {
    detail = detail.map((x) => x?.msg || x?.message || JSON.stringify(x)).join("；");
  }
  return detail || data.error || data.message || `请求失败（${res.status}）`;
}

function effectiveMatchKind(r) {
  const raw = r.match_kind || r.match_type;
  if (raw === "exact" || raw === "direct") return "exact";
  if (raw === "retrieved" || raw === "reference") return "retrieved";
  const hasCorpus = !!(r.chunk_id || r.id || r.text || r.zh_snippet || r.zh);
  if (hasCorpus) return "retrieved";
  return "none";
}

function matchTypeLabel(r) {
  const kind = effectiveMatchKind(r);
  if (kind === "exact") return "直接引用";
  if (kind === "retrieved") return "参考翻译";
  return "无匹配";
}

function normalizeDedupedRef(r, lineIndex) {
  const kind = effectiveMatchKind(r);
  return {
    paragraph: r.paragraph,
    id: (r.id || r.chunk_id || "").toString(),
    text: (r.text || r.zh_snippet || r.zh || "").trim(),
    en: (r.en || r.en_snippet || "").trim(),
    ch_source: (r.ch_source || r.source || "").trim(),
    en_source: (r.en_source || "").trim(),
    match_kind: kind,
    match_type: kind === "exact" ? "direct" : kind === "retrieved" ? "reference" : "none",
    line_index: lineIndex,
    zh: r.zh,
    source_type: r.source_type || "main",
    clauses: r.clauses || [],
    rerank_score: r.rerank_score,
  };
}

function lineTypeClass(group) {
  const t = group.line_type || "reference";
  return t === "outline" ? "line-type-outline" : "line-type-reference";
}

function hitLayerClass(layer) {
  if (layer === "层1·Additional Pool") return "layer-1";
  if (layer === "层2·ES Pool") return "layer-2";
  if (layer === "层3·Feasts") return "layer-3";
  if (layer === "层4·检索") return "layer-4";
  if (layer === "层4·检索失败") return "layer-4-fail";
  return "";
}

function formatRerankScore(score) {
  if (score == null || Number.isNaN(score)) return "";
  return Number(score).toFixed(4);
}

function statLabel(key) {
  const map = {
    total_lines: "总行数",
    pool: "Pool 子句",
    exact: "直接引用",
    retrieved: "参考翻译",
    none: "无匹配",
    additional_pool_lines: "Additional Pool 行",
    pool_full_match_lines: "ES Pool 行",
    feasts_lines: "Feasts 行",
    source_translated: "出处路1命中",
  };
  return map[key] || key;
}

function clearAll() {
  content.value = "";
  error.value = null;
  refs.value = [];
  summary.value = null;
  warnings.value = [];
}

async function runRetrieve() {
  const text = (content.value || "").trim();
  error.value = null;
  refs.value = [];
  summary.value = null;
  warnings.value = [];

  if (!text) {
    error.value = "请先粘贴纲目内容";
    return;
  }
  if (text.length > MAX_CONTENT_CHARS) {
    error.value = `正文过长：最多 ${MAX_CONTENT_CHARS.toLocaleString()} 字`;
    return;
  }

  const authToken = localStorage.getItem("token") || null;
  if (!authToken) {
    window.location.hash = "/login";
    return;
  }

  loading.value = true;
  try {
    const res = await fetch(`${apiBase}/api/ai_search/enhanced_translate/retrieve_test`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${authToken}`,
      },
      body: JSON.stringify({ content: text }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(parseApiError(res, data));
    if (data.error) throw new Error(data.error);

    refs.value = data.refs || [];
    summary.value = data.summary || null;
    warnings.value = data.warnings || [];
  } catch (e) {
    error.value = e.message || "检索失败";
    toastError(error.value);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="retrieve-test">
    <a-card>
      <p class="hint">
        仅执行检索与出处路1匹配，不调用 Gemini。用于调试各层命中、参考语料分层与 rerank 分数。
      </p>
      <a-divider :style="{ margin: '12px 0' }" />

      <div v-if="warnings.length" class="warn-strip">
        <div v-for="(w, i) in warnings" :key="i" class="warn-line">{{ w }}</div>
      </div>

      <div class="action-row">
        <button
          type="button"
          class="action-btn"
          :disabled="!canRetrieve || loading"
          @click="runRetrieve"
        >
          {{ loading ? "检索中…" : "开始检索" }}
        </button>
        <button type="button" class="clear-btn" :disabled="loading" @click="clearAll">清空</button>
      </div>

      <div class="textarea-wrap">
        <a-textarea
          v-model:value="content"
          :rows="12"
          placeholder="请粘贴简体中文纲目全文（可含分号子句与行末读经标注）"
          class="content-area"
          :disabled="loading"
          :maxlength="MAX_CONTENT_CHARS"
          show-count
        />
      </div>

      <div v-if="error" class="error">{{ error }}</div>
    </a-card>

    <a-card v-if="summary" class="result-card">
      <template #title>统计摘要</template>
      <div class="summary-grid">
        <template v-for="(val, key) in summary" :key="key">
          <div
            v-if="val !== null && val !== undefined && key !== 'gemini_cost_usd' && key !== 'total_cost_usd'"
            class="summary-item"
          >
            <span class="summary-label">{{ statLabel(key) }}</span>
            <span class="summary-value">{{ val }}</span>
          </div>
        </template>
      </div>
    </a-card>

    <a-card v-if="lineRefGroups.length" class="result-card refs-card">
      <template #title>
        参考语料（{{ lineRefGroups.length }} 行 · {{ totalDedupedCount }} 段）
      </template>
      <div class="refs-scroll">
        <div class="refs-list">
          <div
            v-for="group in lineRefGroups"
            :key="`line-${group.line_index}`"
            class="ref-line-group"
          >
            <div class="ref-line-title" :class="lineTypeClass(group)">
              <span class="line-type-tag">{{ group.line_type === "outline" ? "outline" : "reference" }}</span>
              <span
                v-if="group.hit_layer"
                class="hit-layer-tag"
                :class="hitLayerClass(group.hit_layer)"
              >{{ group.hit_layer }}</span>
              Line {{ group.line_index + 1 }}：{{ group.original_line }}
              <span v-if="group.stats?.additional_pool_line" class="pool-tag">Additional Pool</span>
              <span v-else-if="group.stats?.pool_line" class="pool-tag es-pool">ES Pool</span>
              <span v-else-if="group.stats?.feasts_line" class="pool-tag es-pool">Feasts</span>
            </div>
            <div
              v-if="group.reference_source_zh"
              class="ref-source-block"
            >
              <span class="ref-source-zh">{{ group.reference_source_zh }}</span>
              <span v-if="group.reference_source_en" class="ref-source-arrow"> → </span>
              <span v-if="group.reference_source_en" class="ref-source-en">{{ group.reference_source_en }}</span>
              <span v-else class="ref-source-pending">（路1未命中）</span>
            </div>
            <div
              v-for="r in (group.deduped_refs || []).map((x) => normalizeDedupedRef(x, group.line_index))"
              :key="`${group.line_index}-p-${r.paragraph}-${r.id}`"
              class="ref-card"
              :class="{
                'ref-card-direct': r.match_kind === 'exact',
                'ref-card-reference': r.match_kind === 'retrieved',
              }"
            >
              <div class="ref-card-head">
                <span class="ref-para">Paragraph {{ r.paragraph }}</span>
                <span
                  v-if="r.source_type === 'main'"
                  class="ref-source-tag tag-main"
                >主参考</span>
                <span
                  v-else-if="r.source_type === 'clause'"
                  class="ref-source-tag tag-clause"
                >子句参考</span>
                <span
                  v-if="r.rerank_score != null"
                  class="rerank-score"
                >rerank: {{ formatRerankScore(r.rerank_score) }}</span>
                <span
                  class="ref-tag-pill"
                  :class="{
                    'tag-direct': r.match_kind === 'exact',
                    'tag-reference': r.match_kind === 'retrieved',
                    'tag-none': r.match_kind === 'none',
                  }"
                >
                  [{{ matchTypeLabel(r) }}]
                </span>
              </div>
              <div
                v-if="r.source_type === 'clause' && r.clauses?.length"
                class="ref-clauses"
              >
                <span class="ref-label">clause</span>
                <span class="ref-value">{{ r.clauses.join("；") }}</span>
              </div>
              <div v-if="r.id" class="ref-id">id: {{ r.id }}</div>
              <div v-if="r.text" class="ref-field">
                <span class="ref-label">text</span>
                <span class="ref-value">{{ r.text }}</span>
              </div>
              <div v-if="r.en" class="ref-field">
                <span class="ref-label">en</span>
                <span class="ref-value">{{ r.en }}</span>
              </div>
              <div v-if="r.ch_source" class="ref-source-line">ch_source: {{ r.ch_source }}</div>
              <div v-if="r.en_source" class="ref-source-line">en_source: {{ r.en_source }}</div>
            </div>
          </div>
        </div>
      </div>
    </a-card>
  </div>
</template>

<style scoped>
.retrieve-test {
  max-width: 720px;
  margin: 0 auto;
}

.retrieve-test :deep(.ant-card) {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.06);
}

.hint {
  color: #555;
  margin: 0;
  font-size: 0.95em;
  line-height: 1.5;
}

.warn-strip {
  margin-bottom: 0.75rem;
  padding: 0.65rem 0.85rem;
  background: #fffbe6;
  border: 1px solid #ffe58f;
  border-radius: 8px;
}

.warn-line {
  color: #ad6800;
  font-size: 0.9em;
  line-height: 1.5;
}

.action-row {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
  align-items: center;
}

.action-btn {
  padding: 0.5em 1.5em;
  font-size: 1em;
  background: #1890ff;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}

.action-btn:hover:not(:disabled) {
  background: #40a9ff;
}

.action-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.clear-btn {
  padding: 0.5em 1em;
  font-size: 0.95em;
  background: #fff;
  color: #666;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  cursor: pointer;
}

.textarea-wrap {
  margin-top: 0.5rem;
}

.content-area {
  font-family: inherit;
}

.error {
  color: #cf1322;
  margin-top: 0.75rem;
}

.result-card {
  margin-top: 1rem;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 0.5rem 1rem;
}

.summary-item {
  display: flex;
  flex-direction: column;
  font-size: 0.85em;
}

.summary-label {
  color: #8c8c8c;
}

.summary-value {
  font-weight: 600;
  color: #262626;
}

.refs-scroll {
  max-height: 1200px;
  overflow-y: auto;
}

.refs-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.ref-line-group {
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 0.75rem;
  background: #fff;
}

.ref-line-title {
  font-weight: 600;
  color: #333;
  margin-bottom: 0.65rem;
  font-size: 0.9em;
  line-height: 1.5;
  word-break: break-word;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
}

.line-type-tag {
  font-size: 0.75em;
  font-weight: 600;
  padding: 0.1em 0.4em;
  border-radius: 4px;
  background: #f0f0f0;
  color: #595959;
}

.line-type-outline .line-type-tag {
  background: rgba(114, 46, 209, 0.1);
  color: #722ed1;
}

.hit-layer-tag {
  font-size: 0.75em;
  font-weight: 600;
  padding: 0.1em 0.4em;
  border-radius: 4px;
}

.layer-1 {
  background: rgba(56, 158, 13, 0.12);
  color: #389e0d;
}

.layer-2 {
  background: rgba(22, 119, 255, 0.12);
  color: #1677ff;
}

.layer-3 {
  background: rgba(250, 140, 22, 0.12);
  color: #d46b08;
}

.layer-4 {
  background: rgba(114, 46, 209, 0.12);
  color: #722ed1;
}

.layer-4-fail {
  background: rgba(207, 19, 34, 0.1);
  color: #cf1322;
}

.pool-tag {
  font-size: 0.75em;
  font-weight: 600;
  padding: 0.1em 0.4em;
  border-radius: 4px;
  background: rgba(56, 158, 13, 0.1);
  color: #389e0d;
}

.pool-tag.es-pool {
  background: rgba(22, 119, 255, 0.1);
  color: #1677ff;
}

.ref-card {
  border: 1px solid #e8e8e8;
  border-radius: 10px;
  padding: 0.75rem 1rem;
  background: #fafafa;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  margin-top: 0.5rem;
}

.ref-card-direct {
  border-left: 4px solid #389e0d;
}

.ref-card-reference {
  border-left: 4px solid #1677ff;
}

.ref-card-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.ref-para {
  font-weight: 600;
  color: #333;
}

.rerank-score {
  font-size: 0.8em;
  color: #722ed1;
  font-family: monospace;
}

.ref-tag-pill {
  font-size: 0.85em;
  font-weight: 600;
  padding: 0.1em 0.45em;
  border-radius: 4px;
}

.tag-direct {
  color: #389e0d;
  background: rgba(56, 158, 13, 0.08);
}

.tag-reference {
  color: #1677ff;
  background: rgba(22, 119, 255, 0.08);
}

.tag-none {
  color: #8c8c8c;
  background: #f5f5f5;
}

.ref-id {
  font-size: 0.85em;
  color: #666;
  margin-bottom: 0.35rem;
}

.ref-field {
  margin-top: 0.35rem;
  line-height: 1.55;
}

.ref-label {
  display: block;
  font-size: 0.75em;
  font-weight: 600;
  color: #8c8c8c;
  text-transform: lowercase;
  margin-bottom: 0.15rem;
}

.ref-value {
  display: block;
  color: #262626;
  white-space: pre-wrap;
  word-break: break-word;
}

.ref-source-line {
  margin-top: 0.35rem;
  font-size: 0.8em;
  color: #8c8c8c;
}

.ref-source-tag {
  font-size: 0.75em;
  font-weight: 600;
  padding: 0.1em 0.4em;
  border-radius: 4px;
}

.tag-main {
  background: rgba(114, 46, 209, 0.08);
  color: #722ed1;
}

.tag-clause {
  background: rgba(19, 194, 194, 0.08);
  color: #08979c;
}

.ref-clauses {
  margin-top: 0.35rem;
}

.ref-source-block {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  margin-bottom: 0.5rem;
  font-size: 0.85em;
}

.ref-source-zh {
  color: #8c8c8c;
}

.ref-source-arrow {
  color: #bbb;
}

.ref-source-en {
  color: #1677ff;
  font-style: italic;
}

.ref-source-pending {
  color: #faad14;
}
</style>

<script setup>
import { ref, computed } from "vue";
import { toastError } from "@main/components/utils/Dialog.js";

// 与主站其它工具一致：默认同源（nginx/8000）；仅单独起 testD 时在 .env 设 VITE_API_BASE=http://localhost:8050
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
  };
}

function lineTypeLabel(group) {
  const t = group.line_type || "reference";
  if (t === "outline") return "outline";
  if (t === "title") return "title";
  if (t === "bible-reading") return "bible-reading";
  return "reference";
}

function lineTypeClass(group) {
  const t = group.line_type || "reference";
  if (t === "outline") return "line-type-outline";
  if (t === "title") return "line-type-title";
  if (t === "bible-reading") return "line-type-bible";
  return "line-type-reference";
}

function hitLayerClass(layer) {
  if (layer === "层1·Additional Pool") return "layer-1";
  if (layer === "篇题·Pool" || layer === "篇题·无参考") return "layer-title";
  if (layer === "读经·跳过检索") return "layer-bible";
  if (layer === "层2·ES Pool") return "layer-2";
  if (layer === "层3·Feasts") return "layer-3";
  if (layer === "层4·检索") return "layer-4";
  if (layer === "层4·检索失败") return "layer-4-fail";
  return "";
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
    source_translated: "出处已翻译",
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
    const res = await fetch(`${apiBase}/api/testd/retrieve_test`, {
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
  <div class="page">
    <p class="hint">
      仅执行检索，不调用 Gemini。用于调试 <code>_retrieve_line</code> 各层命中与参考语料。
    </p>

    <a-alert
      v-if="warnings.length"
      type="warning"
      show-icon
      class="warn-banner"
      message="检索服务提示"
      :description="warnings.join('；')"
    />

    <div class="direction-actions">
      <a-button type="primary" :disabled="!canRetrieve || loading" :loading="loading" @click="runRetrieve">
        {{ loading ? "检索中…" : "开始检索" }}
      </a-button>
      <a-button type="default" danger @click="clearAll">清除</a-button>
    </div>

    <a-textarea
      v-model:value="content"
      :rows="14"
      placeholder="请粘贴简体中文纲目全文（可含分号子句与行末读经标注）"
      class="input-area"
    />

    <div v-if="error" class="err panel-err">{{ error }}</div>

    <div v-if="summary" class="summary-block">
      <div class="summary-head">统计摘要</div>
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
    </div>

    <div v-if="lineRefGroups.length" class="refs-block">
      <div class="refs-head">
        <span>参考语料（{{ lineRefGroups.length }} 行 · {{ totalDedupedCount }} 段）</span>
      </div>
      <div class="refs-list">
        <div
          v-for="group in lineRefGroups"
          :key="`line-${group.line_index}`"
          class="ref-line-group"
        >
          <div class="ref-line-title" :class="lineTypeClass(group)">
            <span class="line-type-tag">{{ lineTypeLabel(group) }}</span>
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
            <span v-if="group.reference_source_en" class="ref-source-arrow">→</span>
            <span v-if="group.reference_source_en" class="ref-source-en">{{ group.reference_source_en }}</span>
            <span v-else class="ref-source-pending">（翻译中）</span>
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
  </div>
</template>

<style scoped>
.page {
  max-width: 960px;
  margin: 0 auto;
  padding: 0 0 3rem;
}
.hint {
  color: #666;
  margin-bottom: 0.75rem;
}
.warn-banner {
  margin-bottom: 0.75rem;
  border: 1px solid #ffd591;
  background: #fff7e6;
  border-radius: 8px;
}
.direction-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
.input-area {
  font-family: inherit;
}
.err {
  color: #cf1322;
}
.panel-err {
  margin: 1rem 0;
}
.summary-block {
  margin-top: 1rem;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  padding: 0.75rem 1rem;
  background: #fff;
}
.summary-head {
  font-weight: 600;
  margin-bottom: 0.5rem;
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
.refs-block {
  margin-top: 1.5rem;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
}
.refs-head {
  padding: 0.75rem 1rem;
  font-weight: 600;
  background: #f5f5f5;
}
.refs-list {
  padding: 0.75rem 1rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.ref-line-group {
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 0.75rem;
  background: #fafafa;
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
.line-type-title .line-type-tag {
  background: rgba(19, 194, 194, 0.12);
  color: #08979c;
}
.line-type-bible .line-type-tag {
  background: rgba(47, 84, 235, 0.1);
  color: #2f54eb;
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
.layer-title {
  background: rgba(19, 194, 194, 0.12);
  color: #08979c;
}
.layer-bible {
  background: rgba(47, 84, 235, 0.1);
  color: #2f54eb;
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
.ref-line-group .ref-card {
  margin-top: 0.5rem;
}
.ref-card {
  border: 1px solid #e8e8e8;
  border-radius: 10px;
  padding: 0.75rem 1rem;
  background: #fff;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
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
  margin-top: 0.35rem;
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
  color: #fa8c16;
  font-size: 0.9em;
}
</style>

<script setup>
import ToolsHeader from "@main/components/toolbox/ToolsHeader.vue";
import { ref, computed } from "vue";
import { toastSuccess, toastWarning, toastError } from "@main/components/utils/Dialog.js";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";
const MAX_CONTENT_CHARS = 100_000;

const content = ref("");
const promptOverride = ref("");
const inputError = ref(null);
const loading = ref(false);
const error = ref(null);
const errorModalVisible = ref(false);
const errorModalMessage = ref("");
const result = ref(null);
const refs = ref([]);
const summary = ref(null);
const warnings = ref([]);
const durationMs = ref(null);
const downloadFormats = ref(["docx"]);
const downloading = ref(false);
const downloadingRefsTxt = ref(false);
/** line_index → 用户编辑后的 gemini_translate */
const editedTranslations = ref({});

const canTranslate = computed(() => !!(content.value || "").trim());

function formatDuration(ms) {
  if (ms == null) return "";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

function parseApiError(res, data) {
  let detail = data.detail;
  if (Array.isArray(detail)) {
    detail = detail.map((x) => x?.msg || x?.message || JSON.stringify(x)).join("；");
  }
  return detail || data.error || data.message || `请求失败（${res.status}）`;
}

function copyText(text) {
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    try {
      toastSuccess("已复制到剪贴板");
    } catch (_) {}
  });
}

async function updatePrompt() {
  const authToken = localStorage.getItem("token") || null;
  if (!authToken) {
    window.location.hash = "/login";
    return;
  }
  try {
    const res = await fetch(`${apiBase}/api/kg_rag/enhanced_translate/update_prompt`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${authToken}`,
      },
      body: JSON.stringify({ prompt: promptOverride.value }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(parseApiError(res, data));
    toastSuccess("Prompt 已更新");
  } catch (e) {
    toastError(e.message || "更新失败");
  }
}

async function translate() {
  const text = (content.value || "").trim();
  inputError.value = null;
  error.value = null;
  errorModalVisible.value = false;
  errorModalMessage.value = "";
  result.value = null;
  refs.value = [];
  editedTranslations.value = {};
  summary.value = null;
  warnings.value = [];

  if (!text) {
    inputError.value = "请先粘贴简体中文纲目";
    return;
  }
  if (text.length > MAX_CONTENT_CHARS) {
    inputError.value = `正文过长：最多 ${MAX_CONTENT_CHARS.toLocaleString()} 字`;
    return;
  }

  const authToken = localStorage.getItem("token") || null;
  if (!authToken) {
    window.location.hash = "/login";
    return;
  }

  loading.value = true;
  const start = Date.now();
  try {
    const res = await fetch(`${apiBase}/api/kg_rag/enhanced_translate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${authToken}`,
      },
      body: JSON.stringify({
        content: text,
        prompt_override: promptOverride.value || null,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(parseApiError(res, data));
    if (data.error && !data.result) {
      errorModalMessage.value = data.error;
      errorModalVisible.value = true;
      return;
    }
    if (!data.result) throw new Error("翻译失败，请稍后重试");
    result.value = data.result;
    refs.value = data.refs || [];
    const edits = {};
    for (const group of data.refs || []) {
      edits[group.line_index] = group.gemini_translate || "";
    }
    editedTranslations.value = edits;
    summary.value = data.summary || null;
    warnings.value = data.warnings || [];
    durationMs.value = Date.now() - start;
    if (warnings.value.length) {
      toastWarning(warnings.value.join("；"));
    } else {
      toastSuccess("增强式翻译完成");
    }
  } catch (err) {
    error.value = err.message || "网络错误，请稍后重试";
  } finally {
    loading.value = false;
  }
}

function getEditedResultText() {
  if (!lineRefGroups.value.length) return (result.value || "").trim();
  return lineRefGroups.value
    .map((g, i) => {
      const idx = g.line_index ?? i;
      const edited = editedTranslations.value[idx];
      if (edited !== undefined && edited !== null) return String(edited);
      return g.gemini_translate || "";
    })
    .join("\n");
}

const savingLineIndex = ref(null);

async function saveTranslation(group) {
  const originalLine = (group.original_line || "").trim();
  const lineIndex = group.line_index;
  const newTranslation = (editedTranslations.value[lineIndex] || "").trim();
  if (!originalLine || !newTranslation) return;

  const authToken = localStorage.getItem("token") || null;
  if (!authToken) {
    window.location.hash = "/login";
    return;
  }
  savingLineIndex.value = lineIndex;
  try {
    const res = await fetch(`${apiBase}/api/kg_rag/enhanced_translate/update_translation`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${authToken}`,
      },
      body: JSON.stringify({
        original_line: originalLine,
        new_translation: newTranslation,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(parseApiError(res, data));
    if (data.success) {
      group.gemini_translate = newTranslation;
      toastSuccess(`Line ${lineIndex + 1} 已更新 Additional Pool`);
    } else {
      toastWarning(data.error || "Pool 中无对应条目，未写入");
    }
  } catch (e) {
    toastError(e.message || "更新 Pool 失败");
  } finally {
    savingLineIndex.value = null;
  }
}

function onTranslationBlur(group) {
  saveTranslation(group);
}

async function downloadFormatted() {
  const editedText = getEditedResultText();
  if (!editedText) {
    toastWarning("请先完成翻译");
    return;
  }
  if (!downloadFormats.value.length) {
    toastWarning("请至少选择一个下载格式");
    return;
  }
  const authToken = localStorage.getItem("token") || null;
  if (!authToken) {
    window.location.hash = "/login";
    return;
  }
  downloading.value = true;
  try {
    for (const format of ["docx", "pdf"].filter((f) => downloadFormats.value.includes(f))) {
      const res = await fetch(`${apiBase}/api/ai_search/format_outline_only`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({
          direction: "zh2en",
          translated_text: editedText,
          output_format: format,
          is_outline: true,
        }),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        toastError(`${format.toUpperCase()} 格式化失败: ${errorData.detail || errorData.error || "未知错误"}`);
        continue;
      }
      const data = await res.json();
      if (format === "docx" && data.docx_base64) {
        const bin = Uint8Array.from(atob(data.docx_base64), (c) => c.charCodeAt(0));
        const blob = new Blob([bin], {
          type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = data.filename || "outline_en.docx";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
    }
  } finally {
    downloading.value = false;
  }
}

function matchTypeLabel(r) {
  const kind = effectiveMatchKind(r);
  if (kind === "exact") return "直接引用";
  if (kind === "retrieved") return "参考翻译";
  return "无匹配";
}

function isLineGroupShape(arr) {
  return arr.length > 0 && arr[0] != null && arr[0].original_line != null;
}

/** 后端 refs：按行 [{ line_index, original_line, deduped_refs, line_refs }] */
const lineRefGroups = computed(() => {
  const raw = refs.value || [];
  if (!raw.length) return [];
  if (isLineGroupShape(raw)) return raw;
  return [];
});

const totalDedupedCount = computed(() =>
  lineRefGroups.value.reduce((n, g) => n + (g.deduped_refs || []).length, 0)
);

function lineTypeClass(group) {
  const t = group.line_type || "reference";
  return t === "outline" ? "line-type-outline" : "line-type-reference";
}

function formatCost(usd) {
  if (usd == null || Number.isNaN(usd)) return "";
  return `$${Number(usd).toFixed(4)}`;
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
    additional_pool_appended: "Pool 新增",
    additional_pool_append_skipped: "Pool 跳过",
    gemini_cost_usd: "Gemini 费用",
  };
  return map[key] || key;
}

function effectiveMatchKind(r) {
  const raw = r.match_kind || r.match_type;
  if (raw === "exact" || raw === "direct") return "exact";
  if (raw === "retrieved" || raw === "reference") return "retrieved";
  const hasCorpus = !!(r.chunk_id || r.id || r.text || r.zh_snippet || r.zh);
  if (hasCorpus) return "retrieved";
  return "none";
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
  };
}

function buildRefsTxtContent() {
  const lines = [];
  lines.push("【带翻译内容】");
  lines.push((content.value || "").trim());
  lines.push("");
  lines.push("【编辑后译文】");
  lines.push(getEditedResultText());
  lines.push("");
  lines.push("【参考语料列表】");
  lineRefGroups.value.forEach((group, gIdx) => {
    if (gIdx > 0) lines.push("");
    const lineNo = (group.line_index ?? gIdx) + 1;
    lines.push(`Line ${lineNo}：${group.original_line || ""}`);
    const edited = editedTranslations.value[group.line_index ?? gIdx];
    if (edited !== undefined && edited !== null && String(edited).trim()) {
      lines.push(`译文：${String(edited).trim()}`);
    }
    (group.deduped_refs || []).forEach((r, pIdx) => {
      if (pIdx > 0) lines.push("");
      const nr = normalizeDedupedRef(r, group.line_index ?? gIdx);
      const para = nr.paragraph ?? pIdx + 1;
      lines.push(`Paragraph ${para} [${matchTypeLabel(nr)}]`);
      if (nr.id) lines.push(`id: ${nr.id}`);
      if (nr.text) lines.push(`text: ${nr.text}`);
      if (nr.en) lines.push(`en: ${nr.en}`);
      if (nr.ch_source) lines.push(`ch_source: ${nr.ch_source}`);
      if (nr.en_source) lines.push(`en_source: ${nr.en_source}`);
    });
  });
  return lines.join("\n");
}

function downloadRefsTxt() {
  const zh = (content.value || "").trim();
  if (!zh) {
    toastWarning("请先粘贴中文纲目");
    return;
  }
  if (!lineRefGroups.value.length) {
    toastWarning("请先完成翻译以生成参考语料");
    return;
  }
  downloadingRefsTxt.value = true;
  try {
    const body = buildRefsTxtContent();
    const blob = new Blob([body], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, "");
    a.download = `enhanced_translate_refs_${stamp}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toastSuccess("已下载原文+语料 TXT");
  } catch (e) {
    toastError(e?.message || "下载失败");
  } finally {
    downloadingRefsTxt.value = false;
  }
}
</script>

<template>
  <ToolsHeader title="增强式翻译（testD）" />

  <a-modal
    v-model:visible="errorModalVisible"
    title="翻译失败"
    ok-text="知道了"
    hide-cancel
    @ok="errorModalVisible = false"
  >
    <p>{{ errorModalMessage }}</p>
  </a-modal>

  <div class="page">
    <p class="hint">
      逐条检索职事语料后翻译为英文。绿色为直接引用，蓝色为参考翻译。
    </p>
    <a-alert
      v-if="warnings.length"
      type="warning"
      show-icon
      class="warn-banner"
      message="检索服务提示"
      :description="warnings.join('；') + '（此为临时状态，可稍后重新点击「增强式翻译」重试。）'"
    />

    <a-textarea
      v-model:value="content"
      :rows="14"
      placeholder="请粘贴简体中文纲目全文（可含分号子句与行末读经标注，如 —约三16：）"
      class="input-area"
    />
    <p v-if="inputError" class="err">{{ inputError }}</p>

    <div class="prompt-row">
      <span>附加 Prompt（可选）</span>
      <a-input v-model:value="promptOverride" placeholder="仅影响本次或保存到服务端" />
      <a-button size="small" @click="updatePrompt">保存 Prompt</a-button>
    </div>

    <div class="actions">
      <a-button type="primary" :disabled="!canTranslate || loading" @click="translate">
        {{ loading ? "翻译中…" : "增强式翻译" }}
      </a-button>
    </div>

    <div v-if="error" class="err panel-err">{{ error }}</div>

    <div v-if="summary" class="summary-block">
      <div class="summary-head">统计摘要</div>
      <div class="summary-grid">
        <div v-for="(val, key) in summary" :key="key" class="summary-item">
          <span class="summary-label">{{ statLabel(key) }}</span>
          <span class="summary-value">
            {{ key === "gemini_cost_usd" || key === "total_cost_usd" ? formatCost(val) : val }}
          </span>
        </div>
      </div>
    </div>

    <div v-if="result" class="result-block">
      <div class="result-head">
        <span>英文纲目</span>
        <span v-if="durationMs" class="dur">{{ formatDuration(durationMs) }}</span>
        <a-button type="link" size="small" @click="copyText(result)">复制</a-button>
        <a-button type="link" size="small" :loading="downloading" @click="downloadFormatted">
          下载 DOCX
        </a-button>
        <a-button
          type="link"
          size="small"
          :loading="downloadingRefsTxt"
          :disabled="!lineRefGroups.length"
          @click="downloadRefsTxt"
        >
          下载原文+语料
        </a-button>
      </div>
      <pre class="result-text">{{ result }}</pre>
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
            <span class="line-type-tag">{{ group.line_type === "outline" ? "outline" : "reference" }}</span>
            Line {{ group.line_index + 1 }}：{{ group.original_line }}
            <span v-if="group.stats?.additional_pool_line" class="pool-tag">Additional Pool</span>
            <span v-else-if="group.stats?.pool_line" class="pool-tag es-pool">ES Pool</span>
          </div>
          <a-textarea
            v-model:value="editedTranslations[group.line_index]"
            class="line-translation-input"
            :auto-size="{ minRows: 1 }"
            placeholder="编辑该行译文（失焦后自动更新 Additional Pool）"
            @blur="onTranslationBlur(group)"
          />
          <div class="line-translation-actions">
            <a-button
              size="small"
              :loading="savingLineIndex === group.line_index"
              @click="saveTranslation(group)"
            >
              保存
            </a-button>
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
  padding: 1rem 1.5rem 3rem;
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
.warn-banner :deep(.ant-alert-icon) {
  color: #fa8c16;
}
.warn-banner :deep(.ant-alert-message) {
  color: #d46b08;
  font-weight: 600;
}
.warn-banner :deep(.ant-alert-description) {
  color: #ad6800;
}
.input-area {
  font-family: inherit;
}
.prompt-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  margin: 0.75rem 0;
}
.actions {
  margin: 1rem 0;
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
.result-block {
  margin-top: 1.5rem;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 1rem;
  background: #fafafa;
}
.result-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
  font-weight: 600;
}
.dur {
  color: #888;
  font-weight: normal;
  font-size: 0.9em;
}
.result-text {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
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
.line-translation-input {
  margin-bottom: 0.35rem;
  font-family: inherit;
  font-size: 14px;
}
.line-translation-input :deep(textarea) {
  overflow-y: hidden;
  resize: none;
}
.line-translation-actions {
  margin-bottom: 0.65rem;
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
.ref-loc {
  color: #999;
  font-size: 0.85em;
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
.ref-id,
.ref-query {
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
</style>

<script setup>
import ToolsHeader from "@/components/toolbox/ToolsHeader.vue";
import RetrieveTest from "@/features/enhanced_translate/RetrieveTest.vue";
import { ref, computed } from "vue";
import { toastSuccess, toastWarning, toastError } from "@/components/utils/Dialog.js";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";
const MAX_CONTENT_CHARS = 100_000;

const activeView = ref("translate");
const content = ref("");
const direction = ref("zh2en");
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

function clearAll() {
  content.value = "";
  inputError.value = null;
  error.value = null;
  errorModalVisible.value = false;
  errorModalMessage.value = "";
  result.value = null;
  refs.value = [];
  editedTranslations.value = {};
  summary.value = null;
  warnings.value = [];
  durationMs.value = null;
  refsFilter.value = "all";
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
  refsFilter.value = "all";

  if (!text) {
    inputError.value =
      direction.value === "en2zh" ? "请先粘贴英文纲目" : "请先粘贴简体中文纲目";
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

  const endpoint =
    direction.value === "en2zh"
      ? "/api/ai_search/enhanced_translate/en2zh"
      : "/api/ai_search/enhanced_translate/translate";

  loading.value = true;
  const start = Date.now();
  try {
    const res = await fetch(`${apiBase}${endpoint}`, {
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

function translateZh2en() {
  direction.value = "zh2en";
  translate();
}

function translateEn2zh() {
  direction.value = "en2zh";
  translate();
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
    const res = await fetch(`${apiBase}/api/ai_search/enhanced_translate/update_translation`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${authToken}`,
      },
      body: JSON.stringify({
        original_line: originalLine,
        new_translation: newTranslation,
        direction: direction.value,
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
          direction: direction.value,
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

const lineRefGroups = computed(() => {
  const raw = refs.value || [];
  if (!raw.length) return [];
  if (isLineGroupShape(raw)) return raw;
  return [];
});

const refsFilter = ref("all");

/** 行级状态：direct=绿（Pool/精确/body 子串全等）、reference=蓝（含 main/clause 参考）、none=灰 */
function lineStatus(group) {
  const st = group.stats || {};
  if (st.additional_pool_line || st.pool_line || st.feasts_line) return "direct";
  const kinds = (group.deduped_refs || []).map((r) => effectiveMatchKind(r));
  if (kinds.includes("exact")) return "direct";
  if (kinds.includes("retrieved")) return "reference";
  return "none";
}

const refsStatusCount = computed(() => {
  const c = { direct: 0, reference: 0, none: 0 };
  lineRefGroups.value.forEach((g) => {
    c[lineStatus(g)] += 1;
  });
  return c;
});

const filteredLineRefGroups = computed(() => {
  if (refsFilter.value === "all") return lineRefGroups.value;
  return lineRefGroups.value.filter((g) => lineStatus(g) === refsFilter.value);
});

const totalDedupedCount = computed(() =>
  lineRefGroups.value.reduce((n, g) => n + (g.deduped_refs || []).length, 0)
);

function lineTypeClass(group) {
  const t = group.line_type || "reference";
  if (t === "outline") return "line-type-outline";
  if (t === "title") return "line-type-title";
  if (t === "bible-reading") return "line-type-bible-reading";
  return "line-type-reference";
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
    feasts_lines: "Feasts 行",
    additional_pool_appended: "Pool 新增",
    additional_pool_append_skipped: "Pool 跳过",
    gemini_cost_usd: "Gemini 费用",
    total_cost_usd: "总费用",
    source_translated: "出处已翻译",
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
    source_type: r.source_type || "main",
    clauses: r.clauses || [],
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
  <ToolsHeader title="增强式翻译" />

  <a-modal
    v-model:visible="errorModalVisible"
    title="翻译失败"
    ok-text="知道了"
    hide-cancel
    @ok="errorModalVisible = false"
  >
    <p>{{ errorModalMessage }}</p>
  </a-modal>

  <div class="box">
    <div class="view-switcher">
      <button
        type="button"
        class="view-switch-btn"
        :class="{ active: activeView === 'test' }"
        @click="activeView = activeView === 'test' ? 'translate' : 'test'"
      >
        检索测试台
      </button>
    </div>

    <RetrieveTest v-if="activeView === 'test'" />

    <template v-else>
    <a-card>
      <p class="hint">
        逐条检索职事语料后翻译为英文。绿色为直接引用，蓝色为参考翻译，灰色为无匹配。
        <strong>输入上限 {{ MAX_CONTENT_CHARS.toLocaleString() }} 字</strong>。
      </p>
      <a-divider :style="{ margin: '12px 0' }" />

      <p class="direction-fixed">
        翻译方向：{{ direction === "en2zh" ? "英文 → 简体中文" : "简体中文 → 英文" }}
      </p>
      <div class="direction-actions">
        <button
          type="button"
          class="action-btn"
          :class="{ 'action-btn-primary': direction === 'zh2en' }"
          :disabled="!canTranslate || loading"
          @click="translateZh2en"
        >
          {{ loading && direction === "zh2en" ? "翻译中…" : "中翻英" }}
        </button>
        <button
          type="button"
          class="action-btn"
          :class="{ 'action-btn-primary': direction === 'en2zh' }"
          :disabled="!canTranslate || loading"
          @click="translateEn2zh"
        >
          {{ loading && direction === "en2zh" ? "翻译中…" : "英翻中" }}
        </button>
      </div>
      <a-divider :style="{ margin: '12px 0' }" />

      <div class="textarea-wrap">
        <a-textarea
          v-model:value="content"
          :rows="12"
          :placeholder="
            direction === 'en2zh'
              ? '请粘贴英文纲目全文（可含分号子句与行末读经标注，如 —John 3:16:）'
              : '请粘贴简体中文纲目全文（可含分号子句与行末读经标注，如 —约三16：）'
          "
          class="content-area"
          :disabled="loading"
          :maxlength="MAX_CONTENT_CHARS"
          show-count
          allow-clear
        />
      </div>

      <div class="prompt-row">
        <span class="label">附加 Prompt（可选，仅本次请求）</span>
        <a-input
          v-model:value="promptOverride"
          placeholder="留空则使用默认增强翻译规则"
          :disabled="loading"
        />
      </div>

      <div class="action-row">
        <button type="button" class="clear-btn" :disabled="loading" @click="clearAll">清空</button>
      </div>
      <p v-if="loading" class="loading-hint">请耐心等待，逐行检索与翻译可能需要 1～2 分钟</p>
    </a-card>

    <div v-if="inputError" class="error">{{ inputError }}</div>
    <div v-if="error" class="error">{{ error }}</div>

    <template v-if="result || summary || lineRefGroups.length">
      <div v-if="warnings.length" class="warn-strip">
        <div v-for="(w, i) in warnings" :key="i" class="warn-line">{{ w }}</div>
      </div>

      <a-card v-if="summary" class="result-card">
        <template #title>统计摘要</template>
        <div class="summary-grid">
          <template v-for="(val, key) in summary" :key="key">
            <div v-if="val !== null && val !== undefined" class="summary-item">
              <span class="summary-label">{{ statLabel(key) }}</span>
              <span class="summary-value">
                {{ key === "gemini_cost_usd" || key === "total_cost_usd" ? formatCost(val) : val }}
              </span>
            </div>
          </template>
        </div>
      </a-card>

      <a-card v-if="result" class="result-card">
        <template #title>
          <div class="result-title-row">
            <span>{{ direction === "en2zh" ? "中文纲目" : "英文纲目" }}</span>
            <span v-if="durationMs" class="dur">{{ formatDuration(durationMs) }}</span>
            <button type="button" class="link-btn" @click="copyText(result)">复制</button>
            <button type="button" class="link-btn" :disabled="downloading" @click="downloadFormatted">
              {{ downloading ? "下载中…" : "下载 DOCX" }}
            </button>
            <button
              type="button"
              class="link-btn"
              :disabled="downloadingRefsTxt || !lineRefGroups.length"
              @click="downloadRefsTxt"
            >
              {{ downloadingRefsTxt ? "下载中…" : "下载原文+语料" }}
            </button>
          </div>
        </template>
        <div class="result-scroll">
          <pre class="result-text">{{ result }}</pre>
        </div>
      </a-card>

      <a-card v-if="lineRefGroups.length" class="result-card refs-card">
        <template #title>
          参考语料（{{ lineRefGroups.length }} 行 · {{ totalDedupedCount }} 段）
        </template>
        <div class="refs-stats">
          <span
            class="stat-item stat-all"
            :class="{ 'stat-active': refsFilter === 'all' }"
            @click="refsFilter = 'all'"
          >全部 ({{ lineRefGroups.length }})</span>
          <span
            class="stat-item stat-green"
            :class="{ 'stat-active': refsFilter === 'direct' }"
            @click="refsFilter = 'direct'"
          >直接引用 ({{ refsStatusCount.direct }})</span>
          <span
            class="stat-item stat-blue"
            :class="{ 'stat-active': refsFilter === 'reference' }"
            @click="refsFilter = 'reference'"
          >参考翻译 ({{ refsStatusCount.reference }})</span>
          <span
            class="stat-item stat-gray"
            :class="{ 'stat-active': refsFilter === 'none' }"
            @click="refsFilter = 'none'"
          >无匹配 ({{ refsStatusCount.none }})</span>
        </div>
        <div class="refs-scroll">
        <div class="refs-list">
          <div
            v-for="group in filteredLineRefGroups"
            :key="`line-${group.line_index}`"
            class="ref-line-group"
          >
            <div class="ref-line-title" :class="lineTypeClass(group)">
              <span class="line-type-tag">{{ group.line_type || "reference" }}</span>
              Line {{ group.line_index + 1 }}：{{ group.original_line }}
              <span v-if="group.stats?.additional_pool_line" class="pool-tag">Additional Pool</span>
              <span v-else-if="group.stats?.pool_line" class="pool-tag es-pool">ES Pool</span>
              <span v-else-if="group.stats?.feasts_line" class="pool-tag es-pool">Feasts</span>
            </div>
            <div
              v-if="group.reference_source_zh_list?.length || group.reference_source_zh"
              class="ref-source-block"
            >
              <template v-if="group.reference_source_zh_list?.length">
                <div
                  v-for="(srcZh, si) in group.reference_source_zh_list"
                  :key="si"
                  class="ref-source-pair"
                >
                  <span class="ref-source-zh">{{ srcZh }}</span>
                </div>
                <span v-if="group.reference_source_en" class="ref-source-arrow"> → </span>
                <span v-if="group.reference_source_en" class="ref-source-en">{{ group.reference_source_en }}</span>
                <span v-else class="ref-source-pending">（待翻译）</span>
              </template>
              <template v-else>
                <span class="ref-source-zh">{{ group.reference_source_zh }}</span>
                <span v-if="group.reference_source_en" class="ref-source-arrow"> → </span>
                <span v-if="group.reference_source_en" class="ref-source-en">{{ group.reference_source_en }}</span>
                <span v-else class="ref-source-pending">（待翻译）</span>
              </template>
            </div>
            <a-textarea
              v-model:value="editedTranslations[group.line_index]"
              class="line-translation-input"
              :auto-size="{ minRows: 1, maxRows: 4 }"
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
      </a-card>
    </template>
    </template>
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

.direction-fixed {
  margin: 0 0 8px;
  font-weight: 600;
  color: #333;
  font-size: 1em;
}

.direction-actions {
  display: flex;
  gap: 12px;
  margin-bottom: 4px;
}

.action-btn-primary {
  background: #1677ff;
  color: #fff;
  border-color: #1677ff;
}

.ref-source-pair {
  margin-bottom: 2px;
}

.textarea-wrap {
  position: relative;
}

.content-area {
  font-family: inherit;
}

.prompt-row {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin: 0.75rem 0 0;
}

.prompt-row .label {
  font-size: 0.9em;
  color: #555;
}

.action-row {
  display: flex;
  gap: 0.75rem;
  margin-top: 1rem;
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

.clear-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.loading-hint {
  margin: 0.75rem 0 0;
  color: #888;
  font-size: 0.9em;
}

.error {
  color: #cf1322;
  margin-top: 0.75rem;
}

.warn-strip {
  margin-top: 1rem;
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

.result-card {
  margin-top: 1rem;
}

.result-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.dur {
  color: #888;
  font-weight: normal;
  font-size: 0.9em;
}

.link-btn {
  background: none;
  border: none;
  color: #1890ff;
  cursor: pointer;
  padding: 0;
  font-size: 0.9em;
}

.link-btn:disabled {
  color: #bbb;
  cursor: not-allowed;
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

.result-scroll {
  max-height: 420px;
  overflow-y: auto;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  padding: 12px 16px;
  background: #fafafa;
}

.result-text {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
}

.refs-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.stat-item {
  padding: 2px 10px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  user-select: none;
}

.stat-all {
  color: #595959;
  background: #f5f5f5;
  border: 1px solid #d9d9d9;
}

.stat-green {
  color: #389e0d;
  background: #f6ffed;
  border: 1px solid #b7eb8f;
}

.stat-blue {
  color: #096dd9;
  background: #e6f4ff;
  border: 1px solid #91caff;
}

.stat-gray {
  color: #8c8c8c;
  background: #fafafa;
  border: 1px solid #d9d9d9;
}

.stat-all.stat-active {
  background: #595959;
  color: #fff;
  border-color: #595959;
}

.stat-green.stat-active {
  background: #52c41a;
  color: #fff;
  border-color: #52c41a;
}

.stat-blue.stat-active {
  background: #1677ff;
  color: #fff;
  border-color: #1677ff;
}

.stat-gray.stat-active {
  background: #8c8c8c;
  color: #fff;
  border-color: #8c8c8c;
}

.refs-scroll {
  max-height: 1200px;
  overflow-y: auto;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  padding: 12px 16px;
  background: #fafafa;
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

.line-translation-actions {
  margin-bottom: 0.65rem;
}

.ref-card {
  border: 1px solid #e8e8e8;
  border-radius: 10px;
  padding: 0.75rem 1rem;
  background: #fff;
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

.view-switcher {
  margin-bottom: 0.75rem;
}

.view-switch-btn {
  padding: 0.4em 1em;
  font-size: 0.9em;
  background: #fff;
  color: #595959;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  cursor: pointer;
}

.view-switch-btn.active {
  background: #1890ff;
  color: #fff;
  border-color: #1890ff;
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

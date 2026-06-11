<script setup>
import { ref, computed } from "vue";

const apiBase = "";

const headerSeries = ref("");
const headerTopic = ref("");
const headerChapter = ref("");
const headerReading = ref("");
const inputText = ref("");
const loading = ref(false);
const downloading = ref(false);
const errorMsg = ref("");
const results = ref([]);
const copiedAll = ref(false);
const statusFilter = ref("all");

const statusMeta = {
  original: { label: "原文", color: "#52c41a" },
  minor: { label: "微调", color: "#faad14" },
  replaced: { label: "已替换", color: "#1890ff" },
  manual: { label: "人工处理", color: "#f5222d" },
};

// 与 kg_rag_service.py _BIBLE_BOOKS 保持一致
const BIBLE_BOOKS =
  "创出利民申书士得撒上撒下王上王下代上代下拉尼斯伯诗箴传歌赛耶哀结但" +
  "何珥摩俄拿弥鸿哈番该亚玛" +
  "太可路约徒罗林前林后加弗腓西帖前帖后提前提后多门来雅彼前彼后约壹约贰约叁犹启" +
  "参";

const PREFIX_RE = /^[壹貳贰參叄叁参肆伍陸陆柒捌玖拾一二三四五六七八九十\da-z（）()]+[\t　]/;

function escapeCharClass(s) {
  return s.replace(/[\]\\^-]/g, "\\$&");
}

const BOOK_PAT = `[${escapeCharClass(BIBLE_BOOKS)}]{1,4}`;
const CHAP_PAT = `[\\d一二三四五六七八九十百～~\\-至、\\s]+`;
const REF_UNIT = `(?:${BOOK_PAT})?${CHAP_PAT}`;
const SCRIPTURE_REF_RE = new RegExp(
  `(—${BOOK_PAT}${CHAP_PAT}(?:[,，；;]${REF_UNIT})*[：:。]?\\s*)$`
);
const PURE_VERSE_RE = /(—[\d～~\-至、\s\d]+节[。：:]?\s*)$/;

function findScriptureSuffix(rest) {
  const scriptureMatches = [...rest.matchAll(new RegExp(SCRIPTURE_REF_RE.source, "g"))];
  if (scriptureMatches.length) {
    const m = scriptureMatches[scriptureMatches.length - 1];
    return [rest.slice(0, m.index), m[0]];
  }
  const m = rest.match(PURE_VERSE_RE);
  if (m) {
    return [rest.slice(0, m.index), m[0]];
  }
  return [rest, ""];
}

function parseOutlineLine(line) {
  const text = line || "";
  const pm = text.match(PREFIX_RE);
  if (pm) {
    const prefix = pm[0];
    const rest = text.slice(prefix.length);
    const [body, suffix] = findScriptureSuffix(rest);
    return { prefix, body, suffix };
  }
  const [body, suffix] = findScriptureSuffix(text);
  return { prefix: "", body, suffix };
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function charDiffOps(a, b) {
  const n = a.length;
  const m = b.length;
  const dp = Array.from({ length: n + 1 }, () => Array(m + 1).fill(0));
  for (let i = 1; i <= n; i += 1) {
    for (let j = 1; j <= m; j += 1) {
      if (a[i - 1] === b[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
      }
    }
  }
  const ops = [];
  let i = n;
  let j = m;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && a[i - 1] === b[j - 1]) {
      ops.unshift({ type: "equal", ch: a[i - 1] });
      i -= 1;
      j -= 1;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      ops.unshift({ type: "insert", ch: b[j - 1] });
      j -= 1;
    } else {
      ops.unshift({ type: "delete", ch: a[i - 1] });
      i -= 1;
    }
  }
  return ops;
}

function renderDiffOps(ops) {
  let html = "";
  for (const op of ops) {
    const ch = escapeHtml(op.ch);
    if (op.type === "equal") {
      html += ch;
    } else if (op.type === "delete") {
      html += `<span class="diff-del">${ch}</span>`;
    } else {
      html += `<span class="diff-ins">${ch}</span>`;
    }
  }
  return html;
}

function diffHighlight(original, result) {
  const o = parseOutlineLine(original);
  const r = parseOutlineLine(result);
  const bodyHtml = renderDiffOps(charDiffOps(o.body, r.body));
  const suffix = r.suffix || o.suffix;
  return `${escapeHtml(r.prefix || o.prefix)}${bodyHtml}${escapeHtml(suffix)}`;
}

const canStart = computed(() => inputText.value.trim().length > 0);

const statusCount = computed(() => {
  const c = { original: 0, minor: 0, replaced: 0, manual: 0 };
  results.value.forEach((r) => {
    if (c[r.status] !== undefined) c[r.status] += 1;
  });
  return c;
});

const filteredData = computed(() => {
  if (statusFilter.value === "all") return results.value;
  return results.value.filter((r) => r.status === statusFilter.value);
});

function buildHeaderLines() {
  return [headerSeries.value, headerTopic.value, headerChapter.value, headerReading.value].filter(
    (s) => (s || "").trim()
  );
}

async function postJson(path, body) {
  const res = await fetch(`${apiBase}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  let data = {};
  try {
    data = JSON.parse(text);
  } catch {}
  return { ok: res.ok, status: res.status, data };
}

async function startMinisterialize() {
  const lines = inputText.value.split("\n").filter((l) => l.trim());
  if (!lines.length) return;
  loading.value = true;
  errorMsg.value = "";
  results.value = [];
  statusFilter.value = "all";
  try {
    const { ok, data } = await postJson("/api/testc/ministerialize/process", { lines });
    if (!ok) {
      errorMsg.value = "处理失败，请稍后重试";
      return;
    }
    let seq = 0;
    results.value = (data.results || []).map((r) => {
      seq += 1;
      return {
        key: String(seq),
        displaySeq: seq,
        original: r.original,
        status: r.status,
        result: r.result ?? "",
        suggestion: r.suggestion || "",
        source: r.source || "",
        error: r.error || "",
      };
    });
  } catch (e) {
    errorMsg.value = "网络错误：" + e;
  } finally {
    loading.value = false;
  }
}

function copyAll() {
  if (!results.value.length) return;
  const headers = buildHeaderLines().map((s) => s.trim());
  const bodyLines = results.value
    .map((r) => (r.result || "").trim())
    .filter(Boolean);
  const text = [...headers, ...bodyLines].join("\n");
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    copiedAll.value = true;
    setTimeout(() => {
      copiedAll.value = false;
    }, 2000);
  });
}

async function downloadDocx(withSource = false) {
  if (!results.value.length) {
    errorMsg.value = "请先完成职事化";
    return;
  }
  const authToken = localStorage.getItem("token");
  if (!authToken) {
    window.location.hash = "/login";
    return;
  }

  const lines = results.value
    .map((row) => ({
      text: (row.result || "").trim(),
      source: (row.source || "").trim(),
    }))
    .filter((r) => r.text);
  if (!lines.length) {
    errorMsg.value = "结果为空，无法下载";
    return;
  }

  downloading.value = true;
  errorMsg.value = "";
  try {
    const res = await fetch(`${apiBase}/api/kg_rag/ministerialize_docx`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${authToken}`,
      },
      body: JSON.stringify({
        lines,
        header_lines: buildHeaderLines(),
        title: (headerChapter.value || "").trim(),
        with_source: withSource,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      errorMsg.value = data.detail || data.error || "下载失败";
      return;
    }
    const b64 = data.docx_base64;
    const title = (headerChapter.value || "").trim();
    const filename = withSource
      ? title
        ? `${title}（纲目带出处）.docx`
        : "纲目职事化（纲目带出处）.docx"
      : data.filename || "纲目职事化.docx";
    if (!b64) {
      errorMsg.value = data.error || "未返回文件";
      return;
    }
    const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const blob = new Blob([bin], {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    errorMsg.value = err.message || "下载失败";
  } finally {
    downloading.value = false;
  }
}

function statusLabel(status) {
  return statusMeta[status]?.label || status;
}

function statusColor(status) {
  return statusMeta[status]?.color || "#999";
}
</script>

<template>
  <div class="page">
    <div class="page-title">纲目职事化</div>
    <p class="page-desc">每行一条纲目，最多 200 行</p>

    <div class="section">
      <div class="header-fields">
        <div class="header-row">
          <span class="header-label">第一行</span>
          <input
            v-model="headerSeries"
            class="input-text"
            type="text"
            placeholder="第一行（可选）"
            :disabled="loading"
          />
        </div>
        <div class="header-row">
          <span class="header-label">第二行</span>
          <input
            v-model="headerTopic"
            class="input-text"
            type="text"
            placeholder="第二行（可选）"
            :disabled="loading"
          />
        </div>
        <div class="header-row">
          <span class="header-label">第三行</span>
          <input
            v-model="headerChapter"
            class="input-text"
            type="text"
            placeholder="第三行（可选）"
            :disabled="loading"
          />
        </div>
        <div class="header-row">
          <span class="header-label">读经</span>
          <input
            v-model="headerReading"
            class="input-text"
            type="text"
            placeholder="读经（可选）"
            :disabled="loading"
          />
        </div>
      </div>

      <div class="field-divider" />

      <label class="field-label">纲目正文</label>
      <textarea
        v-model="inputText"
        class="textarea"
        rows="10"
        placeholder="请粘贴纲目，每行一条"
        :disabled="loading"
      />
    </div>

    <button
      class="primary-btn"
      :disabled="!canStart || loading"
      @click="startMinisterialize"
    >
      {{ loading ? "处理中…" : "开始职事化" }}
    </button>

    <div v-if="loading" class="loading-hint">
      职事化处理中，请稍候…（行数多时约需 10～20 秒）
    </div>

    <div v-if="errorMsg" class="error-box">{{ errorMsg }}</div>

    <div v-if="results.length" class="results-section">
      <div class="result-card">
        <div class="info-bar">
          <div class="info-row">
            <span
              class="stat-item stat-all"
              :class="{ 'stat-active': statusFilter === 'all' }"
              @click="statusFilter = 'all'"
            >全部 {{ results.length }}</span>
            <span
              class="stat-item stat-green"
              :class="{ 'stat-active': statusFilter === 'original' }"
              @click="statusFilter = 'original'"
            >原文 {{ statusCount.original }}</span>
            <span
              class="stat-item stat-gold"
              :class="{ 'stat-active': statusFilter === 'minor' }"
              @click="statusFilter = 'minor'"
            >微调 {{ statusCount.minor }}</span>
            <span
              class="stat-item stat-blue"
              :class="{ 'stat-active': statusFilter === 'replaced' }"
              @click="statusFilter = 'replaced'"
            >已替换 {{ statusCount.replaced }}</span>
            <span
              class="stat-item stat-red"
              :class="{ 'stat-active': statusFilter === 'manual' }"
              @click="statusFilter = 'manual'"
            >人工处理 {{ statusCount.manual }}</span>
          </div>
        </div>

        <div class="result-list">
          <div
            v-for="(row, idx) in filteredData"
            :key="row.key"
            class="result-item"
            :class="{ 'result-item-last': idx === filteredData.length - 1 }"
          >
            <div class="result-row-original">
              <span class="seq-num">{{ row.displaySeq }}.</span>
              <span class="original-text">{{ row.original }}</span>
            </div>
            <div class="result-row-inner-divider" />
            <div class="result-row-edit">
              <span
                class="status-tag"
                :style="{ background: statusColor(row.status), borderColor: statusColor(row.status) }"
              >
                {{ statusLabel(row.status) }}
              </span>
              <template v-if="row.status === 'minor'">
                <textarea
                  v-model="row.result"
                  class="result-input"
                  rows="2"
                  :disabled="loading"
                />
                <div
                  v-if="row.suggestion"
                  class="result-diff minor-suggestion"
                  v-html="diffHighlight(row.original, row.suggestion)"
                />
              </template>
              <textarea
                v-else
                v-model="row.result"
                class="result-input"
                rows="2"
                :disabled="loading"
              />
              <input
                v-if="row.status === 'manual' || row.status === 'replaced'"
                v-model="row.source"
                class="source-input"
                type="text"
                placeholder="手动输入出处，如：创世记生命读经，第一篇；无需括号"
                :disabled="loading"
              />
              <div v-if="row.error" class="row-error">{{ row.error }}</div>
            </div>
          </div>
        </div>
      </div>

      <div class="bottom-actions">
        <button class="copy-all-btn" type="button" @click="copyAll">
          {{ copiedAll ? "已复制" : "复制全部结果" }}
        </button>
        <button
          class="download-btn download-btn-primary"
          type="button"
          :disabled="downloading"
          @click="downloadDocx(false)"
        >
          {{ downloading ? "下载中…" : "下载 docx" }}
        </button>
        <button
          class="download-btn"
          type="button"
          :disabled="downloading"
          @click="downloadDocx(true)"
        >
          {{ downloading ? "下载中…" : "下载含出处 docx" }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page {
  max-width: 960px;
  margin: 0 auto;
  padding: 2em 1.5em 4em;
  background: #f7f5f0;
  min-height: 100vh;
  color: #333;
  font-family: sans-serif;
}

.page-title {
  font-size: 1.5em;
  font-weight: 700;
  color: #2c5f8a;
  margin-bottom: 0.4em;
}

.page-desc {
  margin: 0 0 1.5em;
  font-size: 0.95em;
  color: #666;
}

.section {
  background: #fff;
  border-radius: 8px;
  padding: 1.2em 1.4em;
  margin-bottom: 1.2em;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
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

.header-label {
  flex: 0 0 4em;
  color: #555;
  font-weight: 500;
  font-size: 0.95em;
}

.field-divider {
  height: 1px;
  background: #f0ece4;
  margin: 16px 0;
}

.field-label {
  display: block;
  font-weight: 600;
  color: #444;
  margin-bottom: 8px;
  font-size: 0.95em;
}

.input-text,
.textarea,
.result-input,
.source-input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #d0ccc4;
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 0.95em;
  font-family: inherit;
  background: #faf9f7;
  color: #333;
  outline: none;
  transition: border-color 0.15s;
}

.header-row .input-text {
  flex: 1;
}

.textarea {
  padding: 10px 12px;
  line-height: 1.7;
  resize: vertical;
}

.result-input {
  resize: vertical;
  line-height: 1.7;
  min-height: 2.5em;
}

.input-text:focus,
.textarea:focus,
.result-input:focus,
.source-input:focus {
  border-color: #2c5f8a;
}

.input-text:disabled,
.textarea:disabled,
.result-input:disabled,
.source-input:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.source-input {
  margin-top: 4px;
  font-size: 0.85em;
  color: #999;
}

.primary-btn {
  width: 100%;
  padding: 12px;
  background: #2c5f8a;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 1.05em;
  font-weight: 600;
  cursor: pointer;
  margin-bottom: 1em;
  transition: background 0.15s, opacity 0.15s;
}

.primary-btn:hover:not(:disabled) {
  background: #1e4a6e;
}

.primary-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.loading-hint {
  text-align: center;
  color: #666;
  font-size: 0.9em;
  margin-bottom: 1.2em;
}

.error-box {
  background: #fff2f0;
  border: 1px solid #ffccc7;
  border-radius: 6px;
  padding: 10px 14px;
  color: #cf1322;
  font-size: 0.9em;
  margin-bottom: 1.2em;
}

.results-section {
  margin-top: 1.5em;
}

.result-card {
  background: #fff;
  border-radius: 8px;
  padding: 1.2em 1.4em;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.07);
  margin-bottom: 1em;
}

.info-bar {
  margin-bottom: 12px;
}

.info-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
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

.stat-gold {
  color: #d48806;
  background: #fffbe6;
  border: 1px solid #ffe58f;
}

.stat-blue {
  color: #096dd9;
  background: #e6f4ff;
  border: 1px solid #91caff;
}

.stat-red {
  color: #cf1322;
  background: #fff1f0;
  border: 1px solid #ffa39e;
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

.stat-gold.stat-active {
  background: #faad14;
  color: #fff;
  border-color: #faad14;
}

.stat-blue.stat-active {
  background: #1677ff;
  color: #fff;
  border-color: #1677ff;
}

.stat-red.stat-active {
  background: #ff4d4f;
  color: #fff;
  border-color: #ff4d4f;
}

.result-list {
  display: flex;
  flex-direction: column;
}

.result-item {
  padding: 12px 0 16px;
  border-bottom: 1px solid #e8e8e8;
}

.result-item-last {
  border-bottom: none;
  padding-bottom: 0;
}

.result-row-original {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  line-height: 1.6;
}

.seq-num {
  flex: 0 0 auto;
  color: #aaa;
  font-size: 12px;
  min-width: 1.5em;
}

.original-text {
  color: #888;
  flex: 1;
  word-break: break-word;
  white-space: pre-wrap;
}

.result-row-inner-divider {
  height: 1px;
  background: #f0f0f0;
  margin: 8px 0 10px 1.5em;
}

.result-row-edit {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 0;
  padding-left: 1.5em;
}

.status-tag {
  display: inline-block;
  align-self: flex-start;
  padding: 2px 10px;
  border-radius: 4px;
  font-size: 0.85em;
  font-weight: 600;
  color: #fff;
  border: 1px solid transparent;
}

.result-diff {
  flex: 1;
  min-height: 32px;
  padding: 4px 11px;
  line-height: 1.6;
  word-break: break-word;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  background: #fff;
}

.result-diff :deep(.diff-del) {
  text-decoration: line-through;
  color: #dc3545;
}

.result-diff :deep(.diff-ins) {
  background: #d4edda;
  color: #155724;
}

.minor-suggestion {
  background: #fafafa;
  border-radius: 6px;
  color: #595959;
  cursor: default;
}

.row-error {
  margin-top: 6px;
  font-size: 0.82em;
  color: #cf1322;
}

.bottom-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.copy-all-btn,
.download-btn {
  padding: 8px 20px;
  border: 1px solid #2c5f8a;
  border-radius: 6px;
  background: #fff;
  color: #2c5f8a;
  font-size: 0.95em;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.copy-all-btn:hover,
.download-btn:hover:not(:disabled) {
  background: #2c5f8a;
  color: #fff;
}

.download-btn-primary {
  background: #2c5f8a;
  color: #fff;
}

.download-btn-primary:hover:not(:disabled) {
  background: #1e4a6e;
  border-color: #1e4a6e;
}

.download-btn:disabled,
.download-btn-primary:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>

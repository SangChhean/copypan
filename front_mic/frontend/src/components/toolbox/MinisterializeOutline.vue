<script setup>
import ToolsHeader from "./ToolsHeader.vue";
import { ref, computed } from "vue";
import { LoadingOutlined, DownloadOutlined } from "@ant-design/icons-vue";
import { toastSuccess, toastWarning } from "../utils/Dialog";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";

const headerSeries = ref("");
const headerTopic = ref("");
const headerChapter = ref("");
const headerReading = ref("");
const inputText = ref("");
const loading = ref(false);
const downloading = ref(false);
const error = ref(null);
const tableData = ref([]);

const statusTag = {
  original: { color: "green", label: "原文" },
  minor: { color: "gold", label: "微调" },
  replaced: { color: "blue", label: "已替换" },
  manual: { color: "red", label: "人工处理" },
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

const showResults = computed(() => tableData.value.length > 0);

const stats = computed(() => ({
  original: tableData.value.filter((r) => r.status === "original").length,
  minor: tableData.value.filter((r) => r.status === "minor").length,
  replaced: tableData.value.filter((r) => r.status === "replaced").length,
  manual: tableData.value.filter((r) => r.status === "manual").length,
  total: tableData.value.length,
}));

const showStats = computed(() => showResults.value && !loading.value);

function buildHeaderLines() {
  return [headerSeries.value, headerTopic.value, headerChapter.value, headerReading.value].filter(
    (s) => (s || "").trim()
  );
}

function mapResultRow(r, displaySeq) {
  return {
    key: String(r.index),
    index: r.index,
    displaySeq,
    original: r.original,
    status: r.status,
    result: r.result,
    suggestion: r.suggestion || "",
    rerunning: false,
    editing: false,
  };
}

async function startMinisterialize() {
  const raw = (inputText.value || "").trim();
  if (!raw) {
    error.value = "请先粘贴纲目，每行一条";
    tableData.value = [];
    return;
  }
  const authToken = localStorage.getItem("token");
  if (!authToken) {
    window.location.hash = "/login";
    return;
  }

  const lines = raw.split("\n");
  loading.value = true;
  error.value = null;
  tableData.value = [];

  try {
    const res = await fetch(`${apiBase}/api/kg_rag/ministerialize`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${authToken}`,
      },
      body: JSON.stringify({ lines }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      error.value = data.detail || data.error || "职事化失败";
      return;
    }
    const results = data.results || [];
    if (!results.length) {
      error.value = "没有可处理的非空条目";
      return;
    }
    let seq = 0;
    tableData.value = results.map((r) => {
      seq += 1;
      return mapResultRow(r, seq);
    });
    toastSuccess(`职事化完成，共 ${results.length} 条`);
  } catch (err) {
    error.value = err.message || "网络错误，请稍后重试";
  } finally {
    loading.value = false;
  }
}

async function rerunRow(row) {
  const authToken = localStorage.getItem("token");
  if (!authToken) {
    window.location.hash = "/login";
    return;
  }
  if (row.rerunning || loading.value) {
    return;
  }

  row.rerunning = true;
  try {
    const res = await fetch(`${apiBase}/api/kg_rag/ministerialize`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${authToken}`,
      },
      body: JSON.stringify({ lines: [row.original] }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      toastWarning(data.detail || data.error || "重跑失败");
      return;
    }
    const results = data.results || [];
    const hit = results.find((r) => r.index === row.index) || results[0];
    if (hit) {
      row.status = hit.status;
      row.result = hit.result;
      row.suggestion = hit.suggestion || "";
      row.editing = false;
    } else {
      toastWarning("未返回重跑结果");
    }
  } catch (err) {
    toastWarning(err.message || "重跑失败");
  } finally {
    row.rerunning = false;
  }
}

function deleteRow(row) {
  tableData.value = tableData.value.filter((r) => r.key !== row.key);
}

async function downloadDocx() {
  if (!tableData.value.length) {
    toastWarning("请先完成职事化");
    return;
  }
  const authToken = localStorage.getItem("token");
  if (!authToken) {
    window.location.hash = "/login";
    return;
  }

  const lines = tableData.value.map((row) => (row.result || "").trim()).filter(Boolean);
  if (!lines.length) {
    toastWarning("结果为空，无法下载");
    return;
  }

  downloading.value = true;
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
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      toastWarning(data.detail || data.error || "下载失败");
      return;
    }
    const b64 = data.docx_base64;
    const filename = data.filename || "纲目职事化.docx";
    if (!b64) {
      toastWarning(data.error || "未返回文件");
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
    toastSuccess(`已下载：${filename}`);
  } catch (err) {
    toastWarning(err.message || "下载失败");
  } finally {
    downloading.value = false;
  }
}
</script>

<template>
  <ToolsHeader title="纲目职事化" />
  <div class="box">
    <a-card>
      <p class="hint">填写标题（可选）并粘贴纲目正文，每行一条。系统将逐条检索职事书摘录并抽取贴近原文。</p>
      <a-divider :style="{ margin: '12px 0' }" />

      <div class="header-fields">
        <div class="header-row">
          <span class="field-label">第一行</span>
          <a-input v-model:value="headerSeries" placeholder="第一行（可选）" :disabled="loading" />
        </div>
        <div class="header-row">
          <span class="field-label">第二行</span>
          <a-input v-model:value="headerTopic" placeholder="第二行（可选）" :disabled="loading" />
        </div>
        <div class="header-row">
          <span class="field-label">第三行</span>
          <a-input v-model:value="headerChapter" placeholder="第三行（可选）" :disabled="loading" />
        </div>
        <div class="header-row">
          <span class="field-label">读经</span>
          <a-input v-model:value="headerReading" placeholder="读经（可选）" :disabled="loading" />
        </div>
      </div>

      <a-divider :style="{ margin: '16px 0' }" />

      <a-textarea
        v-model:value="inputText"
        :auto-size="{ minRows: 8, maxRows: 20 }"
        placeholder="粘贴纲目正文，每行一条"
        :disabled="loading"
      />

      <div class="actions">
        <a-button type="primary" :loading="loading" :disabled="loading" @click="startMinisterialize">
          <template v-if="loading"><LoadingOutlined /> 处理中…</template>
          <template v-else>开始职事化</template>
        </a-button>
      </div>

      <a-alert v-if="error" type="error" :message="error" show-icon class="err-alert" />
    </a-card>

    <a-card v-if="showResults" class="result-card">
      <div class="result-list">
        <div
          v-for="(row, idx) in tableData"
          :key="row.key"
          class="result-item"
          :class="{ 'result-item-last': idx === tableData.length - 1 }"
        >
          <div class="result-row-original">
            <span class="seq-num">{{ row.displaySeq }}.</span>
            <span class="original-text">{{ row.original }}</span>
          </div>
          <div class="result-row-inner-divider" />
          <div class="result-row-edit">
            <div style="display: flex; align-items: center; gap: 8px">
              <a-tag
                v-if="row.rerunning"
                color="default"
                class="status-tag"
              >
                处理中...
              </a-tag>
              <a-tag
                v-else
                :color="statusTag[row.status]?.color || 'default'"
                class="status-tag"
              >
                {{ statusTag[row.status]?.label || row.status }}
              </a-tag>
              <a-button
                type="link"
                size="small"
                class="rerun-btn"
                :disabled="row.rerunning || loading"
                @click="rerunRow(row)"
              >
                重跑
              </a-button>
              <a-button
                type="link"
                size="small"
                danger
                class="rerun-btn"
                :disabled="row.rerunning || loading"
                @click="deleteRow(row)"
              >
                删除
              </a-button>
            </div>
            <template v-if="row.status === 'minor' && !row.rerunning">
              <a-textarea
                v-model:value="row.result"
                class="result-input"
                :auto-size="{ minRows: 1 }"
              />
              <div
                v-if="row.suggestion"
                class="result-diff minor-suggestion"
                v-html="diffHighlight(row.original, row.suggestion)"
              />
            </template>
            <a-textarea
              v-else-if="row.status !== 'minor'"
              v-model:value="row.result"
              class="result-input"
              :auto-size="{ minRows: 1 }"
              :disabled="row.rerunning"
              @blur="row.editing = false"
            />
          </div>
        </div>
      </div>

      <div v-if="showStats" class="result-stats">
        <a-space :size="16" wrap>
          <span class="stat-item stat-original">原文 {{ stats.original }} 条</span>
          <span class="stat-item stat-minor">微调 {{ stats.minor }} 条</span>
          <span class="stat-item stat-replaced">已替换 {{ stats.replaced }} 条</span>
          <span class="stat-item stat-manual">人工处理 {{ stats.manual }} 条</span>
          <span class="stat-item stat-total">共 {{ stats.total }} 条</span>
        </a-space>
      </div>

      <div class="actions bottom-actions">
        <a-button type="primary" :loading="downloading" @click="downloadDocx">
          <DownloadOutlined /> 下载 docx
        </a-button>
      </div>
    </a-card>
  </div>
</template>

<style scoped>
.box {
  padding: 1em;
  max-width: 1200px;
  margin: 0 auto;
}
.hint {
  color: #666;
  margin: 0;
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
  color: #555;
  font-weight: 500;
}
.header-row :deep(.ant-input) {
  flex: 1;
}
.actions {
  margin-top: 16px;
}
.result-stats {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
}
.stat-item {
  font-size: 13px;
}
.stat-original {
  color: #389e0d;
}
.stat-minor {
  color: #d4b106;
}
.stat-replaced {
  color: #1677ff;
}
.stat-manual {
  color: #cf1322;
}
.stat-total {
  color: #8c8c8c;
}
.bottom-actions {
  margin-top: 20px;
}
.result-card {
  margin-top: 20px;
}
.err-alert {
  margin-top: 12px;
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
  flex: 0 0 auto;
  margin: 0;
}
.result-input {
  flex: 1;
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
.result-diff-clickable {
  cursor: pointer;
}
.result-diff-clickable:hover {
  border-color: #4096ff;
}
.result-diff :deep(.diff-del) {
  text-decoration: line-through;
  color: #dc3545;
}
.result-diff :deep(.diff-ins) {
  background: #d4edda;
  color: #155724;
}
.rerun-btn {
  flex: 0 0 auto;
  padding: 0 4px;
  margin: 0;
}
.minor-suggestion {
  background: #fafafa;
  border-radius: 6px;
  color: #595959;
  cursor: default;
}
</style>

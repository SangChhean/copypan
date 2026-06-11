<script setup>
import { ref, computed } from "vue";
import { useRouter } from "vue-router";
import { LeftOutlined } from "@ant-design/icons-vue";

const router = useRouter();
const toast = ref("");
const errorMsg = ref("");
const inputLine1 = ref("");
const inputLine2 = ref("");
const inputLine3 = ref("");
const inputScripture = ref("");
const inputText = ref("");
const loading = ref(false);
const cards = ref([]);
const editTexts = ref([]);
const sourceEdits = ref([]);
const diffSegments = ref([]);
const selectedFilter = ref("all");

const STATUS_META = {
  original: { label: "原文", tagClass: "tag-original" },
  adjusted: { label: "微调", tagClass: "tag-adjusted" },
  replaced: { label: "已替换", tagClass: "tag-replaced" },
  manual:   { label: "人工处理", tagClass: "tag-manual" },
};

const FILTER_KEYS = ["all", "original", "adjusted", "replaced", "manual"];
const FILTER_LABELS = {
  all: "全部",
  original: "原文",
  adjusted: "微调",
  replaced: "已替换",
  manual: "人工处理",
};

const visibleIndices = computed(() => {
  const out = [];
  cards.value.forEach((item, i) => {
    if (selectedFilter.value === "all" || item.status === selectedFilter.value) {
      out.push(i);
    }
  });
  return out;
});

function showToast(msg) {
  toast.value = msg;
  setTimeout(() => { if (toast.value === msg) toast.value = ""; }, 2500);
}

function statusCount(status) {
  if (status === "all") return cards.value.length;
  return cards.value.filter((c) => c.status === status).length;
}

function defaultEditText(item) {
  if (item.status === "original") return item.result;
  if (item.status === "adjusted") return item.original;
  if (item.status === "replaced") return item.result;
  return "";
}

function splitLines(text) {
  return text.replace(/\r\n/g, "\n").split("\n");
}

function formatError(data, status) {
  if (!data) return `请求失败（HTTP ${status}）`;
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail.map((d) => d.msg || JSON.stringify(d)).join("；");
  }
  return data.message || JSON.stringify(data);
}

function charDiffSegments(original, result) {
  const a = original || "";
  const b = result || "";
  if (!b) return [];
  const m = a.length;
  const n = b.length;
  const dp = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (a[i - 1] === b[j - 1]) dp[i][j] = dp[i - 1][j - 1] + 1;
      else dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }
  const matchedInB = new Set();
  let i = m;
  let j = n;
  while (i > 0 && j > 0) {
    if (a[i - 1] === b[j - 1]) {
      matchedInB.add(j - 1);
      i -= 1;
      j -= 1;
    } else if (dp[i - 1][j] >= dp[i][j - 1]) {
      i -= 1;
    } else {
      j -= 1;
    }
  }
  const segments = [];
  let buf = "";
  let changed = false;
  for (let k = 0; k < b.length; k++) {
    const isChanged = !matchedInB.has(k);
    if (!buf) {
      buf = b[k];
      changed = isChanged;
    } else if (isChanged === changed) {
      buf += b[k];
    } else {
      segments.push({ text: buf, changed });
      buf = b[k];
      changed = isChanged;
    }
  }
  if (buf) segments.push({ text: buf, changed });
  return segments;
}

function buildHeaderLines() {
  const lines = [];
  if (inputLine1.value.trim()) lines.push(inputLine1.value.trim());
  if (inputLine2.value.trim()) lines.push(inputLine2.value.trim());
  if (inputLine3.value.trim()) lines.push(inputLine3.value.trim());
  if (inputScripture.value) lines.push(inputScripture.value);
  return lines;
}

function lineWithSource(idx, withSource) {
  const line = editTexts.value[idx] ?? "";
  if (!withSource) return line;
  const item = cards.value[idx];
  if (!item) return line;
  if (item.status === "original" || item.status === "adjusted") {
    if (item.source) return `${line}（${item.source}）`;
    return line;
  }
  if (item.status === "replaced" || item.status === "manual") {
    const src = (sourceEdits.value[idx] ?? "").trim();
    if (src) return `${line}（${src}）`;
  }
  return line;
}

async function startProcess() {
  errorMsg.value = "";
  const lines = splitLines(inputText.value).filter((l) => l.trim() !== "");
  if (lines.length === 0) {
    showToast("请先输入纲目内容");
    return;
  }

  loading.value = true;
  cards.value = [];
  editTexts.value = [];
  sourceEdits.value = [];
  diffSegments.value = [];
  selectedFilter.value = "all";

  try {
    const res = await fetch("/api/testa/ministerialize/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lines }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      errorMsg.value = formatError(data, res.status);
      return;
    }

    const results = data.results || [];
    cards.value = results;
    results.forEach((item, i) => {
      editTexts.value[i] = defaultEditText(item);
      sourceEdits.value[i] = (item.status === "replaced" || item.status === "manual")
        ? (item.source || "")
        : "";
      diffSegments.value[i] = item.status === "adjusted"
        ? charDiffSegments(item.original, item.result)
        : [];
    });
  } catch (e) {
    errorMsg.value = e.message || "网络请求失败";
  } finally {
    loading.value = false;
  }
}

function copySuggestText(idx) {
  const text = cards.value[idx]?.result || "";
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => showToast("已复制职事化结果"));
}

function copyAll(withSource) {
  if (cards.value.length === 0) {
    showToast("暂无结果可复制");
    return;
  }
  const parts = [...buildHeaderLines()];
  cards.value.forEach((_, i) => {
    parts.push(lineWithSource(i, withSource));
  });
  navigator.clipboard.writeText(parts.join("\n")).then(() => {
    showToast(withSource ? "已复制全部加出处结果" : "已复制全部结果");
  });
}

function statusMeta(status) {
  return STATUS_META[status] || { label: status, tagClass: "tag-manual" };
}
</script>

<template>
  <div class="page">
    <div v-if="toast" class="toast">{{ toast }}</div>

    <div class="header">
      <a-button type="text" class="back-btn" @click="router.back()">
        <template #icon><LeftOutlined /></template>
      </a-button>
      <span class="header-title">纲目职事化</span>
    </div>

    <div class="card">
      <div class="field">
        <label class="field-label">第一行</label>
        <a-input v-model:value="inputLine1" placeholder="可选" :disabled="loading" />
      </div>
      <div class="field">
        <label class="field-label">第二行</label>
        <a-input v-model:value="inputLine2" placeholder="可选" :disabled="loading" />
      </div>
      <div class="field">
        <label class="field-label">第三行</label>
        <a-input v-model:value="inputLine3" placeholder="可选" :disabled="loading" />
      </div>
      <div class="field">
        <label class="field-label">读经</label>
        <a-input v-model:value="inputScripture" placeholder="如：读经：…" :disabled="loading" />
      </div>

      <div class="field">
        <label class="field-label">纲目输入</label>
        <a-textarea
          v-model:value="inputText"
          placeholder="每行一条纲目，最多 200 行"
          :disabled="loading"
          :auto-size="{ minRows: 8, maxRows: 16 }"
        />
      </div>

      <div v-if="loading" class="loading-hint">职事化中…</div>
      <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>

      <div class="action-row">
        <a-button
          type="primary"
          class="start-btn"
          :loading="loading"
          :disabled="loading"
          @click="startProcess"
        >
          {{ loading ? "职事化中…" : "开始职事化" }}
        </a-button>
      </div>
    </div>

    <div v-if="cards.length > 0" class="card filter-card">
      <div class="filter-row">
        <button
          v-for="key in FILTER_KEYS"
          :key="key"
          type="button"
          class="filter-btn"
          :class="{ active: selectedFilter === key }"
          @click="selectedFilter = key"
        >
          {{ FILTER_LABELS[key] }}({{ statusCount(key) }})
        </button>
      </div>
    </div>

    <div
      v-for="idx in visibleIndices"
      :key="idx"
      class="card result-card"
    >
      <div class="result-head">
        <span class="status-tag" :class="statusMeta(cards[idx].status).tagClass">
          {{ statusMeta(cards[idx].status).label }}
        </span>
      </div>

      <div class="field">
        <label class="field-label">原文</label>
        <div class="readonly-line">{{ cards[idx].original }}</div>
      </div>

      <div class="field">
        <label class="field-label">编辑结果</label>
        <a-textarea
          v-model:value="editTexts[idx]"
          :disabled="loading"
          :auto-size="{ minRows: 2, maxRows: 8 }"
          placeholder="可在此编辑最终结果"
        />
      </div>

      <div v-if="cards[idx].status === 'replaced' || cards[idx].status === 'manual'" class="field">
        <label class="field-label">出处</label>
        <a-input
          v-model:value="sourceEdits[idx]"
          :disabled="loading"
          placeholder="书目出处，可复制时附在行末"
        />
      </div>

      <div v-if="cards[idx].status === 'adjusted'" class="field">
        <div class="suggest-head">
          <label class="field-label suggest-label">职事化结果（对照）</label>
          <button type="button" class="mini-copy-btn" @click="copySuggestText(idx)">
            复制
          </button>
        </div>
        <div class="readonly-line suggest-line">
          <template v-for="(seg, si) in diffSegments[idx]" :key="si">
            <span :class="{ 'diff-changed': seg.changed }">{{ seg.text }}</span>
          </template>
        </div>
      </div>
    </div>

    <div v-if="cards.length > 0" class="card copy-card">
      <a-button type="primary" class="copy-all-btn" @click="copyAll(false)">
        复制全部结果
      </a-button>
      <a-button type="primary" class="copy-all-btn" @click="copyAll(true)">
        复制全部加出处结果
      </a-button>
    </div>
  </div>
</template>

<style scoped>
.toast {
  position: fixed;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: #0d9488;
  color: #fff;
  padding: 8px 24px;
  border-radius: 20px;
  font-size: 14px;
  z-index: 9999;
  pointer-events: none;
}
.page {
  min-height: 100vh;
  background: #f5f5f5;
  padding-bottom: 40px;
}
.header {
  background: linear-gradient(135deg, #0f766e 0%, #14b8a6 100%);
  padding: 0 20px;
  height: 52px;
  display: flex;
  align-items: center;
  position: relative;
  box-shadow: 0 2px 8px rgba(15, 118, 110, 0.35);
}
.back-btn {
  color: #ccfbf1;
  font-size: 18px;
  position: absolute;
  left: 12px;
}
.header-title {
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  flex: 1;
  text-align: center;
  letter-spacing: 0.5px;
}
.card {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  margin: 12px 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
.field { margin-bottom: 14px; }
.field:last-child { margin-bottom: 0; }
.field-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: #333;
  margin-bottom: 8px;
}
.readonly-line {
  font-size: 14px;
  line-height: 1.6;
  color: #434343;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 8px 12px;
  white-space: pre-wrap;
  word-break: break-word;
}
.suggest-line {
  background: #f0fdfa;
  border-color: #99f6e4;
  color: #115e59;
}
.diff-changed {
  background: #ffedd5;
  color: #c2410c;
  text-decoration: underline;
  text-decoration-color: #fb923c;
  border-radius: 2px;
}
.suggest-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.suggest-label {
  margin-bottom: 0;
}
.mini-copy-btn {
  border: 1px solid #99f6e4;
  background: #fff;
  color: #0f766e;
  border-radius: 4px;
  font-size: 12px;
  padding: 2px 10px;
  cursor: pointer;
}
.mini-copy-btn:hover {
  background: #f0fdfa;
}
.loading-hint {
  text-align: center;
  color: #0f766e;
  font-size: 14px;
  margin-bottom: 12px;
}
.error-msg {
  color: #cf1322;
  font-size: 13px;
  margin-bottom: 12px;
  line-height: 1.5;
}
.action-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
.start-btn {
  background: #0d9488;
  border-color: #0d9488;
}
.start-btn:hover,
.start-btn:focus {
  background: #0f766e !important;
  border-color: #0f766e !important;
}
.filter-card {
  padding-top: 12px;
  padding-bottom: 12px;
}
.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.filter-btn {
  border: 1px solid #d9d9d9;
  background: #fff;
  color: #595959;
  border-radius: 16px;
  font-size: 13px;
  padding: 4px 12px;
  cursor: pointer;
}
.filter-btn.active {
  background: #0d9488;
  border-color: #0d9488;
  color: #fff;
}
.result-head {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}
.status-tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}
.tag-original {
  background: #f6ffed;
  color: #389e0d;
  border: 1px solid #b7eb8f;
}
.tag-adjusted {
  background: #e6f4ff;
  color: #0958d9;
  border: 1px solid #91caff;
}
.tag-replaced {
  background: #fff7e6;
  color: #d46b08;
  border: 1px solid #ffd591;
}
.tag-manual {
  background: #fff1f0;
  color: #cf1322;
  border: 1px solid #ffa39e;
}
.copy-card {
  display: flex;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}
.copy-all-btn {
  background: #0d9488;
  border-color: #0d9488;
  min-width: 140px;
}
.copy-all-btn:hover,
.copy-all-btn:focus {
  background: #0f766e !important;
  border-color: #0f766e !important;
}
</style>

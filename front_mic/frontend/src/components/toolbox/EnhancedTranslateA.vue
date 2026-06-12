<script setup>
import { ref, computed } from "vue";
import { useRouter } from "vue-router";
import { LeftOutlined, DownOutlined, RightOutlined } from "@ant-design/icons-vue";

const apiBase = "";
const router = useRouter();

const inputText = ref("");
const loading = ref(false);
const errorMsg = ref("");
const rows = ref([]);
const resultText = ref("");
const costUsd = ref(null);
const hasResult = ref(false);

const enEdits = ref([]);
const savedBaseline = ref([]);
const saveStates = ref([]);
const refOpen = ref([]);
const selectedFilter = ref("all");

const FILTER_KEYS = ["all", "pool", "retrieved", "none"];
const FILTER_LABELS = {
  all: "全部",
  pool: "直接引用",
  retrieved: "参考翻译",
  none: "无匹配",
};

const STATUS_META = {
  pool: { label: "直接引用", color: "#52c41a", bg: "#f6ffed", border: "#b7eb8f" },
  retrieved: { label: "参考翻译", color: "#1890ff", bg: "#e6f4ff", border: "#91caff" },
  none: { label: "无匹配", color: "#8c8c8c", bg: "#f5f5f5", border: "#d9d9d9" },
};

const stats = computed(() => {
  const list = rows.value;
  const total = list.length;
  const direct = list.filter((r) => r.status === "pool").length;
  const reference = list.filter((r) => r.status === "retrieved").length;
  const none = list.filter((r) => r.status === "none").length;
  const poolNew = list.filter(
    (r) =>
      (r.status === "retrieved" || r.status === "none") &&
      (r.en || "").trim() &&
      !r.error,
  ).length;
  return { total, direct, reference, none, poolNew };
});

const visibleRows = computed(() => {
  const list = rows.value;
  if (selectedFilter.value === "all") {
    return list.map((row, idx) => ({ row, idx }));
  }
  return list
    .map((row, idx) => ({ row, idx }))
    .filter(({ row }) => row.status === selectedFilter.value);
});

function formatCost(val) {
  if (val == null || Number.isNaN(Number(val))) return "—";
  return `$${Number(val).toFixed(4)}`;
}

function formatError(data, status) {
  if (!data) return `请求失败（HTTP ${status}）`;
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail.map((d) => d.msg || JSON.stringify(d)).join("；");
  }
  return data.message || JSON.stringify(data);
}

function statusMeta(status) {
  return STATUS_META[status] || STATUS_META.none;
}

function splitNonEmptyLines(text) {
  return text.replace(/\r\n/g, "\n").split("\n").map((l) => l.trim()).filter(Boolean);
}

function assignRows(apiRows) {
  selectedFilter.value = "all";
  rows.value = apiRows.map((item, i) => ({ ...item, lineNo: i + 1 }));
  enEdits.value = [];
  savedBaseline.value = [];
  saveStates.value = [];
  refOpen.value = [];
  apiRows.forEach((item, i) => {
    enEdits.value[i] = item.en || "";
    savedBaseline.value[i] = item.en || "";
    saveStates.value[i] = null;
    refOpen.value[i] = false;
  });
}

function filterCount(key) {
  if (key === "all") return rows.value.length;
  return rows.value.filter((r) => r.status === key).length;
}

async function startTranslate() {
  errorMsg.value = "";
  const lines = splitNonEmptyLines(inputText.value);
  if (lines.length === 0) return;
  if (lines.length > 200) {
    errorMsg.value = "超过 200 行，请删减后重试";
    return;
  }

  loading.value = true;
  hasResult.value = false;
  rows.value = [];
  resultText.value = "";
  costUsd.value = null;

  try {
    const res = await fetch(`${apiBase}/api/testa/enhanced-translate/translate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: inputText.value }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      errorMsg.value = formatError(data, res.status);
      return;
    }

    assignRows(Array.isArray(data.rows) ? data.rows : []);
    resultText.value = data.result || "";
    costUsd.value = data.cost_usd ?? 0;
    hasResult.value = true;
  } catch (e) {
    errorMsg.value = e.message || "网络请求失败";
  } finally {
    loading.value = false;
  }
}

function copyAll() {
  if (!resultText.value) return;
  navigator.clipboard.writeText(resultText.value).then(() => {});
}

function toggleRef(idx) {
  refOpen.value[idx] = !refOpen.value[idx];
}

async function onEnBlur(idx) {
  const row = rows.value[idx];
  if (!row || row.error) return;

  const current = (enEdits.value[idx] ?? "").trim();
  const baseline = (savedBaseline.value[idx] ?? "").trim();
  if (current === baseline) return;

  saveStates.value[idx] = { type: "pending" };

  try {
    const res = await fetch(`${apiBase}/api/testa/enhanced-translate/update_translation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        original_line: row.line,
        new_translation: current,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      saveStates.value[idx] = {
        type: "error",
        detail: formatError(data, res.status),
      };
      return;
    }
    if (data.success) {
      savedBaseline.value[idx] = current;
      enEdits.value[idx] = current;
      rows.value[idx] = { ...row, en: current };
      saveStates.value[idx] = { type: "success" };
      setTimeout(() => {
        if (saveStates.value[idx]?.type === "success") {
          saveStates.value[idx] = null;
        }
      }, 2500);
    } else {
      saveStates.value[idx] = {
        type: "error",
        detail: "语料库中未找到该句，无法写回",
      };
    }
  } catch (e) {
    saveStates.value[idx] = {
      type: "error",
      detail: e.message || "网络请求失败",
    };
  }
}
</script>

<template>
  <div class="page">
    <div class="header">
      <a-button type="text" class="back-btn" @click="router.back()">
        <template #icon><LeftOutlined /></template>
      </a-button>
      <span class="header-title">增强式翻译</span>
    </div>

    <div class="body">
      <div class="card input-card">
        <a-textarea
          v-model:value="inputText"
          placeholder="粘贴纲目，每行一条，最多 200 行"
          :disabled="loading"
          :auto-size="{ minRows: 8, maxRows: 16 }"
          class="input-area"
        />
        <div class="action-row">
          <a-button
            type="primary"
            class="start-btn"
            :disabled="loading || !splitNonEmptyLines(inputText).length"
            :loading="loading"
            @click="startTranslate"
          >
            开始翻译
          </a-button>
          <span v-if="loading" class="loading-hint">
            翻译中，行数多时约 20～60 秒…
          </span>
        </div>
        <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>
      </div>

      <template v-if="hasResult">
        <div class="card">
          <div class="section-title">统计摘要</div>
          <div class="summary-grid">
            <div class="summary-item">
              <span class="summary-label">总行数</span>
              <span class="summary-value">{{ stats.total }}</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">直接引用</span>
              <span class="summary-value stat-green">{{ stats.direct }}</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">参考翻译</span>
              <span class="summary-value stat-blue">{{ stats.reference }}</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">无匹配</span>
              <span class="summary-value stat-gray">{{ stats.none }}</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">Pool 新增</span>
              <span class="summary-value">{{ stats.poolNew }}</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">本次费用</span>
              <span class="summary-value">{{ formatCost(costUsd) }}</span>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="section-title-row">
            <span class="section-title">英文全文</span>
            <button type="button" class="link-btn" @click="copyAll">复制全部</button>
          </div>
          <div class="result-scroll">
            <pre class="result-text">{{ resultText }}</pre>
          </div>
        </div>

        <div class="card">
          <div class="section-title-row filter-head">
            <span class="section-title">逐行结果</span>
            <div class="filter-tags">
              <button
                v-for="key in FILTER_KEYS"
                :key="key"
                type="button"
                class="filter-tag"
                :class="[
                  `filter-${key}`,
                  { active: selectedFilter === key },
                ]"
                @click="selectedFilter = key"
              >
                {{ FILTER_LABELS[key] }} ({{ filterCount(key) }})
              </button>
            </div>
          </div>

          <div
            v-for="{ row, idx } in visibleRows"
            :key="idx"
            class="line-card"
          >
            <div class="line-head">
              <span class="line-no">{{ row.lineNo }}</span>
              <span
                class="status-pill"
                :style="{
                  color: statusMeta(row.status).color,
                  background: statusMeta(row.status).bg,
                  borderColor: statusMeta(row.status).border,
                }"
              >
                {{ statusMeta(row.status).label }}
              </span>
            </div>
            <div class="zh-line">{{ row.line }}</div>

            <div v-if="row.error" class="translate-fail">翻译失败</div>

            <a-textarea
              v-else
              v-model:value="enEdits[idx]"
              class="en-edit"
              :class="{
                'en-saved': saveStates[idx]?.type === 'success',
                'en-failed': saveStates[idx]?.type === 'error',
              }"
              :auto-size="{ minRows: 2, maxRows: 8 }"
              :disabled="loading"
              @blur="onEnBlur(idx)"
            />

            <div v-if="saveStates[idx]?.type === 'success'" class="save-hint success">
              已写回语料库 ✓
            </div>
            <div v-else-if="saveStates[idx]?.type === 'error'" class="save-hint error">
              写回失败：{{ saveStates[idx].detail }}
            </div>

            <div v-if="row.status === 'retrieved' && row.ref" class="ref-block">
              <button type="button" class="ref-toggle" @click="toggleRef(idx)">
                <RightOutlined v-if="!refOpen[idx]" class="ref-icon" />
                <DownOutlined v-else class="ref-icon" />
                参考语料
              </button>
              <div v-if="refOpen[idx]" class="ref-body">
                <div v-if="row.ref.source" class="ref-source">
                  出处：{{ row.ref.source }}
                </div>
                <div v-if="row.ref.text" class="ref-part">
                  <span class="ref-label">中文</span>
                  <div class="ref-text">{{ row.ref.text }}</div>
                </div>
                <div class="ref-part">
                  <span class="ref-label">英文</span>
                  <div v-if="row.ref.en" class="ref-text">{{ row.ref.en }}</div>
                  <div v-else class="ref-en-missing">该段语料无英文对照</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f5f5;
}
.header {
  background: #8b5e34;
  padding: 0 20px;
  height: 52px;
  display: flex;
  align-items: center;
  position: relative;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(139, 94, 52, 0.35);
}
.back-btn {
  color: #f5e6d8;
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
.body {
  flex: 1;
  padding: 16px;
  max-width: 960px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
}
.card {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}
.input-area {
  font-size: 14px;
}
.action-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.start-btn {
  background: #8b5e34;
  border-color: #8b5e34;
  min-width: 108px;
}
.start-btn:hover:not(:disabled),
.start-btn:focus:not(:disabled) {
  background: #734d2b !important;
  border-color: #734d2b !important;
}
.start-btn:disabled {
  background: #c4a882;
  border-color: #c4a882;
  color: rgba(255, 255, 255, 0.85);
}
.loading-hint {
  font-size: 13px;
  color: #8b5e34;
}
.error-msg {
  margin-top: 10px;
  color: #cf1322;
  font-size: 13px;
  line-height: 1.5;
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #262626;
  margin-bottom: 12px;
}
.section-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.section-title-row .section-title {
  margin-bottom: 0;
}
.filter-head {
  flex-wrap: wrap;
  gap: 10px;
}
.filter-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}
.filter-tag {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 4px;
  cursor: pointer;
  background: #fff;
  transition: all 0.2s;
  user-select: none;
}
.filter-tag.filter-all {
  color: #595959;
  border: 1px solid #d9d9d9;
}
.filter-tag.filter-all.active {
  color: #fff;
  background: #595959;
  border-color: #595959;
}
.filter-tag.filter-pool {
  color: #52c41a;
  border: 1px solid #b7eb8f;
}
.filter-tag.filter-pool.active {
  color: #fff;
  background: #52c41a;
  border-color: #52c41a;
}
.filter-tag.filter-retrieved {
  color: #1890ff;
  border: 1px solid #91caff;
}
.filter-tag.filter-retrieved.active {
  color: #fff;
  background: #1890ff;
  border-color: #1890ff;
}
.filter-tag.filter-none {
  color: #8c8c8c;
  border: 1px solid #d9d9d9;
}
.filter-tag.filter-none.active {
  color: #fff;
  background: #8c8c8c;
  border-color: #8c8c8c;
}
.link-btn {
  border: none;
  background: none;
  color: #8b5e34;
  font-size: 13px;
  cursor: pointer;
  padding: 0 4px;
}
.link-btn:hover {
  text-decoration: underline;
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px 16px;
}
.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
}
.summary-label {
  font-size: 12px;
  color: #8c8c8c;
}
.summary-value {
  font-size: 18px;
  font-weight: 600;
  color: #262626;
}
.stat-green {
  color: #52c41a;
}
.stat-blue {
  color: #1890ff;
}
.stat-gray {
  color: #8c8c8c;
}
.result-scroll {
  max-height: 360px;
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
.line-card {
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 12px;
  background: #fff;
}
.line-card:last-child {
  margin-bottom: 0;
}
.line-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.line-no {
  font-size: 12px;
  color: #8c8c8c;
  font-weight: 600;
  min-width: 1.5em;
}
.status-pill {
  display: inline-block;
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 12px;
  border: 1px solid;
  font-weight: 500;
}
.zh-line {
  font-size: 14px;
  color: #262626;
  line-height: 1.6;
  margin-bottom: 10px;
  word-break: break-word;
}
.translate-fail {
  color: #cf1322;
  font-size: 14px;
  font-weight: 500;
  padding: 8px 0;
}
.en-edit {
  font-size: 14px;
}
.en-edit.en-saved {
  border-color: #52c41a !important;
  box-shadow: 0 0 0 2px rgba(82, 196, 26, 0.12);
}
.en-edit.en-failed {
  border-color: #ff4d4f !important;
  box-shadow: 0 0 0 2px rgba(255, 77, 79, 0.12);
}
.save-hint {
  margin-top: 6px;
  font-size: 12px;
}
.save-hint.success {
  color: #52c41a;
}
.save-hint.error {
  color: #cf1322;
  line-height: 1.5;
}
.ref-block {
  margin-top: 10px;
  border-top: 1px dashed #e8e8e8;
  padding-top: 8px;
}
.ref-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: none;
  background: none;
  color: #8b5e34;
  font-size: 13px;
  cursor: pointer;
  padding: 0;
}
.ref-icon {
  font-size: 11px;
}
.ref-body {
  margin-top: 8px;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 6px;
  border: 1px solid #f0f0f0;
}
.ref-source {
  font-size: 12px;
  color: #8c8c8c;
  line-height: 1.5;
  margin-bottom: 10px;
}
.ref-en-missing {
  font-size: 13px;
  color: #bfbfbf;
  line-height: 1.6;
  font-style: italic;
}
.ref-part + .ref-part {
  margin-top: 10px;
}
.ref-label {
  display: block;
  font-size: 11px;
  color: #8c8c8c;
  margin-bottom: 4px;
}
.ref-text {
  font-size: 13px;
  line-height: 1.6;
  color: #434343;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>

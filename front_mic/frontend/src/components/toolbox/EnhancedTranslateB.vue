<script setup>
import { ref, computed, nextTick, watch } from "vue";
import { ArrowLeftOutlined } from "@ant-design/icons-vue";

const apiBase = "";

const inputText = ref("");
const loading = ref(false);
const rows = ref([]);
const costUsd = ref(0);
const activeFilter = ref("all");
const copyBtnText = ref("复制全部");
const rowListRef = ref(null);

const goToolbox = () => {
  window.location.hash = "/tools";
};

const isDirectQuote = (status) => status === "pool" || status === "exact";

const statusCounts = computed(() => {
  const list = rows.value;
  return {
    all: list.length,
    pool: list.filter((r) => isDirectQuote(r.status)).length,
    retrieved: list.filter((r) => r.status === "retrieved").length,
    none: list.filter((r) => r.status === "none").length,
  };
});

const filteredRows = computed(() =>
  rows.value
    .map((row, index) => ({ row, lineNo: index + 1 }))
    .filter(({ row }) => {
      if (activeFilter.value === "all") return true;
      if (activeFilter.value === "pool") return isDirectQuote(row.status);
      return row.status === activeFilter.value;
    })
);

const fullEnglishText = computed(() =>
  rows.value.map((r) => r.en || "").join("\n")
);

const statusLabel = (status) => {
  if (status === "pool") return "直接引用·笔记本";
  if (status === "exact") return "直接引用·定译";
  if (status === "retrieved") return "参考翻译";
  return "无匹配";
};

function adjustRowHeight(el) {
  const target = el?.target || el;
  if (!target) return;
  target.style.height = "auto";
  target.style.height = `${target.scrollHeight}px`;
}

function adjustAllRowHeights() {
  nextTick(() => {
    const root = rowListRef.value;
    if (!root) return;
    root.querySelectorAll(".en-textarea").forEach((ta) => adjustRowHeight(ta));
  });
}

function setFilter(filter) {
  activeFilter.value = filter;
}

watch(activeFilter, () => {
  adjustAllRowHeights();
});

function clearAll() {
  inputText.value = "";
  rows.value = [];
  costUsd.value = 0;
  activeFilter.value = "all";
}

async function startTranslate() {
  if (!inputText.value.trim()) {
    alert("请先粘贴纲目内容");
    return;
  }

  loading.value = true;
  try {
    const res = await fetch(`${apiBase}/api/testb/enhanced-translate/translate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: inputText.value }),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      alert(data.detail || `请求失败 (${res.status})`);
      return;
    }

    const data = await res.json();
    rows.value = (data.rows || []).map((r) => ({
      ...r,
      saving: false,
      saved: false,
      refOpen: false,
    }));
    costUsd.value = data.cost_usd ?? 0;
    activeFilter.value = "all";
    adjustAllRowHeights();
  } catch {
    alert("请求失败，请检查后端是否运行");
  } finally {
    loading.value = false;
  }
}

async function copyAll() {
  const text = fullEnglishText.value;
  if (!text.trim()) return;
  try {
    await navigator.clipboard.writeText(text);
    copyBtnText.value = "已复制 ✓";
    setTimeout(() => {
      copyBtnText.value = "复制全部";
    }, 2000);
  } catch {
    alert("复制失败");
  }
}

function onEnInput(row, event) {
  row.saved = false;
  adjustRowHeight(event);
}

async function saveRow(row) {
  row.saving = true;
  try {
    const res = await fetch(
      `${apiBase}/api/testb/enhanced-translate/update_translation`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          original_line: row.line,
          new_translation: row.en,
        }),
      }
    );
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.success) {
      row.saved = true;
    } else {
      alert("保存失败");
    }
  } catch {
    alert("保存失败");
  } finally {
    row.saving = false;
  }
}

function toggleRef(row) {
  row.refOpen = !row.refOpen;
}
</script>

<template>
  <div class="et-page">
    <div class="et-header">
      <div class="back-btn" title="返回工具箱" @click="goToolbox">
        <ArrowLeftOutlined />
        <span>返回</span>
      </div>
      <h1 class="page-title">增强式翻译测试（test_B）</h1>
    </div>

    <!-- 中文原文区 -->
    <section class="section">
      <div class="section-label">中文原文</div>
      <textarea
        v-model="inputText"
        class="input-area"
        placeholder="粘贴纲目，每行一条，最多 200 行"
        :disabled="loading"
      />
      <div class="btn-row">
        <button
          type="button"
          class="primary-btn"
          :disabled="loading"
          @click="startTranslate"
        >
          开始翻译
        </button>
        <button type="button" class="ghost-btn" :disabled="loading" @click="clearAll">
          清空
        </button>
        <span v-if="loading" class="loading-hint">翻译中，行数多时约 20～60 秒…</span>
      </div>
    </section>

    <!-- 英文全文区 -->
    <section class="section">
      <div class="section-head">
        <div class="section-label">英文全文</div>
        <button type="button" class="ghost-btn" :disabled="!rows.length" @click="copyAll">
          {{ copyBtnText }}
        </button>
      </div>
      <div class="result-box">
        <div v-if="rows.length" class="en-lines">
          <div v-for="(row, i) in rows" :key="'en-' + i" class="en-line">
            {{ row.en }}
          </div>
        </div>
        <div v-else class="placeholder">翻译结果将显示在这里</div>
      </div>
    </section>

    <!-- 状态筛选 -->
    <div v-if="rows.length" class="filter-row">
      <button
        type="button"
        class="filter-pill"
        :class="{ active: activeFilter === 'all', 'pill-all': true }"
        @click="setFilter('all')"
      >
        全部 ({{ statusCounts.all }})
      </button>
      <button
        type="button"
        class="filter-pill"
        :class="{ active: activeFilter === 'pool', 'pill-pool': true }"
        @click="setFilter('pool')"
      >
        直接引用 ({{ statusCounts.pool }})
      </button>
      <button
        type="button"
        class="filter-pill"
        :class="{ active: activeFilter === 'retrieved', 'pill-retrieved': true }"
        @click="setFilter('retrieved')"
      >
        参考翻译 ({{ statusCounts.retrieved }})
      </button>
      <button
        type="button"
        class="filter-pill"
        :class="{ active: activeFilter === 'none', 'pill-none': true }"
        @click="setFilter('none')"
      >
        无匹配 ({{ statusCounts.none }})
      </button>
    </div>

    <!-- 逐行结果 -->
    <div v-if="filteredRows.length" ref="rowListRef" class="row-list">
      <div v-for="{ row, lineNo } in filteredRows" :key="lineNo" class="row-card">
        <div class="row-head">
          <span class="line-no">第 {{ lineNo }} 行</span>
          <span class="status-tag" :class="'tag-' + row.status">
            {{ statusLabel(row.status) }}
          </span>
          <span class="zh-line">{{ row.line }}</span>
          <button
            v-if="(row.status === 'retrieved' || row.status === 'exact') && row.ref"
            type="button"
            class="ref-toggle"
            @click="toggleRef(row)"
          >
            参考语料 {{ row.refOpen ? "▴" : "▾" }}
          </button>
        </div>

        <div
          v-if="(row.status === 'retrieved' || row.status === 'exact') && row.ref && row.refOpen"
          class="ref-block"
        >
          <div>原文: {{ row.ref.text }}</div>
          <div>定译: {{ row.ref.en }}</div>
        </div>

        <div class="en-edit-row">
          <textarea
            v-model="row.en"
            class="en-textarea"
            rows="1"
            :disabled="row.saving"
            @input="onEnInput(row, $event)"
          />
          <button
            type="button"
            class="save-btn"
            :class="{ saved: row.saved }"
            :disabled="row.saving"
            @click="saveRow(row)"
          >
            {{ row.saving ? "保存中…" : row.saved ? "已保存 ✓" : "保存" }}
          </button>
        </div>
        <div v-if="row.saved" class="saved-hint">
          ✓ 修订已写回笔记本，下次此行将直接命中
        </div>
      </div>
    </div>

    <!-- 底部信息条 -->
    <div v-if="rows.length" class="footer-bar">
      <span>本次花费 ${{ costUsd.toFixed(4) }}</span>
      <span>
        共 {{ statusCounts.all }} 行：
        <span class="c-pool">绿 {{ statusCounts.pool }}</span>
        /
        <span class="c-retrieved">蓝 {{ statusCounts.retrieved }}</span>
        /
        <span class="c-none">灰 {{ statusCounts.none }}</span>
      </span>
    </div>
  </div>
</template>

<style scoped>
.et-page {
  max-width: 820px;
  margin: 0 auto;
  padding: 16px;
  min-height: 100vh;
  background: #fffbeb;
  color: #412402;
  box-sizing: border-box;
}

.et-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}

.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border-radius: 6px;
  border: 1px solid #fac775;
  background: #faeeda;
  color: #92400e;
  cursor: pointer;
  font-size: 14px;
  flex-shrink: 0;
}

.back-btn:hover {
  background: #fde68a;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #92400e;
}

.section {
  margin-bottom: 20px;
}

.section-label {
  font-weight: 600;
  font-size: 14px;
  color: #92400e;
  margin-bottom: 8px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.section-head .section-label {
  margin-bottom: 0;
}

.input-area {
  width: 100%;
  height: 40vh;
  padding: 12px;
  border: 1px solid #fac775;
  border-radius: 8px;
  font-size: 15px;
  line-height: 1.6;
  color: #412402;
  background: #fff;
  resize: none;
  box-sizing: border-box;
  overflow-y: auto;
  font-family: inherit;
}

.input-area:focus {
  outline: none;
  border-color: #d97706;
}

.btn-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.primary-btn {
  padding: 8px 20px;
  border: none;
  border-radius: 8px;
  background: #d97706;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.primary-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.ghost-btn {
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid #fac775;
  background: #fff;
  color: #92400e;
  cursor: pointer;
  font-size: 13px;
}

.ghost-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.ghost-btn:hover:not(:disabled) {
  background: #faeeda;
}

.loading-hint {
  font-size: 13px;
  color: #b45309;
}

.result-box {
  height: 40vh;
  border: 1px solid #fac775;
  border-radius: 8px;
  background: #fff;
  overflow-y: auto;
  padding: 12px;
  box-sizing: border-box;
}

.placeholder {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #a8a29e;
  font-size: 14px;
}

.en-lines {
  line-height: 1.7;
  font-size: 15px;
  white-space: pre-wrap;
  word-break: break-word;
}

.en-line {
  margin-bottom: 4px;
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.filter-pill {
  padding: 4px 14px;
  border-radius: 999px;
  font-size: 13px;
  cursor: pointer;
  border: 1px solid;
  background: #fff;
}

.pill-all {
  border-color: #d97706;
  color: #d97706;
}
.pill-all.active {
  background: #d97706;
  color: #fff;
}

.pill-pool {
  border-color: #52c41a;
  color: #52c41a;
}
.pill-pool.active {
  background: #52c41a;
  color: #fff;
}

.pill-retrieved {
  border-color: #1890ff;
  color: #1890ff;
}
.pill-retrieved.active {
  background: #1890ff;
  color: #fff;
}

.pill-none {
  border-color: #8c8c8c;
  color: #8c8c8c;
}
.pill-none.active {
  background: #8c8c8c;
  color: #fff;
}

.row-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}

.row-card {
  background: #fff;
  border: 1px solid #fac775;
  border-radius: 10px;
  padding: 14px;
}

.row-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 14px;
  line-height: 1.5;
}

.line-no {
  color: #a8a29e;
  flex-shrink: 0;
}

.status-tag {
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 12px;
  flex-shrink: 0;
}

.tag-pool,
.tag-exact {
  background: #f6ffed;
  color: #389e0d;
}

.tag-retrieved {
  background: #e6f7ff;
  color: #0958d9;
}

.tag-none {
  background: #f5f5f5;
  color: #595959;
}

.zh-line {
  flex: 1;
  min-width: 0;
  word-break: break-word;
  color: #412402;
}

.ref-toggle {
  border: none;
  background: none;
  color: #1890ff;
  cursor: pointer;
  font-size: 13px;
  padding: 0;
  flex-shrink: 0;
}

.ref-block {
  background: #e6f7ff;
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 10px;
  font-size: 12px;
  line-height: 1.6;
  color: #0958d9;
  word-break: break-word;
}

.en-edit-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.en-textarea {
  flex: 1;
  min-width: 0;
  min-height: 2.8em;
  padding: 8px 10px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  font-size: 14px;
  line-height: 1.4;
  resize: none;
  overflow-y: hidden;
  font-family: inherit;
  color: #412402;
  box-sizing: border-box;
}

.save-btn {
  flex-shrink: 0;
  padding: 6px 14px;
  border: 1px solid #52c41a;
  border-radius: 6px;
  background: #fff;
  color: #389e0d;
  cursor: pointer;
  font-size: 13px;
}

.save-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.save-btn.saved {
  background: #52c41a;
  color: #fff;
  border-color: #52c41a;
}

.saved-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #389e0d;
}

.footer-bar {
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 0 24px;
  font-size: 13px;
  color: #92400e;
  border-top: 1px solid #fac775;
}

.c-pool {
  color: #389e0d;
}

.c-retrieved {
  color: #0958d9;
}

.c-none {
  color: #595959;
}
</style>

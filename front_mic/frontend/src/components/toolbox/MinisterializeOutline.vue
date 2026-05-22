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
  manual: { color: "orange", label: "人工处理" },
};

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
      return {
        key: String(r.index),
        index: r.index,
        displaySeq: seq,
        original: r.original,
        status: r.status,
        result: r.result,
      };
    });
    toastSuccess(`职事化完成，共 ${results.length} 条`);
  } catch (err) {
    error.value = err.message || "网络错误，请稍后重试";
  } finally {
    loading.value = false;
  }
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
  console.log("[ministerialize download] tableData rows:", JSON.parse(JSON.stringify(tableData.value)));
  console.log("[ministerialize download] lines for docx:", lines);
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
          <span class="field-label">系列名</span>
          <a-input v-model:value="headerSeries" placeholder="系列名（可选）" :disabled="loading" />
        </div>
        <div class="header-row">
          <span class="field-label">总题</span>
          <a-input v-model:value="headerTopic" placeholder="总题（可选）" :disabled="loading" />
        </div>
        <div class="header-row">
          <span class="field-label">篇题</span>
          <a-input v-model:value="headerChapter" placeholder="篇题（可选）" :disabled="loading" />
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
            <a-tag :color="statusTag[row.status]?.color || 'default'" class="status-tag">
              {{ statusTag[row.status]?.label || row.status }}
            </a-tag>
            <a-input v-model:value="row.result" class="result-input" />
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
  color: #d46b08;
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
  align-items: center;
  gap: 10px;
  padding-left: 1.5em;
}
.status-tag {
  flex: 0 0 auto;
}
.result-input {
  flex: 1;
}
</style>

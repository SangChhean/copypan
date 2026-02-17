<script setup>
import ToolsHeader from "./ToolsHeader.vue";
import { ref } from "vue";
import { SearchOutlined, FilterOutlined, LoadingOutlined } from "@ant-design/icons-vue";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";
const keyword = ref("");
const excludeKeywords = ref("");
const loading = ref(false);
const error = ref(null);
const logMessage = ref("");

async function exportDocx() {
  const k = (keyword.value || "").trim();
  if (!k) {
    error.value = "请输入搜索关键词";
    logMessage.value = "请输入搜索关键词后再点击检索并下载。";
    return;
  }
  error.value = null;
  logMessage.value = "正在检索…";
  loading.value = true;
  const authToken = localStorage.getItem("token") || null;
  if (!authToken) {
    loading.value = false;
    logMessage.value = "";
    window.location.hash = "/login";
    return;
  }
  try {
    const res = await fetch(`${apiBase}/api/ai_search/info_retrieval`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${authToken}`,
      },
      body: JSON.stringify({
        keyword: k,
        exclude_keywords: (excludeKeywords.value || "").trim() || undefined,
      }),
    });
    const noResults = (res.headers.get("x-no-results") || res.headers.get("X-No-Results")) === "true";
    if (noResults) {
      const data = await res.json();
      logMessage.value = data.message || "未返回说明";
      return;
    }
    if (!res.ok) {
      const t = await res.text();
      let msg = "导出失败，请稍后重试";
      try {
        const j = JSON.parse(t);
        msg = j.detail || j.message || msg;
      } catch (_) {}
      error.value = msg;
      logMessage.value = "";
      return;
    }
    const multipleFiles = (res.headers.get("x-multiple-files") || res.headers.get("X-Multiple-Files")) === "true";
    if (multipleFiles) {
      const data = await res.json();
      logMessage.value = data.log_message || "";
      const files = data.files || [];
      for (let i = 0; i < files.length; i++) {
        const { filename, content } = files[i];
        const bin = Uint8Array.from(atob(content), (c) => c.charCodeAt(0));
        const blob = new Blob([bin], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
        if (i < files.length - 1) await new Promise((r) => setTimeout(r, 300));
      }
      return;
    }
    const logB64 = res.headers.get("x-retrieval-log") || res.headers.get("X-Retrieval-Log");
    if (logB64) {
      try {
        const bytes = new Uint8Array([...atob(logB64)].map((c) => c.charCodeAt(0)));
        logMessage.value = new TextDecoder().decode(bytes);
      } catch (_) {
        logMessage.value = logB64;
      }
    }
    const blob = await res.blob();
    const disposition = res.headers.get("content-disposition");
    const filename = (() => {
      if (!disposition) return `${k.split(/\s+/)[0] || "export"}.docx`;
      const m = disposition.match(/filename\*?=(?:UTF-8'')?([^;]+)/i);
      if (m) {
        try {
          return decodeURIComponent(m[1].trim().replace(/^["']|["']$/g, ""));
        } catch (_) {}
      }
      return `${k.split(/\s+/)[0] || "export"}.docx`;
    })();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    if (!logMessage.value) logMessage.value = `已下载 ${filename}`;
  } catch (err) {
    logMessage.value = "";
    error.value = err.message || "导出失败，请稍后重试";
  } finally {
    loading.value = false;
  }
}

</script>

<template>
  <ToolsHeader title="信息检索" />
  <div class="box">
    <a-card>
      <p class="hint">
        多搜索词以空格隔开，篇题包含所有搜索词则命中；<br />多过滤词以空格隔开，篇题包含一个过滤词则过滤。
      </p>
      <a-divider :style="{ margin: '12px 0' }" />
      <a-input
        v-model:value="keyword"
        placeholder="请输入搜索词, 多词以空格隔开"
        size="large"
        class="search-input"
        @keyup.enter="exportDocx"
      >
        <template #prefix>
          <SearchOutlined class="input-icon" />
        </template>
      </a-input>
      <a-divider :style="{ margin: '12px 0' }" />
      <a-input
        v-model:value="excludeKeywords"
        placeholder="请输入过滤词, 多词以空格隔开"
        size="large"
        class="search-input"
        allow-clear
      >
        <template #prefix>
          <FilterOutlined class="input-icon" />
        </template>
      </a-input>
      <a-divider :style="{ margin: '12px 0' }" />
      <div class="action-row">
        <button
          type="button"
          class="action-btn"
          :disabled="loading"
          @click="exportDocx"
        >
          <LoadingOutlined v-if="loading" class="btn-icon btn-spin" />
          <span v-if="loading">检索中…</span>
          <span v-else>检索并下载</span>
        </button>
      </div>
    </a-card>
    <div v-if="loading" class="log log-loading">正在检索… 首次可能需要 1～2 分钟，请勿关闭页面。</div>
    <div v-else-if="logMessage" class="log">{{ logMessage }}</div>
    <div v-if="error" class="error">{{ error }}</div>
  </div>
</template>

<style scoped>
.box {
  padding: 1em;
  max-width: 640px;
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

.search-input {
  border-radius: 8px;
  background: #fafafa;
}
.search-input :deep(.ant-input-affix-wrapper) {
  border-radius: 8px;
  border: 1px solid #d9d9d9;
  background: #fafafa;
}
.search-input :deep(.ant-input) {
  background: #fafafa;
}
.input-icon {
  color: rgba(0, 0, 0, 0.45);
  font-size: 16px;
}

.action-row {
  margin-top: 16px;
  padding: 12px 0;
  border-top: 1px solid #f0f0f0;
  display: flex;
  justify-content: center;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 20px;
  font-size: 16px;
  border-radius: 6px;
  border: none;
  background: #1890ff;
  color: #fff;
  cursor: pointer;
}

.action-btn .btn-icon {
  font-size: 18px;
}

.action-btn .btn-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.action-btn:hover:not(:disabled) {
  background: #40a9ff;
}

.action-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.log {
  margin-top: 8px;
  padding: 8px 12px;
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  border-radius: 4px;
  color: #389e0d;
  font-size: 0.9em;
  white-space: pre-line;
}

.log-loading {
  background: #e6f7ff;
  border-color: #91d5ff;
  color: #0050b3;
}

.error {
  margin-top: 12px;
  color: #cf1322;
  font-size: 0.9em;
}
</style>

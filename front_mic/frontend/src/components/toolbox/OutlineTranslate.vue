<script setup>
import ToolsHeader from "./ToolsHeader.vue";
import { ref, computed } from "vue";
import { LoadingOutlined, CopyOutlined, DownloadOutlined } from "@ant-design/icons-vue";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";
const direction = ref("zh2en"); // zh2en | en2zh
const content = ref("");
const loading = ref(false);
const error = ref(null);
const result = ref(null);

const isZh2En = computed(() => direction.value === "zh2en");
const inputPlaceholder = computed(() =>
  isZh2En.value ? "请粘贴中文纲目全文…" : "请粘贴英文纲目全文…"
);

function copyResult() {
  if (!result.value) return;
  navigator.clipboard.writeText(result.value).then(() => {
    try {
      if (window.$message) window.$message.success("已复制到剪贴板");
    } catch (_) {}
  });
}

async function downloadFormattedDocx() {
  const text = (content.value || "").trim();
  if (!text) {
    error.value = isZh2En.value ? "请先粘贴中文纲目" : "请先粘贴英文纲目";
    result.value = null;
    return;
  }
  loading.value = true;
  error.value = null;
  result.value = null;
  const authToken = localStorage.getItem("token") || null;
  if (!authToken) {
    loading.value = false;
    window.location.hash = "/login";
    return;
  }
  try {
    const res = await fetch(`${apiBase}/api/ai_search/outline_translate_and_format`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${authToken}`,
      },
      body: JSON.stringify({ direction: direction.value, content: text }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      error.value = data.detail || data.error || data.message || "翻译并格式化失败，请稍后重试";
      return;
    }
    // 如果翻译失败（有 error 但没有 result），显示错误
    if (data.error && !data.result) {
      error.value = data.error;
      return;
    }
    // 如果格式化失败但翻译成功（有 error 也有 result），只显示警告，不阻止显示结果
    if (data.error && data.result) {
      try {
        if (window.$message) window.$message.warning(`翻译成功，但格式化失败: ${data.error}`);
      } catch (_) {}
    }
    // 更新翻译结果（如果有）
    if (data.result) {
      result.value = data.result;
    }
    // 下载 DOCX（如果有）
    if (data.docx_base64) {
      const bin = Uint8Array.from(atob(data.docx_base64), (c) => c.charCodeAt(0));
      const blob = new Blob([bin], {
        type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = data.filename || (isZh2En.value ? "outline_en.docx" : "outline_zh.docx");
      a.click();
      URL.revokeObjectURL(url);
      try {
        if (window.$message) window.$message.success("已下载格式化 DOCX");
      } catch (_) {}
    } else if (data.error) {
      // 格式化失败但翻译成功
      try {
        if (window.$message) window.$message.warning(`翻译成功，但格式化失败: ${data.error}`);
      } catch (_) {}
    }
  } catch (err) {
    error.value = err.message || "网络错误，请稍后重试";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <ToolsHeader title="纲目翻译" />
  <div class="box">
    <a-card>
      <p class="hint">
        选择翻译方向后，粘贴纲目全文（含标题则一起粘贴），点击按钮后会自动翻译、格式化并下载 DOCX 文件。
      </p>
      <a-divider :style="{ margin: '12px 0' }" />
      <div class="direction-row">
        <span class="label">翻译方向：</span>
        <a-segmented
          v-model:value="direction"
          class="direction-segmented"
          :options="[
            { label: '中文 → 英文', value: 'zh2en' },
            { label: '英文 → 中文', value: 'en2zh' },
          ]"
        />
      </div>
      <a-divider :style="{ margin: '12px 0' }" />
      <a-textarea
        v-model:value="content"
        :placeholder="inputPlaceholder"
        :rows="12"
        class="content-area"
        allow-clear
      />
      <div class="action-row">
        <button
          type="button"
          class="action-btn"
          :disabled="loading"
          @click="downloadFormattedDocx"
        >
          <LoadingOutlined v-if="loading" class="btn-icon btn-spin" />
          <DownloadOutlined v-else class="btn-icon" />
          <span v-if="loading">翻译并格式化中…</span>
          <span v-else>翻译、刷格式并下载</span>
        </button>
      </div>
    </a-card>

    <div v-if="error" class="error">{{ error }}</div>

    <a-card v-if="result" class="result-card">
      <template #title>
        <span>{{ isZh2En ? "英文纲目" : "中文纲目" }}</span>
        <button type="button" class="copy-btn" @click="copyResult">
          <CopyOutlined /> 复制
        </button>
      </template>
      <pre class="result-body">{{ result }}</pre>
    </a-card>
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

.direction-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.direction-row .label {
  font-weight: 600;
  color: #333;
  font-size: 1em;
}

/* 翻译方向分段控件：更醒目，选中项绿色 */
.direction-segmented :deep(.ant-segmented-group) {
  gap: 4px;
}
.direction-segmented :deep(.ant-segmented-item) {
  padding: 8px 20px;
  font-weight: 500;
  font-size: 15px;
  border: 2px solid #d9d9d9;
  border-radius: 6px;
  background: #fafafa;
}
.direction-segmented :deep(.ant-segmented-item:hover) {
  border-color: #52c41a;
  color: #389e0d;
}
.direction-segmented :deep(.ant-segmented-item-selected) {
  background: #52c41a !important;
  border-color: #52c41a !important;
  color: #fff !important;
}
.direction-segmented :deep(.ant-segmented-thumb) {
  background: #52c41a !important;
  border-radius: 4px;
}

.content-area {
  margin-top: 8px;
}

.content-area :deep(.ant-input) {
  border-radius: 8px;
  font-family: inherit;
}

.action-row {
  margin-top: 16px;
  padding: 12px 0;
  border-top: 1px solid #f0f0f0;
  display: flex;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 24px;
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


.error {
  margin-top: 12px;
  color: #cf1322;
  font-size: 0.95em;
}

.result-card {
  margin-top: 20px;
}

.result-card :deep(.ant-card-head) {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}

.copy-btn {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: 13px;
  border-radius: 4px;
  border: 1px solid #d9d9d9;
  background: #fff;
  cursor: pointer;
  color: #555;
}

.copy-btn:hover {
  color: #1890ff;
  border-color: #1890ff;
}

.result-body {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-size: 0.95em;
  line-height: 1.6;
  max-height: 60vh;
  overflow-y: auto;
}
</style>

<script setup>
import ToolsHeader from "./ToolsHeader.vue";
import { ref, computed } from "vue";
import { LoadingOutlined, CopyOutlined, DownloadOutlined } from "@ant-design/icons-vue";
import axios from "axios";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";
const direction = ref("zh_cn2tw"); // zh_cn2tw | zh_tw2cn
const downloadFormats = ref([]); // ["docx", "pdf"] - 用户选择的下载格式
const content = ref("");
const loading = ref(false);
const downloading = ref(false); // 正在下载
const error = ref(null);
const result = ref(null);

const isCn2Tw = computed(() => direction.value === "zh_cn2tw");
const inputPlaceholder = computed(() =>
  isCn2Tw.value ? "请粘贴简体纲目全文…" : "请粘贴台湾繁体纲目全文…"
);

function copyResult() {
  if (!result.value) return;
  navigator.clipboard.writeText(result.value).then(() => {
    try {
      if (window.$message) window.$message.success("已复制到剪贴板");
    } catch (_) {}
  });
}

// 转换（不格式化）
async function convert() {
  const text = (content.value || "").trim();
  if (!text) {
    error.value = isCn2Tw.value ? "请先粘贴简体纲目" : "请先粘贴繁体纲目";
    result.value = null;
    return;
  }
  loading.value = true;
  error.value = null;
  result.value = null;
  downloadFormats.value = [];
  const authToken = localStorage.getItem("token") || null;
  if (!authToken) {
    loading.value = false;
    window.location.hash = "/login";
    return;
  }
  try {
    const endpoint = isCn2Tw.value
      ? "/api/ai_search/outline_to_traditional"
      : "/api/ai_search/traditional_to_simplified";
    const fieldName = isCn2Tw.value ? "answer_zh_tw" : "answer_zh_cn";
    const res = await axios.post(
      `${apiBase}${endpoint}`,
      { content: text },
      {
        headers: {
          Authorization: `Bearer ${authToken}`,
        },
        timeout: 60000,
      }
    );
    const data = res.data;
    if (data[fieldName]) {
      result.value = data[fieldName];
      try {
        if (window.$message) window.$message.success("转换完成！请选择下载格式并点击下载按钮。");
      } catch (_) {}
    } else {
      error.value = data.error || data.detail || "转换失败，请稍后重试";
    }
  } catch (err) {
    error.value = err.response?.data?.detail || err.response?.data?.error || err.message || "网络错误，请稍后重试";
  } finally {
    loading.value = false;
  }
}

// 下载格式化文件
async function downloadFormatted() {
  if (!result.value) {
    try {
      if (window.$message) window.$message.warning("请先完成转换");
    } catch (_) {}
    return;
  }
  if (downloadFormats.value.length === 0) {
    try {
      if (window.$message) window.$message.warning("请至少选择一个下载格式");
    } catch (_) {}
    return;
  }
  
  downloading.value = true;
  const authToken = localStorage.getItem("token") || null;
  if (!authToken) {
    downloading.value = false;
    window.location.hash = "/login";
    return;
  }
  
  try {
    // 依次下载每个选中的格式
    // 使用 format_outline_only 接口，传入已转换的文本，避免重复调用转换 API
    for (const format of downloadFormats.value) {
      const res = await fetch(`${apiBase}/api/ai_search/format_outline_only`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({ 
          direction: direction.value, 
          translated_text: result.value,
          output_format: format,
        }),
      });
      
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        try {
          if (window.$message) window.$message.error(`${format.toUpperCase()} 格式化失败: ${errorData.detail || errorData.error || "未知错误"}`);
        } catch (_) {}
        continue;
      }
      
      const data = await res.json();
      
      // 下载文件
      if (format === "docx" && data.docx_base64) {
        try {
          const bin = Uint8Array.from(atob(data.docx_base64), (c) => c.charCodeAt(0));
          const blob = new Blob([bin], {
            type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = data.filename || "outline.docx";
          a.click();
          URL.revokeObjectURL(url);
        } catch (downloadErr) {
          console.error(`下载${format.toUpperCase()}失败:`, downloadErr);
          try {
            if (window.$message) window.$message.error(`下载 ${format.toUpperCase()} 失败`);
          } catch (_) {}
        }
      } else if (format === "pdf") {
        if (data.pdf_base64) {
          // PDF 转换成功
          try {
            const bin = Uint8Array.from(atob(data.pdf_base64), (c) => c.charCodeAt(0));
            const blob = new Blob([bin], {
              type: "application/pdf",
            });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = data.filename || "outline.pdf";
            a.click();
            URL.revokeObjectURL(url);
          } catch (downloadErr) {
            console.error(`下载${format.toUpperCase()}失败:`, downloadErr);
            try {
              if (window.$message) window.$message.error(`下载 ${format.toUpperCase()} 失败`);
            } catch (_) {}
          }
        } else if (data.docx_base64) {
          // PDF 转换失败，回退到 DOCX
          try {
            const bin = Uint8Array.from(atob(data.docx_base64), (c) => c.charCodeAt(0));
            const blob = new Blob([bin], {
              type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = data.filename || "outline.docx";
            a.click();
            URL.revokeObjectURL(url);
            // 提示用户 PDF 转换失败
            try {
              if (window.$message) {
                window.$message.warning("PDF 转换失败（可能未安装 Microsoft Word 或 LibreOffice），已下载 DOCX 文件");
              }
            } catch (_) {}
          } catch (downloadErr) {
            console.error(`下载DOCX失败:`, downloadErr);
            try {
              if (window.$message) window.$message.error("下载文件失败");
            } catch (_) {}
          }
        } else if (data.error) {
          try {
            if (window.$message) window.$message.warning(`PDF 格式化失败: ${data.error}`);
          } catch (_) {}
        } else {
          try {
            if (window.$message) window.$message.warning("PDF 转换失败，请检查是否安装了 Microsoft Word 或 LibreOffice");
          } catch (_) {}
        }
      } else if (data.error) {
        try {
          if (window.$message) window.$message.warning(`${format.toUpperCase()} 格式化失败: ${data.error}`);
        } catch (_) {}
      }
    }
    
    try {
      if (window.$message) window.$message.success("下载完成！");
    } catch (_) {}
  } catch (err) {
    error.value = err.message || "下载失败，请稍后重试";
  } finally {
    downloading.value = false;
  }
}
</script>

<template>
  <ToolsHeader title="简繁互转" />
  <div class="box">
    <a-card>
      <p class="hint">
        选择转换方向后，粘贴纲目全文（含标题则一起粘贴），点击「转换」按钮完成转换，然后选择下载格式并点击「下载」按钮。
      </p>
      <a-divider :style="{ margin: '12px 0' }" />
      <div class="direction-row">
        <span class="label">转换方向：</span>
        <a-segmented
          v-model:value="direction"
          class="direction-segmented"
          :options="[
            { label: '简体 → 繁体', value: 'zh_cn2tw' },
            { label: '繁体 → 简体', value: 'zh_tw2cn' },
          ]"
        />
      </div>
      <a-divider :style="{ margin: '12px 0' }" />
      <div class="textarea-wrap">
        <a-textarea
          v-model:value="content"
          :placeholder="inputPlaceholder"
          :rows="12"
          class="content-area"
          :disabled="loading"
          allow-clear
        />
        <button
          type="button"
          class="clear-btn"
          :disabled="!content || loading"
          @click="content = ''"
        >
          清空
        </button>
      </div>
      <div class="action-row">
        <button
          type="button"
          class="action-btn"
          :disabled="loading || !content.trim()"
          @click="convert"
        >
          <LoadingOutlined v-if="loading" class="btn-icon btn-spin" />
          <span v-if="loading">转换中…</span>
          <span v-else>转换</span>
        </button>
      </div>
      <p v-if="loading" class="loading-hint">请耐心等待 1～2 分钟</p>
      
      <!-- 转换结果后的下载选项 -->
      <div v-if="result" class="download-section">
        <a-divider :style="{ margin: '16px 0' }" />
        <div class="direction-row">
          <span class="label">下载格式：</span>
          <a-checkbox-group v-model:value="downloadFormats">
            <a-checkbox value="docx">DOCX</a-checkbox>
            <a-checkbox value="pdf">PDF</a-checkbox>
          </a-checkbox-group>
        </div>
        <div class="action-row" style="margin-top: 12px;">
          <button
            type="button"
            class="action-btn"
            :disabled="downloading || downloadFormats.length === 0"
            @click="downloadFormatted"
          >
            <LoadingOutlined v-if="downloading" class="btn-icon btn-spin" />
            <DownloadOutlined v-else class="btn-icon" />
            <span v-if="downloading">格式化并下载中…</span>
            <span v-else>刷格式并下载</span>
          </button>
        </div>
        <p v-if="downloading" class="loading-hint">请耐心等待 1～2 分钟</p>
      </div>
    </a-card>

    <div v-if="error" class="error">{{ error }}</div>

    <a-card v-if="result" class="result-card">
      <template #title>
        <span>{{ isCn2Tw ? "繁体纲目" : "简体纲目" }}</span>
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

/* 转换方向分段控件：更醒目，选中项绿色 */
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

.textarea-wrap {
  margin-top: 8px;
  position: relative;
}

.content-area {
  display: block;
}

.content-area :deep(.ant-input) {
  border-radius: 8px;
  font-family: inherit;
}

/* 明显的清空按钮 */
.clear-btn {
  margin-top: 10px;
  padding: 6px 16px;
  font-size: 14px;
  font-weight: 500;
  color: #666;
  background: #fff;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  cursor: pointer;
}
.clear-btn:hover:not(:disabled) {
  color: #ff4d4f;
  border-color: #ff4d4f;
  background: #fff1f0;
}
.clear-btn:disabled {
  color: #bbb;
  cursor: not-allowed;
  background: #fafafa;
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

.loading-hint {
  margin: 8px 0 0;
  color: #8c8c8c;
  font-size: 0.9em;
  text-align: center;
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

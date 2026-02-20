<script setup>
import ToolsHeader from "./ToolsHeader.vue";
import { ref, computed } from "vue";
import { LoadingOutlined, CopyOutlined, DownloadOutlined } from "@ant-design/icons-vue";
import { toastSuccess, toastWarning, toastError } from "../utils/Dialog";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";
const direction = ref("zh2en"); // zh2en | en2zh
const downloadFormats = ref([]); // ["docx", "pdf"] - 用户选择的下载格式
const content = ref("");
const loading = ref(false);
const downloading = ref(false); // 正在下载
const error = ref(null);
const result = ref(null);
const titleEn = ref(null); // 英文标题（仅中翻英时）

const isZh2En = computed(() => direction.value === "zh2en");
const inputPlaceholder = computed(() =>
  isZh2En.value ? "请粘贴中文纲目全文…" : "请粘贴英文纲目全文…"
);

function copyResult() {
  if (!result.value) return;
  navigator.clipboard.writeText(result.value).then(() => {
    try {
      toastSuccess("已复制到剪贴板");
    } catch (_) {}
  });
}

// 翻译（不格式化）
async function translate() {
  const text = (content.value || "").trim();
  if (!text) {
    error.value = isZh2En.value ? "请先粘贴中文纲目" : "请先粘贴英文纲目";
    result.value = null;
    return;
  }
  loading.value = true;
  error.value = null;
  result.value = null;
  titleEn.value = null;
  downloadFormats.value = [];
  const authToken = localStorage.getItem("token") || null;
  if (!authToken) {
    loading.value = false;
    window.location.hash = "/login";
    return;
  }
  try {
    const res = await fetch(`${apiBase}/api/ai_search/outline_translate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${authToken}`,
      },
      body: JSON.stringify({ 
        direction: direction.value, 
        content: text,
        outline_topic: null, // 工具箱翻译不需要标题
      }),
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      error.value = errorData.detail || errorData.error || errorData.message || "翻译失败，请稍后重试";
      return;
    }
    
    const data = await res.json();
    if (data.error && !data.result) {
      error.value = data.error;
      return;
    }
    
    if (data.result) {
      result.value = data.result;
      if (data.title_en) {
        titleEn.value = data.title_en;
      }
      try {
        toastSuccess("翻译完成！请选择下载格式并点击下载按钮。");
      } catch (_) {}
    } else {
      error.value = "翻译失败，请稍后重试";
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
      toastWarning("请先完成翻译");
    } catch (_) {}
    return;
  }
  if (downloadFormats.value.length === 0) {
    try {
      toastWarning("请至少选择一个下载格式");
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
    // 依次下载每个选中的格式，固定顺序：先 DOCX 再 PDF，避免后端 PDF 转换线程 COM 初始化顺序问题
    const orderedFormats = ["docx", "pdf"].filter((f) => downloadFormats.value.includes(f));
    for (const format of orderedFormats) {
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
          toastError(`${format.toUpperCase()} 格式化失败: ${errorData.detail || errorData.error || "未知错误"}`);
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
          a.download = data.filename || (isZh2En.value ? "outline_en.docx" : "outline_zh.docx");
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (downloadErr) {
          console.error(`下载${format.toUpperCase()}失败:`, downloadErr);
          try {
            toastError(`下载 ${format.toUpperCase()} 失败`);
          } catch (_) {}
        }
      } else if (format === "pdf") {
        if (data.pdf_base64) {
          // PDF 转换成功（移动端与桌面端均使用下载）
          try {
            const bin = Uint8Array.from(atob(data.pdf_base64), (c) => c.charCodeAt(0));
            const blob = new Blob([bin], {
              type: "application/pdf",
            });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = data.filename || (isZh2En.value ? "outline_en.pdf" : "outline_zh.pdf");
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          } catch (downloadErr) {
            console.error(`下载${format.toUpperCase()}失败:`, downloadErr);
            try {
              toastError(`下载 ${format.toUpperCase()} 失败`);
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
            a.download = data.filename || (isZh2En.value ? "outline_en.docx" : "outline_zh.docx");
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            setTimeout(() => URL.revokeObjectURL(url), 1000);
            // 提示用户 PDF 转换失败
            try {
              toastWarning("PDF 转换失败（可能未安装 Microsoft Word 或 LibreOffice），已下载 DOCX 文件");
            } catch (_) {}
          } catch (downloadErr) {
            console.error(`下载DOCX失败:`, downloadErr);
            try {
              toastError("下载文件失败");
            } catch (_) {}
          }
        } else if (data.error) {
          try {
            toastWarning(`PDF 格式化失败: ${data.error}`);
          } catch (_) {}
        } else {
          try {
            toastWarning("PDF 转换失败，请检查是否安装了 Microsoft Word 或 LibreOffice");
          } catch (_) {}
        }
      } else if (data.error) {
        try {
          toastWarning(`${format.toUpperCase()} 格式化失败: ${data.error}`);
        } catch (_) {}
      }
    }
    
    try {
      toastSuccess("下载完成！");
    } catch (_) {}
  } catch (err) {
    error.value = err.message || "下载失败，请稍后重试";
  } finally {
    downloading.value = false;
  }
}
</script>

<template>
  <ToolsHeader title="纲目翻译" />
  <div class="box">
    <a-card>
      <p class="hint">
        选择翻译方向后，粘贴纲目全文（含标题则一起粘贴），点击「翻译」按钮完成翻译，然后选择下载格式并点击「下载」按钮。
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
          @click="translate"
        >
          <LoadingOutlined v-if="loading" class="btn-icon btn-spin" />
          <span v-if="loading">翻译中…</span>
          <span v-else>翻译</span>
        </button>
      </div>
      <p v-if="loading" class="loading-hint">请耐心等待 1～2 分钟</p>
      
      <!-- 翻译结果后的下载选项 -->
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

.loading-hint {
  margin: 8px 0 0;
  color: #8c8c8c;
  font-size: 0.9em;
  text-align: center;
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

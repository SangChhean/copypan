<script setup>
/**
 * 来源：front_mic/frontend/src/features/outline_translate/OutlineTranslate.vue
 * CN 改造：仅中↔英；鉴权走 cn_token/http；429 超限提示。
 */
import ToolsHeader from "@/components/ToolsHeader.vue";
import { ref, computed } from "vue";
import { LoadingOutlined, CopyOutlined, DownloadOutlined } from "@ant-design/icons-vue";
import http from "@/utils/http.js";
import { getToken } from "@/utils/auth.js";
import { toastSuccess, toastWarning, toastError } from "@/utils/Dialog.js";

const translateUsage = ref({ used: 0, limit: 3 });

const sourceLang = ref("zh");
const content = ref("");
const inputError = ref(null);
const loading = ref(false);
const downloading = ref(false);
const error = ref(null);
const result = ref(null);
const durationMs = ref(null);
const downloadFormats = ref(["docx"]);

const isSourceChinese = computed(() => sourceLang.value === "zh");
const apiDirection = computed(() => (isSourceChinese.value ? "zh2en" : "en2zh"));
const formatDirection = computed(() => (isSourceChinese.value ? "zh2en" : "en2zh"));

const inputPlaceholder = computed(() =>
  isSourceChinese.value ? "请粘贴简体中文纲目全文…" : "请粘贴英文纲目全文…"
);

function formatDuration(ms) {
  if (ms == null) return "";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

function parseApiError(err) {
  const data = err?.response?.data || {};
  let detail = data.detail;
  if (Array.isArray(detail)) {
    detail = detail.map((x) => x?.msg || JSON.stringify(x)).join("；");
  }
  return detail || data.error || data.message || err?.message || "请求失败";
}

async function refreshUsage() {
  try {
    const res = await http.get("/api/cn/auth/usage");
    translateUsage.value = res.data?.translate || { used: 0, limit: 3 };
  } catch {
    /* ignore */
  }
}

refreshUsage();

async function translate() {
  const text = (content.value || "").trim();
  inputError.value = null;
  error.value = null;
  result.value = null;

  if (!text) {
    inputError.value = isSourceChinese.value ? "请先粘贴简体中文纲目" : "请先粘贴英文纲目";
    return;
  }
  if (!getToken()) {
    window.location.hash = "/login";
    return;
  }

  loading.value = true;
  const start = Date.now();
  try {
    const res = await http.post("/api/ai_search/outline_translate", {
      direction: apiDirection.value,
      content: text,
      outline_topic: null,
    });
    const data = res.data || {};
    if (data.error && !data.result) {
      throw new Error(data.error);
    }
    if (!data.result) {
      throw new Error("翻译失败，请稍后重试");
    }
    result.value = data.result;
    durationMs.value = Date.now() - start;
    toastSuccess("翻译完成！");
    await refreshUsage();
  } catch (err) {
    const status = err?.response?.status;
    const msg = parseApiError(err);
    if (status === 429) {
      toastWarning(msg || "今日纲目翻译次数已达上限，请明天再来");
    } else {
      error.value = msg;
      toastError(msg);
    }
  } finally {
    loading.value = false;
  }
}

function copyText() {
  if (!result.value) return;
  navigator.clipboard.writeText(result.value).then(() => toastSuccess("已复制到剪贴板"));
}

async function downloadFormatted() {
  if (!result.value) {
    toastWarning("请先完成翻译");
    return;
  }
  if (!downloadFormats.value.length) {
    toastWarning("请至少选择一个下载格式");
    return;
  }
  if (!getToken()) {
    window.location.hash = "/login";
    return;
  }

  downloading.value = true;
  try {
    for (const format of ["docx", "pdf"].filter((f) => downloadFormats.value.includes(f))) {
      const res = await http.post("/api/ai_search/format_outline_only", {
        direction: formatDirection.value,
        translated_text: result.value,
        output_format: format,
        is_outline: true,
      });
      const data = res.data || {};
      const b64 = format === "pdf" ? data.pdf_base64 : data.docx_base64;
      if (!b64) {
        toastError(data.error || `${format.toUpperCase()} 下载失败`);
        continue;
      }
      const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
      const mime =
        format === "pdf"
          ? "application/pdf"
          : "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
      const blob = new Blob([bin], { type: mime });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = data.filename || `outline.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    }
  } catch (err) {
    toastError(parseApiError(err));
  } finally {
    downloading.value = false;
  }
}
</script>

<template>
  <ToolsHeader title="纲目翻译" />
  <div class="cn-page-body translate-body">
    <a-radio-group v-model:value="sourceLang" button-style="solid" class="dir-switch">
      <a-radio-button value="zh">中文 → 英文</a-radio-button>
      <a-radio-button value="en">英文 → 中文</a-radio-button>
    </a-radio-group>

    <a-divider :style="{ margin: '12px 0' }" />

    <div class="cn-result translate-pane">
      <div class="cn-label">输入</div>
      <a-textarea v-model:value="content" :placeholder="inputPlaceholder" :rows="14" :bordered="false" />
    </div>
    <div v-if="inputError" class="err">{{ inputError }}</div>

    <a-space :style="{ marginTop: '12px' }">
      <a-button type="primary" :loading="loading" @click="translate">
        <LoadingOutlined v-if="loading" />
        翻译
      </a-button>
      <a-button class="cn-btn-ghost" @click="content = ''">清空</a-button>
    </a-space>

    <div v-if="error" class="err">{{ error }}</div>

    <div v-if="result" class="cn-result translate-pane result-out">
      <div class="result-meta">
        <span v-if="durationMs != null">{{ formatDuration(durationMs) }}</span>
        <a-button type="link" size="small" @click="copyText"><CopyOutlined /> 复制</a-button>
      </div>
      <pre class="result-text">{{ result }}</pre>
      <a-checkbox-group v-model:value="downloadFormats" :options="['docx', 'pdf']" />
      <a-button
        type="primary"
        :loading="downloading"
        :style="{ marginTop: '8px' }"
        @click="downloadFormatted"
      >
        <DownloadOutlined /> 刷格式下载
      </a-button>
    </div>
  </div>
</template>

<style scoped>
.translate-body {
  padding-top: 20px;
}
.dir-switch :deep(.ant-radio-button-wrapper-checked) {
  background: var(--cn-charcoal) !important;
  border-color: var(--cn-charcoal) !important;
  color: var(--cn-gold) !important;
}
.dir-switch :deep(.ant-radio-button-wrapper) {
  border-color: var(--cn-gold) !important;
  color: var(--cn-gold) !important;
}
.translate-pane {
  margin-bottom: 12px;
}
.translate-pane :deep(.ant-input) {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
}
.err {
  color: var(--cn-danger);
  margin-top: 8px;
}
.result-out {
  margin-top: 20px;
}
.result-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  color: var(--cn-text-secondary);
  font-size: 13px;
}
.result-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  margin: 0 0 12px;
  line-height: 2;
}
</style>

<!-- 练习组件：连接 testA 独立后端 http://localhost:8001 -->
<script setup>
import { ref, computed, watch } from "vue";
import { DownloadOutlined } from "@ant-design/icons-vue";
import ToolsHeader from "./ToolsHeader.vue";

const apiBase = "";
const MAX_CONTENT_CHARS = 100_000;
const direction = ref("zh2en");
const content = ref("");
const loading = ref(false);
const error = ref(null);
const result = ref(null);
const toast = ref("");

const simplifiedChecked = ref(true);
const traditionalChecked = ref(false);

const resultTraditional = ref(null);
const errorsTraditional = ref([]);
const correctedWordsTraditional = ref({});

watch(traditionalChecked, (val) => {
  if (val) simplifiedChecked.value = true;
});

const isEn2Zh = computed(() => direction.value === "en2zh");
const isZh2En = computed(() => direction.value === "zh2en");

const inputPlaceholder = computed(() => {
  if (direction.value === "zh2en") return "请粘贴中文纲目全文…";
  return "请粘贴英文纲目全文…";
});
const charCount = computed(() => (content.value || "").length);

const translateEndpoint = computed(() => {
  if (direction.value === "zh2en") return `${apiBase}/api/testa/translate/zh2en`;
  if (direction.value === "en2es") return `${apiBase}/api/testa/translate/en2es`;
  return `${apiBase}/api/testa/translate/en2zh`;
});

const resultTitle = computed(() => {
  if (direction.value === "zh2en") return "英文纲目";
  if (direction.value === "en2es") return "西班牙文纲目";
  return "中文纲目";
});

watch(direction, () => {
  resultTraditional.value = null;
  errorsTraditional.value = [];
  correctedWordsTraditional.value = {};
});

function showToast(msg) {
  toast.value = msg;
  setTimeout(() => {
    if (toast.value === msg) toast.value = "";
  }, 2500);
}

function copyResult(text) {
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    showToast("已复制到剪贴板");
  });
}

const formatLoading = ref(false);

async function formatAndDownload(text, lang) {
  const content = text ?? result.value;
  if (!content) return;
  let dlLang = lang;
  if (!dlLang) {
    dlLang = "zh";
    if (direction.value === "zh2en") dlLang = "en";
    if (direction.value === "en2es") dlLang = "es";
  }

  formatLoading.value = true;
  try {
    const res = await fetch("/api/testa/translate/format_download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: content, lang: dlLang }),
    });
    if (!res.ok) {
      showToast("下载失败，请稍后重试");
      return;
    }
    let filename = `formatted_${dlLang}.docx`;
    const disposition = res.headers.get("Content-Disposition");
    if (disposition) {
      const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
      if (utf8Match) {
        filename = decodeURIComponent(utf8Match[1]);
      } else {
        const asciiMatch = disposition.match(/filename="([^"]+)"/i);
        if (asciiMatch) filename = asciiMatch[1];
      }
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    showToast("下载失败，请稍后重试");
  } finally {
    formatLoading.value = false;
  }
}

function highlightMarkers(sentence) {
  return sentence
    .replace(/【【/g, '<span class="error-highlight">')
    .replace(/】】/g, "</span>");
}

function applyCorrections() {
  let text = resultTraditional.value;
  errorsTraditional.value.forEach((item, idx) => {
    const original = item.word;
    const corrected = correctedWordsTraditional.value[idx];
    if (corrected && corrected !== original) {
      text = text.split(original).join(corrected);
      errorsTraditional.value[idx] = { ...item, word: corrected };
      correctedWordsTraditional.value[idx] = corrected;
    }
  });
  resultTraditional.value = text;
}

async function translate() {
  const text = (content.value || "").trim();
  if (!text) {
    error.value = isZh2En.value ? "请先粘贴中文纲目" : "请先粘贴英文纲目";
    result.value = null;
    return;
  }
  if (text.length > MAX_CONTENT_CHARS) {
    error.value = `正文过长：最多 ${MAX_CONTENT_CHARS.toLocaleString()} 字，请分段翻译`;
    result.value = null;
    return;
  }

  loading.value = true;
  error.value = null;
  result.value = null;
  resultTraditional.value = null;
  errorsTraditional.value = [];
  correctedWordsTraditional.value = {};

  try {
    const res = await fetch(translateEndpoint.value, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: text }),
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      let detail = errorData.detail;
      if (Array.isArray(detail)) {
        detail = detail.map((x) => x?.msg || x?.message || JSON.stringify(x)).join("；");
      }
      error.value = detail || errorData.error || errorData.message || "翻译失败，请稍后重试";
      return;
    }
    const data = await res.json();
    if (data.error && !data.result) {
      error.value = data.error;
      return;
    }
    if (!data.result) {
      error.value = "翻译失败，请稍后重试";
      return;
    }
    result.value = data.result;

    if (direction.value === "en2zh" && traditionalChecked.value) {
      const res2 = await fetch(`${apiBase}/api/testa/zh_convert`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: data.result }),
      });
      if (res2.ok) {
        const data2 = await res2.json();
        resultTraditional.value = data2.result || "";
        errorsTraditional.value = data2.errors || [];
        const init = {};
        (data2.errors || []).forEach((item, idx) => {
          init[idx] = item.word;
        });
        correctedWordsTraditional.value = init;
      }
    }

    showToast("翻译完成！");
  } catch (err) {
    error.value =
      (err && err.message) ||
      (typeof err === "string" ? err : "") ||
      "网络错误，请稍后重试";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <ToolsHeader title="翻译工具（testA）" />
  <div v-if="toast" class="toast">{{ toast }}</div>
  <div class="box">
    <section class="card">
      <p class="hint">
        独立练习后端：粘贴纲目后点「翻译」即可（无下载）。
        <strong>输入上限 {{ MAX_CONTENT_CHARS.toLocaleString() }} 字</strong>。
      </p>
      <hr class="divider" />
      <div class="direction-row">
        <span class="label">翻译方向：</span>
        <div class="segmented">
          <button
            type="button"
            class="seg-btn"
            :class="{ active: direction === 'zh2en' }"
            @click="direction = 'zh2en'"
          >
            中文 → 英文
          </button>
          <button
            type="button"
            class="seg-btn"
            :class="{ active: direction === 'en2zh' }"
            @click="direction = 'en2zh'"
          >
            英文 → 中文
          </button>
          <button
            type="button"
            class="seg-btn"
            :class="{ active: direction === 'en2es' }"
            @click="direction = 'en2es'"
          >
            英文 → 西班牙文
          </button>
        </div>
      </div>

      <div v-if="isEn2Zh" class="output-options">
        <label class="option-label" :class="{ locked: traditionalChecked }">
          <input
            type="checkbox"
            v-model="simplifiedChecked"
            :disabled="traditionalChecked"
          />
          中文简体
        </label>
        <label class="option-label">
          <input v-model="traditionalChecked" type="checkbox" />
          中文繁体
        </label>
      </div>

      <hr class="divider" />
      <div class="textarea-wrap">
        <textarea
          v-model="content"
          :placeholder="inputPlaceholder"
          rows="12"
          class="content-area"
          :disabled="loading"
          :maxlength="MAX_CONTENT_CHARS"
        />
        <div class="count-row">
          <span class="char-count">{{ charCount.toLocaleString() }} / {{ MAX_CONTENT_CHARS.toLocaleString() }}</span>
          <button type="button" class="clear-btn" :disabled="!content || loading" @click="content = ''">
            清空
          </button>
        </div>
      </div>
      <div class="action-row">
        <button type="button" class="action-btn" :disabled="loading || !content.trim()" @click="translate">
          <span v-if="loading" class="spin">⟳</span>
          <span>{{ loading ? "翻译中…" : "翻译" }}</span>
        </button>
      </div>
      <p v-if="loading" class="loading-hint">请耐心等待 1～2 分钟</p>
    </section>

    <div v-if="error" class="error">{{ error }}</div>

    <div v-if="result && !isEn2Zh" class="card result-wrap">
      <div class="result-head">
        <span class="result-title">{{ resultTitle }}</span>
        <div class="result-actions">
          <button type="button" class="copy-btn" @click="copyResult(result)">复制</button>
        </div>
      </div>
      <pre class="result-body">{{ result }}</pre>
    </div>
    <div v-if="result && !isEn2Zh" class="format-bar">
      <a-button class="format-download-btn" :loading="formatLoading" @click="formatAndDownload()">
        <template #icon><DownloadOutlined /></template>
        刷格式并下载
      </a-button>
    </div>

    <div v-if="result && isEn2Zh && simplifiedChecked" class="card result-wrap">
      <div class="result-head">
        <span class="result-title">中文简体</span>
        <div class="result-actions">
          <button type="button" class="copy-btn" @click="copyResult(result)">复制</button>
        </div>
      </div>
      <pre class="result-body">{{ result }}</pre>
    </div>
    <div v-if="result && isEn2Zh && simplifiedChecked" class="format-bar">
      <a-button class="format-download-btn" :loading="formatLoading" @click="formatAndDownload(result, 'zh')">
        <template #icon><DownloadOutlined /></template>
        刷格式并下载
      </a-button>
    </div>

    <div v-if="resultTraditional && isEn2Zh && traditionalChecked" class="card result-wrap">
      <div class="result-head">
        <span class="result-title">中文繁体</span>
        <div class="result-actions">
          <button type="button" class="copy-btn" @click="copyResult(resultTraditional)">复制</button>
        </div>
      </div>
      <pre class="result-body">{{ resultTraditional }}</pre>

      <div v-if="errorsTraditional.length > 0" class="error-report">
        <div class="error-report-title">
          <span>易错字报告</span>
          <span class="error-count">{{ errorsTraditional.length }} 处</span>
        </div>
        <div
          v-for="(item, idx) in errorsTraditional"
          :key="idx"
          class="error-item"
        >
          <div class="error-sentence" v-html="highlightMarkers(item.sentence)"></div>
          <div class="error-fix-row">
            <span class="error-label">修正为：</span>
            <a-input
              v-model:value="correctedWordsTraditional[idx]"
              size="small"
              class="error-input"
            />
          </div>
        </div>
        <a-button type="primary" class="apply-btn" @click="applyCorrections">
          应用全部修正
        </a-button>
      </div>
    </div>
    <div v-if="resultTraditional && isEn2Zh && traditionalChecked" class="format-bar">
      <a-button class="format-download-btn" :loading="formatLoading" @click="formatAndDownload(resultTraditional, 'zh')">
        <template #icon><DownloadOutlined /></template>
        刷格式并下载
      </a-button>
    </div>
  </div>
</template>

<style scoped>
.toast {
  position: fixed;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.75);
  color: #fff;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  z-index: 1000;
}
.box {
  padding: 1em;
  max-width: 720px;
  margin: 0 auto;
}
.card {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
.hint {
  color: #555;
  margin: 0;
  font-size: 0.95em;
  line-height: 1.5;
}
.divider {
  border: none;
  border-top: 1px solid #f0f0f0;
  margin: 12px 0;
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
}
.segmented {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.seg-btn {
  padding: 8px 20px;
  font-weight: 500;
  font-size: 15px;
  border: 2px solid #d9d9d9;
  border-radius: 6px;
  background: #fafafa;
  cursor: pointer;
}
.seg-btn:hover {
  border-color: #52c41a;
  color: #389e0d;
}
.seg-btn.active {
  background: #52c41a;
  border-color: #52c41a;
  color: #fff;
}
.output-options {
  display: flex;
  gap: 20px;
  padding: 10px 0 4px;
}
.option-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: #333;
  cursor: pointer;
  user-select: none;
}
.option-label.locked {
  color: #bbb;
  cursor: not-allowed;
}
.option-label input[type="checkbox"] {
  width: 15px;
  height: 15px;
  cursor: pointer;
  accent-color: #52c41a;
}
.option-label.locked input[type="checkbox"] {
  cursor: not-allowed;
}
.textarea-wrap {
  margin-top: 8px;
}
.content-area {
  width: 100%;
  box-sizing: border-box;
  border-radius: 8px;
  border: 1px solid #d9d9d9;
  padding: 10px;
  font-family: inherit;
  font-size: 14px;
  resize: vertical;
}
.count-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
}
.char-count {
  font-size: 13px;
  color: #888;
}
.clear-btn {
  padding: 6px 16px;
  font-size: 14px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
}
.clear-btn:hover:not(:disabled) {
  color: #ff4d4f;
  border-color: #ff4d4f;
}
.action-row {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
  display: flex;
  justify-content: center;
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
.action-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}
.spin {
  display: inline-block;
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
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
}
.result-wrap {
  margin-top: 20px;
}
.result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-weight: 600;
}
.result-title {
  color: #333;
}
.result-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.format-bar {
  margin: 0 16px 12px;
}
.format-download-btn {
  width: 100%;
  height: 38px;
  background: #55bbff;
  border-color: #55bbff;
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  border-radius: 6px;
}
.format-download-btn:hover {
  background: #7cccff;
  border-color: #7cccff;
  color: #fff;
}
.copy-btn {
  padding: 4px 10px;
  font-size: 13px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
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
.error-report {
  margin-top: 16px;
  border: 1px solid #faad14;
  border-radius: 8px;
  padding: 16px;
  background: #fffbe6;
}
.error-report-title {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #d48806;
}
.error-count {
  background: #faad14;
  color: #fff;
  border-radius: 10px;
  padding: 0 8px;
  font-size: 12px;
}
.error-item {
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #ffe58f;
}
.error-item:last-of-type {
  border-bottom: none;
}
.error-sentence {
  font-size: 13px;
  color: #595959;
  margin-bottom: 6px;
  line-height: 1.6;
}
:deep(.error-highlight) {
  background: #fff1b8;
  color: #d4380d;
  font-weight: 600;
  padding: 0 2px;
  border-radius: 2px;
}
.error-fix-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.error-label {
  font-size: 13px;
  color: #8c8c8c;
  white-space: nowrap;
}
.error-input {
  width: 160px;
}
.apply-btn {
  margin-top: 12px;
  width: 100%;
  background: #faad14;
  border-color: #faad14;
}
.apply-btn:hover {
  background: #ffc53d !important;
  border-color: #ffc53d !important;
}
</style>

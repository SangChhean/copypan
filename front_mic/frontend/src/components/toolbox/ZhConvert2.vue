<script setup>
import { ref, computed } from "vue";
import { ArrowLeftOutlined } from "@ant-design/icons-vue";

const apiBase = "";
const MAX_CONTENT_CHARS = 100_000;
const direction = ref("zh_cn2tw"); // zh_cn2tw | zh_tw2cn
const content = ref("");
const loading = ref(false);
const error = ref(null);
const result = ref(null);
const copyHint = ref("");

const isCn2Tw = computed(() => direction.value === "zh_cn2tw");
const charCount = computed(() => (content.value || "").length);
const inputPlaceholder = computed(() =>
  isCn2Tw.value ? "请粘贴简体内容…" : "请粘贴繁体内容…"
);
const resultTitle = computed(() => (isCn2Tw.value ? "繁体结果" : "简体结果"));
const apiUrl = computed(() =>
  isCn2Tw.value
    ? `${apiBase}/api/testa/zh_convert`
    : `${apiBase}/api/testa/tw_convert`
);

function clearInput() {
  content.value = "";
  error.value = null;
}

function goBack() {
  window.history.back();
}

function copyResult() {
  if (!result.value) return;
  navigator.clipboard.writeText(result.value).then(() => {
    copyHint.value = "已复制";
    setTimeout(() => {
      copyHint.value = "";
    }, 2000);
  });
}

async function convert() {
  const text = (content.value || "").trim();
  if (!text) {
    error.value = isCn2Tw.value ? "请先粘贴简体内容" : "请先粘贴繁体内容";
    result.value = null;
    return;
  }
  if (text.length > MAX_CONTENT_CHARS) {
    error.value = `正文过长：最多 ${MAX_CONTENT_CHARS.toLocaleString()} 字`;
    result.value = null;
    return;
  }

  loading.value = true;
  error.value = null;
  result.value = null;

  try {
    const res = await fetch(apiUrl.value, {
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
      error.value = detail || errorData.error || errorData.message || "转换失败，请稍后重试";
      return;
    }

    const data = await res.json();
    if (data.error && !data.result) {
      error.value = data.error;
      return;
    }
    if (data.result) {
      result.value = data.result;
    } else {
      error.value = "转换失败，请稍后重试";
    }
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
  <div class="page">
    <div class="header">
      <div @click="goBack()" class="back"><ArrowLeftOutlined /></div>
      <div class="header-title">简繁互转（testA）</div>
    </div>

    <div class="box">
      <div class="card">
        <p class="hint">
          选择转换方向后，粘贴全文，点击「转换」按钮完成转换。
        </p>
        <hr class="divider" />

        <div class="direction-row">
          <span class="label">转换方向：</span>
          <div class="direction-segmented">
            <button
              type="button"
              class="seg-btn"
              :class="{ selected: direction === 'zh_cn2tw' }"
              :disabled="loading"
              @click="direction = 'zh_cn2tw'"
            >
              简体 → 繁体
            </button>
            <button
              type="button"
              class="seg-btn"
              :class="{ selected: direction === 'zh_tw2cn' }"
              :disabled="loading"
              @click="direction = 'zh_tw2cn'"
            >
              繁体 → 简体
            </button>
          </div>
        </div>

        <hr class="divider" />

        <div class="textarea-wrap">
          <textarea
            v-model="content"
            class="content-area"
            :placeholder="inputPlaceholder"
            rows="12"
            :disabled="loading"
            :maxlength="MAX_CONTENT_CHARS"
          />
          <div class="input-footer">
            <span class="char-count">
              {{ charCount.toLocaleString() }} / {{ MAX_CONTENT_CHARS.toLocaleString() }} 字
            </span>
            <button
              type="button"
              class="clear-btn"
              :disabled="!content || loading"
              @click="clearInput"
            >
              清空
            </button>
          </div>
        </div>

        <div class="action-row">
          <button
            type="button"
            class="action-btn"
            :disabled="loading || !content.trim()"
            @click="convert"
          >
            <span v-if="loading" class="btn-icon btn-spin">⟳</span>
            <span v-if="loading">转换中…</span>
            <span v-else>转换</span>
          </button>
        </div>
      </div>

      <div v-if="error" class="error">{{ error }}</div>

      <div v-if="result" class="card result-card">
        <div class="result-head">
          <span class="result-title">{{ resultTitle }}</span>
          <span v-if="copyHint" class="copy-hint">{{ copyHint }}</span>
          <button type="button" class="copy-btn" @click="copyResult">复制</button>
        </div>
        <pre class="result-body">{{ result }}</pre>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  background: #f5f5f5;
  padding: 0 0 2em;
  box-sizing: border-box;
}

.header {
  padding: 10px 20px;
  display: flex;
  flex-direction: row;
  align-items: center;
  font-size: large;
  font-weight: bold;
  color: #55bbff;
  background-color: #001529;
  margin-bottom: 30px;
}

.header-title {
  text-align: center;
  width: 100%;
}

.back {
  cursor: pointer;
}

.back:hover {
  color: #1677ff;
  transform: scale(1.8);
  transition: 0.2s;
}

.box {
  max-width: 720px;
  margin: 0 auto;
  padding: 0 1em;
}

.card {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.06);
}

.hint {
  color: #555;
  margin: 0;
  font-size: 0.95em;
  line-height: 1.5;
}

.divider {
  margin: 12px 0;
  border: none;
  border-top: 1px solid #f0f0f0;
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

.direction-segmented {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.seg-btn {
  padding: 8px 20px;
  font-weight: 500;
  font-size: 15px;
  border: 2px solid #d9d9d9;
  border-radius: 6px;
  background: #fafafa;
  color: #333;
  cursor: pointer;
}

.seg-btn:hover:not(:disabled):not(.selected) {
  border-color: #52c41a;
  color: #389e0d;
}

.seg-btn.selected {
  background: #52c41a;
  border-color: #52c41a;
  color: #fff;
}

.seg-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.textarea-wrap {
  margin-top: 8px;
}

.content-area {
  display: block;
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  padding: 10px;
  font-size: 14px;
  line-height: 1.6;
  font-family: inherit;
  resize: vertical;
}

.content-area:focus {
  outline: none;
  border-color: #1890ff;
  box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.15);
}

.content-area:disabled {
  background: #fafafa;
  cursor: not-allowed;
}

.input-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 10px;
  gap: 8px;
}

.char-count {
  font-size: 13px;
  color: #8c8c8c;
}

.clear-btn {
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
  padding: 12px 0 0;
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

.action-btn .btn-icon {
  font-size: 18px;
}

.action-btn .btn-spin {
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

.result-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
}

.result-title {
  font-weight: 600;
  color: #333;
}

.copy-hint {
  font-size: 13px;
  color: #52c41a;
}

.copy-btn {
  margin-left: auto;
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

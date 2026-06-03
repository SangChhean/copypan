<!-- 练习文件：testA/translate/frontend/src/components/TranslateTest.vue，不用于生产 -->
<script setup>
import { ref, computed } from "vue";
import PageHeader from "./PageHeader.vue";

const apiBase = "http://localhost:8002";
const MAX_CONTENT_CHARS = 100_000;
const direction = ref("zh2en");
const content = ref("");
const loading = ref(false);
const error = ref(null);
const result = ref(null);
const toast = ref("");

const isZh2En = computed(() => direction.value === "zh2en");
const inputPlaceholder = computed(() =>
  isZh2En.value ? "请粘贴中文纲目全文…" : "请粘贴英文纲目全文…"
);
const charCount = computed(() => (content.value || "").length);

const translateEndpoint = computed(() =>
  isZh2En.value
    ? `${apiBase}/api/test/translate/zh2en`
    : `${apiBase}/api/test/translate/en2zh`
);

function showToast(msg) {
  toast.value = msg;
  setTimeout(() => {
    if (toast.value === msg) toast.value = "";
  }, 2500);
}

function copyResult() {
  if (!result.value) return;
  navigator.clipboard.writeText(result.value).then(() => {
    showToast("已复制到剪贴板");
  });
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
    if (data.result) {
      result.value = data.result;
      showToast("翻译完成！");
    } else {
      error.value = "翻译失败，请稍后重试";
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
  <PageHeader title="纲目翻译（testA 练习）" />
  <div v-if="toast" class="toast">{{ toast }}</div>
  <div class="box">
    <section class="card">
      <p class="hint">
        独立练习环境：粘贴纲目后点「翻译」即可（无下载、无登录）。
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
        </div>
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

    <p v-if="error" class="error">{{ error }}</p>

    <section v-if="result" class="card result-card">
      <div class="result-head">
        <span>{{ isZh2En ? "英文纲目" : "中文纲目" }}</span>
        <button type="button" class="copy-btn" @click="copyResult">复制</button>
      </div>
      <pre class="result-body">{{ result }}</pre>
    </section>
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
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
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
.result-card {
  margin-top: 20px;
}
.result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-weight: 600;
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
</style>

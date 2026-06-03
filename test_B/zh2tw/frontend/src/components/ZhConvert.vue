<script setup>
import { ref, computed } from "vue";

// 暴露给模板，使内联的 window.location.href 在 Vue 模板作用域内可用
const window = globalThis;

const apiBase = "http://localhost:8005";
const direction = ref("s2t");
const content = ref("");
const loading = ref(false);
const error = ref(null);
const result = ref(null);
const toast = ref("");

const isS2t = computed(() => direction.value === "s2t");
const inputPlaceholder = computed(() =>
  isS2t.value ? "请粘贴简体中文…" : "请粘贴繁体中文…"
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
    showToast("已复制");
  });
}

async function convert() {
  const text = (content.value || "").trim();
  if (!text) {
    error.value = "请先粘贴要转换的内容";
    result.value = null;
    return;
  }
  loading.value = true;
  error.value = null;
  result.value = null;
  const endpoint = isS2t.value
    ? `${apiBase}/api/testb/zh_convert`
    : `${apiBase}/api/testb/zh_to_simplified`;
  const resultField = isS2t.value ? "answer_zh_tw" : "answer_zh_cn";
  try {
    const res = await fetch(endpoint, {
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
    const answer = data[resultField];
    if (data.error && !answer) {
      error.value = data.error;
      return;
    }
    if (answer) {
      result.value = answer;
      showToast("转换完成！");
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
  <div v-if="toast" class="toast">{{ toast }}</div>
  <div class="box">
    <header class="page-header">
      <button type="button" class="back-btn" aria-label="返回" @click="window.location.href = 'http://localhost/#/tools'">←</button>
      <h1 class="page-title">简繁互转测试</h1>
    </header>

    <section class="card">
      <p class="hint">独立练习环境：粘贴内容后选择方向，点「转换」即可（无下载、无登录）。</p>
      <hr class="divider" />
      <div class="direction-row">
        <span class="label">转换方向：</span>
        <div class="segmented">
          <button
            type="button"
            class="seg-btn"
            :class="{ active: direction === 's2t' }"
            @click="direction = 's2t'"
          >
            简体 → 繁体
          </button>
          <button
            type="button"
            class="seg-btn"
            :class="{ active: direction === 't2s' }"
            @click="direction = 't2s'"
          >
            繁体 → 简体
          </button>
        </div>
      </div>
      <hr class="divider" />
      <div class="textarea-wrap">
        <textarea
          v-model="content"
          :placeholder="inputPlaceholder"
          class="content-area"
          :disabled="loading"
        />
      </div>
      <div class="action-row">
        <button type="button" class="clear-btn" :disabled="!content || loading" @click="content = ''">
          清空
        </button>
        <button type="button" class="convert-btn" :disabled="loading || !content.trim()" @click="convert">
          <span v-if="loading" class="spin">⟳</span>
          <span>{{ loading ? "转换中…" : "转换" }}</span>
        </button>
      </div>
    </section>

    <p v-if="error" class="error">{{ error }}</p>

    <section v-if="result" class="card result-card">
      <div class="result-head">
        <span>转换结果</span>
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
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.back-btn {
  width: 36px;
  height: 36px;
  font-size: 20px;
  line-height: 1;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  background: #fff;
  color: #333;
  cursor: pointer;
}
.back-btn:hover {
  border-color: #1890ff;
  color: #1890ff;
}
.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #222;
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
  height: calc(100vh - 420px);
  min-height: 400px;
  border-radius: 8px;
  border: 1px solid #d9d9d9;
  padding: 10px;
  font-family: inherit;
  font-size: 14px;
  resize: none;
  overflow-y: auto;
}
.action-row {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
  display: flex;
  justify-content: center;
  gap: 16px;
}
.clear-btn {
  padding: 8px 24px;
  font-size: 16px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  background: #fff;
  color: #333;
  cursor: pointer;
}
.clear-btn:hover:not(:disabled) {
  color: #ff4d4f;
  border-color: #ff4d4f;
}
.clear-btn:disabled {
  opacity: 0.5;
  color: #bbb;
  cursor: not-allowed;
}
.convert-btn {
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
.convert-btn:hover:not(:disabled) {
  background: #40a9ff;
}
.convert-btn:disabled {
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
.copy-btn:hover {
  border-color: #1890ff;
  color: #1890ff;
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

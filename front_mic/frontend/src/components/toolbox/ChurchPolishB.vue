<script setup>
import ToolsHeader from "./ToolsHeader.vue";
import { ref, computed } from "vue";
import { LoadingOutlined, CopyOutlined } from "@ant-design/icons-vue";

const article = ref("");
const lang = ref("");
const articleType = ref("");
const loading = ref(false);
const error = ref(null);
const result = ref(null);
const copied = ref(false);

const canSubmit = computed(
  () =>
    article.value.trim().length > 0 &&
    lang.value !== "" &&
    articleType.value !== ""
);

const typeLabels = computed(() => {
  if (lang.value === "en") {
    return { report: "Church Report", testimony: "Testimony" };
  }
  return { report: "召会通讯类", testimony: "见证类" };
});

function selectLang(value) {
  if (lang.value === value) return;
  lang.value = value;
  articleType.value = "";
}

async function generate() {
  if (!canSubmit.value || loading.value) return;
  loading.value = true;
  error.value = null;
  result.value = null;
  copied.value = false;
  try {
    const res = await fetch("/api/testb/church-polish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        article: article.value,
        lang: lang.value,
        article_type: articleType.value,
      }),
    });
    if (!res.ok) {
      let detail = `请求失败（${res.status}）`;
      try {
        const data = await res.json();
        detail = data.detail || detail;
      } catch (_) {}
      throw new Error(detail);
    }
    const data = await res.json();
    result.value = data.result;
  } catch (err) {
    error.value = err.message || "网络错误，请稍后重试";
  } finally {
    loading.value = false;
  }
}

function copyResult() {
  if (!result.value) return;
  navigator.clipboard.writeText(result.value).then(() => {
    copied.value = true;
    setTimeout(() => {
      copied.value = false;
    }, 2000);
  });
}
</script>

<template>
  <ToolsHeader title="召会通讯及见证类润色" />
  <div class="box">
    <a-card>
      <p class="hint">
        先选择语言和文章类型，再输入文章内容，点击「开始润色」即可获得润色结果。
      </p>
      <a-divider :style="{ margin: '12px 0' }" />

      <div class="style-section">
        <span class="label">选择语言：</span>
        <div class="style-grid">
          <button
            type="button"
            class="style-btn"
            :class="{ active: lang === 'zh' }"
            :disabled="loading"
            @click="selectLang('zh')"
          >
            中文
          </button>
          <button
            type="button"
            class="style-btn"
            :class="{ active: lang === 'en' }"
            :disabled="loading"
            @click="selectLang('en')"
          >
            English
          </button>
        </div>
      </div>

      <a-divider :style="{ margin: '16px 0' }" />
      <div class="style-section">
        <span class="label">选择文章类型：</span>
        <div class="style-grid">
          <button
            type="button"
            class="style-btn"
            :class="{ active: articleType === 'report' }"
            :disabled="loading"
            @click="articleType = 'report'"
          >
            {{ typeLabels.report }}
          </button>
          <button
            type="button"
            class="style-btn"
            :class="{ active: articleType === 'testimony' }"
            :disabled="loading"
            @click="articleType = 'testimony'"
          >
            {{ typeLabels.testimony }}
          </button>
        </div>
      </div>

      <a-divider :style="{ margin: '16px 0' }" />
      <div class="textarea-wrap">
        <a-textarea
          v-model:value="article"
          placeholder="请输入需要润色的文章"
          :rows="10"
          class="content-area"
          :disabled="loading"
          allow-clear
        />
      </div>

      <div class="action-row">
        <button
          type="button"
          class="action-btn"
          :disabled="loading || !canSubmit"
          @click="generate"
        >
          <LoadingOutlined v-if="loading" class="btn-icon btn-spin" />
          <span v-if="loading">润色中…</span>
          <span v-else>开始润色</span>
        </button>
      </div>
      <p v-if="loading" class="loading-hint">请耐心等待</p>
    </a-card>

    <div v-if="error" class="error">{{ error }}</div>

    <a-card v-if="result" class="result-card">
      <template #title>
        <span>润色结果</span>
        <button type="button" class="copy-btn" @click="copyResult">
          <CopyOutlined />
          {{ copied ? "已复制" : "复制" }}
        </button>
      </template>
      <pre class="result-body">{{ result }}</pre>
    </a-card>
  </div>
</template>

<style scoped>
.box {
  padding: 1em;
  max-width: 900px;
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

.textarea-wrap {
  margin-top: 8px;
}

.content-area {
  display: block;
}

.content-area :deep(.ant-input) {
  border-radius: 8px;
  font-family: inherit;
}

.style-section .label {
  display: block;
  font-weight: 600;
  color: #333;
  font-size: 1em;
  margin-bottom: 12px;
}

.style-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.style-btn {
  padding: 8px 16px;
  font-size: 14px;
  font-weight: 500;
  color: #555;
  background: #fafafa;
  border: 2px solid #d9d9d9;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.style-btn:hover:not(:disabled) {
  border-color: #52c41a;
  color: #389e0d;
}

.style-btn.active {
  background: #52c41a;
  border-color: #52c41a;
  color: #fff;
}

.style-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
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
  background: #bfbfbf;
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

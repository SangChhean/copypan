<script setup>
import ToolsHeader from "./ToolsHeader.vue";
import { ref, computed, onMounted } from "vue";
import { LoadingOutlined, CopyOutlined } from "@ant-design/icons-vue";

const article = ref("");
const styles = ref({}); // { key: label }
const selectedStyles = ref([]); // [key, ...]
const recoveryStyle = ref(true);
const loading = ref(false);
const error = ref(null);
const results = ref([]); // [{ key, label, text }]
const copiedKey = ref(null);

const canSubmit = computed(
  () => article.value.trim().length > 0 && selectedStyles.value.length > 0
);

function toggleStyle(key) {
  const idx = selectedStyles.value.indexOf(key);
  if (idx === -1) {
    selectedStyles.value.push(key);
  } else {
    selectedStyles.value.splice(idx, 1);
  }
}

function isSelected(key) {
  return selectedStyles.value.includes(key);
}

function splitLabel(label) {
  const idx = label.indexOf("（");
  if (idx === -1) return { main: label, sub: "" };
  return { main: label.slice(0, idx), sub: label.slice(idx) };
}

async function loadStyles() {
  try {
    const res = await fetch("/api/testb/styles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    if (!res.ok) throw new Error(`获取风格列表失败（${res.status}）`);
    styles.value = await res.json();
  } catch (err) {
    error.value = err.message || "获取风格列表失败";
  }
}

async function generate() {
  if (!canSubmit.value || loading.value) return;
  loading.value = true;
  error.value = null;
  results.value = [];
  try {
    const res = await fetch("/api/testb/polish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        article: article.value,
        styles: selectedStyles.value,
        recovery_style: recoveryStyle.value,
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
    const resultMap = data.results || {};
    results.value = selectedStyles.value
      .filter((key) => key in resultMap)
      .map((key) => ({
        key,
        label: styles.value[key] || key,
        text: resultMap[key],
      }));
  } catch (err) {
    error.value = err.message || "网络错误，请稍后重试";
  } finally {
    loading.value = false;
  }
}

function copyResult(item) {
  if (!item.text) return;
  navigator.clipboard.writeText(item.text).then(() => {
    copiedKey.value = item.key;
    setTimeout(() => {
      if (copiedKey.value === item.key) copiedKey.value = null;
    }, 2000);
  });
}

onMounted(loadStyles);
</script>

<template>
  <ToolsHeader title="文字润色" />
  <div class="box">
    <a-card>
      <p class="hint">
        输入文章内容，选择一种或多种润色风格，点击「开始润色」，每种风格的润色结果会单独展示。
      </p>
      <a-divider :style="{ margin: '12px 0' }" />

      <div class="style-section">
        <span class="label">选择润色风格（可多选）：</span>
        <div class="style-grid">
          <button
            v-for="(label, key) in styles"
            :key="key"
            type="button"
            class="style-btn"
            :class="{ active: isSelected(key) }"
            :disabled="loading"
            @click="toggleStyle(key)"
          >
            <span class="style-main">{{ splitLabel(label).main }}</span>
            <span class="style-sub">{{ splitLabel(label).sub }}</span>
          </button>
        </div>
      </div>

      <a-divider :style="{ margin: '16px 0' }" />
      <div class="style-section">
        <span class="label">附加选项：</span>
        <div class="style-grid">
          <button
            type="button"
            class="style-btn"
            :class="{ active: recoveryStyle }"
            :disabled="loading"
            @click="recoveryStyle = !recoveryStyle"
          >
            体现主恢复色彩
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
      <p v-if="loading" class="loading-hint">请耐心等待，多个风格会一起处理</p>
    </a-card>

    <div v-if="error" class="error">{{ error }}</div>

    <div v-if="results.length" class="results-grid">
      <a-card
        v-for="item in results"
        :key="item.key"
        class="result-card"
      >
        <template #title>
          <span>{{ item.label }}</span>
          <button type="button" class="copy-btn" @click="copyResult(item)">
            <CopyOutlined />
            {{ copiedKey === item.key ? "已复制" : "复制" }}
          </button>
        </template>
        <pre class="result-body">{{ item.text }}</pre>
      </a-card>
    </div>
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

.style-main {
  color: #333;
}

.style-sub {
  color: inherit;
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

.results-grid {
  margin-top: 20px;
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: flex-start;
}

.result-card {
  flex: 1 1 360px;
  min-width: 300px;
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

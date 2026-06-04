<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { LeftOutlined } from "@ant-design/icons-vue";

const router = useRouter();

const query = ref("");
const outlineNature = ref("一般性");
const burdenDescription = ref("");
const loading = ref(false);
const error = ref(null);
const answer = ref(null);
const chunksUsed = ref(0);
const chunksData = ref([]);
const showChunks = ref(false);
const toast = ref("");

const outlineNatureOptions = ["一般性", "真理启示", "生命经历", "应用实行"];

function showToast(msg) {
  toast.value = msg;
  setTimeout(() => {
    if (toast.value === msg) toast.value = "";
  }, 2500);
}

function copyResult() {
  if (!answer.value) return;
  const text = query.value ? `${query.value}\n\n${answer.value}` : answer.value;
  navigator.clipboard.writeText(text).then(() => showToast("已复制到剪贴板"));
}

function clearAll() {
  query.value = "";
  outlineNature.value = "一般性";
  burdenDescription.value = "";
  answer.value = null;
  error.value = null;
  chunksUsed.value = 0;
  chunksData.value = [];
  showChunks.value = false;
}

function toggleChunks() {
  showChunks.value = !showChunks.value;
}

async function generate() {
  const text = (query.value || "").trim();
  if (!text) {
    error.value = "请先输入纲目主题";
    answer.value = null;
    return;
  }
  loading.value = true;
  error.value = null;
  answer.value = null;
  chunksUsed.value = 0;
  chunksData.value = [];
  showChunks.value = false;

  try {
    const res = await fetch("/api/testa/generate_outline/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: text,
        outline_nature: outlineNature.value || "一般性",
        burden_description: burdenDescription.value || "",
        audience: "",
      }),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      error.value = errData.detail || errData.error || "生成失败，请稍后重试";
      return;
    }
    const data = await res.json();
    if (data.answer) {
      answer.value = data.answer;
      chunksUsed.value = data.chunks_used || 0;
      chunksData.value = data.chunks || [];
      showToast("纲目生成完成！");
    } else {
      error.value = "生成失败，请稍后重试";
    }
  } catch (err) {
    error.value = (err && err.message) || "网络错误，请稍后重试";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="page">
    <div v-if="toast" class="toast">{{ toast }}</div>

    <!-- 顶栏 -->
    <div class="header">
      <a-button type="text" class="back-btn" @click="router.back()">
        <template #icon><LeftOutlined /></template>
      </a-button>
      <span class="header-title">PanAI 纲目生成</span>
    </div>

    <!-- 版本切换 -->
    <div class="version-bar">
      <div class="ver-btn active">PanAI 2.0</div>
      <div class="ver-btn disabled">PanAI 3.5</div>
    </div>

    <!-- 输入卡片 -->
    <div class="card">
      <div class="field">
        <label class="field-label">纲目主题 <span class="required">*</span></label>
        <a-input
          v-model:value="query"
          placeholder="请输入纲目主题，如：基督是我们的生命"
          :disabled="loading"
          size="large"
        />
      </div>

      <div class="field">
        <label class="field-label">纲目性质</label>
        <div class="seg-group">
          <div
            v-for="opt in outlineNatureOptions"
            :key="opt"
            class="seg-btn"
            :class="{ active: outlineNature === opt, disabled: loading }"
            @click="!loading && (outlineNature = opt)"
          >
            {{ opt }}
          </div>
        </div>
      </div>

      <div class="field">
        <label class="field-label">
          负担说明
          <span class="optional">（可选）</span>
        </label>
        <a-textarea
          v-model:value="burdenDescription"
          placeholder="请输入负担说明…"
          :disabled="loading"
          :auto-size="{ minRows: 2, maxRows: 4 }"
        />
      </div>

      <div class="divider" />

      <div class="action-row">
        <a-button class="clear-btn" :disabled="loading" @click="clearAll">
          清空
        </a-button>
        <a-button
          type="primary"
          class="generate-btn"
          :loading="loading"
          :disabled="loading"
          @click="generate"
        >
          {{ loading ? "生成中…" : "生成纲目" }}
        </a-button>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="error-msg">{{ error }}</div>

    <!-- 结果卡片 -->
    <div v-if="answer" class="card result-card">
      <div class="result-head">
        <span class="result-title-text">生成结果</span>
        <span class="chunks-badge" @click="toggleChunks">
          参考段落 {{ chunksUsed }} 条
        </span>
        <button class="copy-btn" @click="copyResult">复制</button>
      </div>
      <div class="divider" />
      <div class="result-topic">{{ query }}</div>
      <pre class="result-body">{{ answer }}</pre>
    </div>

    <!-- 参考段落卡片 -->
    <div v-if="answer && showChunks" class="card chunks-card">
      <div class="chunks-title">参考段落</div>
      <div
        v-for="(chunk, idx) in chunksData"
        :key="idx"
        class="chunk-item"
      >
        <div class="chunk-source">
          出处：<span>{{ chunk.book_title }}</span>
          {{ chunk.message_number ? ` 第${chunk.message_number}篇` : "" }}
          {{ chunk.message_title || "" }}
        </div>
        <div class="chunk-text">
          {{ (chunk.text || "").slice(0, 50) }}…
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.toast {
  position: fixed;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: #52c41a;
  color: #fff;
  padding: 8px 24px;
  border-radius: 20px;
  font-size: 14px;
  z-index: 9999;
  pointer-events: none;
}
.page {
  min-height: 100vh;
  background: #f5f5f5;
  padding-bottom: 40px;
}
.header {
  background: #001529;
  padding: 0 20px;
  height: 52px;
  display: flex;
  align-items: center;
  position: relative;
}
.back-btn {
  color: #55bbff;
  font-size: 18px;
  position: absolute;
  left: 12px;
}
.header-title {
  color: #fff;
  font-size: 16px;
  font-weight: 500;
  flex: 1;
  text-align: center;
}
.version-bar {
  display: flex;
  gap: 8px;
  padding: 16px 16px 0;
}
.ver-btn {
  flex: 1;
  padding: 9px 0;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  border: 1px solid #d9d9d9;
  background: #fff;
  color: #8c8c8c;
  text-align: center;
  cursor: default;
}
.ver-btn.active {
  background: #1890ff;
  border-color: #1890ff;
  color: #fff;
}
.ver-btn.disabled {
  opacity: 0.45;
}
.card {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  margin: 12px 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
.field {
  margin-bottom: 14px;
}
.field:last-child {
  margin-bottom: 0;
}
.field-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: #333;
  margin-bottom: 6px;
}
.required {
  color: #ff4d4f;
}
.optional {
  font-weight: 400;
  color: #8c8c8c;
  font-size: 12px;
}
.seg-group {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.seg-btn {
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid #d9d9d9;
  background: #fff;
  color: #555;
  font-size: 13px;
  cursor: pointer;
  user-select: none;
  transition: all 0.15s;
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
.seg-btn.disabled {
  opacity: 0.65;
  cursor: not-allowed;
}
.divider {
  height: 1px;
  background: #f0f0f0;
  margin: 12px 0;
}
.action-row {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}
.clear-btn {
  font-weight: 500;
  border-color: #d9d9d9;
  color: #666;
}
.clear-btn:hover {
  border-color: #ff4d4f;
  color: #ff4d4f;
}
.generate-btn {
  background: #1890ff;
  border-color: #1890ff;
  min-width: 110px;
  font-weight: 500;
}
.generate-btn:hover {
  background: #40a9ff;
  border-color: #40a9ff;
}
.error-msg {
  margin: 0 16px 12px;
  color: #cf1322;
  font-size: 13px;
  padding: 8px 12px;
  background: #fff2f0;
  border-radius: 6px;
  border: 1px solid #ffccc7;
}
.result-card {
  margin-top: 0;
}
.result-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.result-title-text {
  font-size: 14px;
  font-weight: 500;
  color: #333;
  flex: 1;
}
.chunks-badge {
  font-size: 11px;
  color: #1890ff;
  background: #e6f7ff;
  border: 1px solid #91d5ff;
  border-radius: 10px;
  padding: 2px 10px;
  cursor: pointer;
  user-select: none;
}
.chunks-badge:hover {
  background: #bae7ff;
}
.copy-btn {
  background: #fff;
  border: 1px solid #d9d9d9;
  color: #555;
  padding: 3px 14px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}
.copy-btn:hover {
  color: #1890ff;
  border-color: #1890ff;
}
.result-topic {
  text-align: center;
  font-weight: 500;
  font-size: 15px;
  color: #333;
  padding: 10px 0 6px;
}
.result-body {
  font-size: 14px;
  color: #333;
  line-height: 1.9;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
}
.chunks-card {
  margin-top: 0;
}
.chunks-title {
  font-size: 13px;
  font-weight: 500;
  color: #333;
  margin-bottom: 10px;
}
.chunk-item {
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}
.chunk-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}
.chunk-source {
  font-size: 12px;
  color: #8c8c8c;
  margin-bottom: 3px;
}
.chunk-source span {
  color: #1890ff;
  font-weight: 500;
}
.chunk-text {
  font-size: 12px;
  color: #aaa;
  line-height: 1.6;
}
</style>

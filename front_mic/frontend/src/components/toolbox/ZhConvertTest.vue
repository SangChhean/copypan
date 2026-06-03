<script setup>
import { ref, computed } from "vue";
import { message } from "ant-design-vue";
import { LoadingOutlined, CopyOutlined } from "@ant-design/icons-vue";
import ToolsHeader from "./ToolsHeader.vue";

const apiBase = "http://localhost:8005";

const direction = ref("s2t"); // s2t | t2s
const content = ref("");
const loading = ref(false);
const result = ref("");

const isS2t = computed(() => direction.value === "s2t");
const inputPlaceholder = computed(() =>
  isS2t.value ? "请粘贴简体中文…" : "请粘贴繁体中文…"
);

async function convert() {
  const text = (content.value || "").trim();
  if (!text) {
    message.error("请先粘贴要转换的内容");
    return;
  }
  loading.value = true;
  result.value = "";
  const endpoint = isS2t.value
    ? `${apiBase}/api/testb/zh_convert`
    : `${apiBase}/api/testb/zh_to_simplified`;
  const fieldName = isS2t.value ? "answer_zh_tw" : "answer_zh_cn";
  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ content: text }),
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      let detail = errorData.detail;
      if (Array.isArray(detail)) {
        detail = detail.map((x) => x?.msg || x?.message || JSON.stringify(x)).join("；");
      }
      message.error(detail || errorData.error || errorData.message || "转换失败，请稍后重试");
      return;
    }

    const data = await res.json();
    const answer = data[fieldName];
    if (data.error && !answer) {
      message.error(data.error);
      return;
    }
    if (answer) {
      result.value = answer;
    } else {
      message.error("转换失败，请稍后重试");
    }
  } catch (err) {
    message.error(
      (err && err.message) ||
        (typeof err === "string" ? err : "") ||
        "网络错误，请稍后重试"
    );
  } finally {
    loading.value = false;
  }
}

function copyResult() {
  if (!result.value) return;
  navigator.clipboard
    .writeText(result.value)
    .then(() => {
      message.success("已复制");
    })
    .catch(() => {
      message.error("复制失败");
    });
}
</script>

<template>
  <ToolsHeader title="简繁互转测试" />
  <div class="box">
    <a-card>
      <p class="hint">
        选择转换方向后，粘贴内容并点「转换」即可（无下载、无登录）。
      </p>
      <a-divider :style="{ margin: '12px 0' }" />

      <div class="direction-row">
        <span class="label">转换方向：</span>
        <a-segmented
          v-model:value="direction"
          class="direction-segmented"
          :options="[
            { label: '简体 → 繁体', value: 's2t' },
            { label: '繁体 → 简体', value: 't2s' },
          ]"
        />
      </div>

      <a-divider :style="{ margin: '12px 0' }" />
      <div class="textarea-wrap">
        <a-textarea
          v-model:value="content"
          :placeholder="inputPlaceholder"
          :disabled="loading"
          allow-clear
          class="content-area"
        />
      </div>

      <div class="action-row">
        <button
          type="button"
          class="action-btn clear-btn"
          :disabled="loading || !content"
          @click="content = ''; result = ''"
        >
          清空
        </button>
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
    </a-card>

    <a-card v-if="result" class="result-card">
      <template #title>
        <span>转换结果</span>
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
}

.content-area :deep(.ant-input) {
  border-radius: 8px;
  font-family: inherit;
  height: calc(100vh - 420px) !important;
  min-height: 400px !important;
  resize: none !important;
  overflow-y: auto !important;
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

.clear-btn {
  background: #fff;
  color: #555;
  border: 1px solid #d9d9d9;
}
.clear-btn:hover:not(:disabled) {
  background: #fff;
  color: #ff4d4f;
  border-color: #ff4d4f;
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

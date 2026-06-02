<script setup>
import { ref, computed } from "vue";
import { message } from "ant-design-vue";
import { LoadingOutlined, CopyOutlined } from "@ant-design/icons-vue";
import ToolsHeader from "./ToolsHeader.vue";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";
/** 与后端 OutlineTranslateRequest / translate_outline 一致（字符数，非 token） */
const MAX_CONTENT_CHARS = 100_000;

const direction = ref("zh2en"); // zh2en | en2zh
const content = ref("");
const loading = ref(false);
const result = ref("");

const isZh2En = computed(() => direction.value === "zh2en");
const inputPlaceholder = computed(() => {
  if (direction.value === "zh2en") return "请粘贴中文纲目正文…";
  if (direction.value === "en2zh") return "请粘贴英文纲目正文…";
  return "请粘贴中文纲目正文…";
});

async function translate() {
  const text = (content.value || "").trim();
  if (!text) {
    message.error("请先粘贴纲目正文");
    return;
  }
  if (text.length > MAX_CONTENT_CHARS) {
    message.error(`正文过长：最多 ${MAX_CONTENT_CHARS.toLocaleString()} 字，请分段翻译`);
    return;
  }
  const authToken = localStorage.getItem("token") || null;
  if (!authToken) {
    window.location.hash = "/login";
    return;
  }
  loading.value = true;
  result.value = "";
  try {
    const body = {
      content: text,
      direction: direction.value,
      outline_topic: null,
    };
    const res = await fetch(`${apiBase}/api/ai_search/outline_translate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${authToken}`,
      },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      let detail = errorData.detail;
      if (Array.isArray(detail)) {
        detail = detail.map((x) => x?.msg || x?.message || JSON.stringify(x)).join("；");
      }
      message.error(detail || errorData.error || errorData.message || "翻译失败，请稍后重试");
      return;
    }

    const data = await res.json();
    if (data.error && !data.result) {
      message.error(data.error);
      return;
    }
    if (data.result) {
      result.value = data.result;
    } else {
      message.error("翻译失败，请稍后重试");
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
  <ToolsHeader title="纲目翻译测试" />
  <div class="box">
    <a-card>
      <p class="hint">
        粘贴纲目正文后点「翻译」即可。<strong>输入上限
        {{ MAX_CONTENT_CHARS.toLocaleString() }} 字</strong>，过长请分段翻译。
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
            { label: '中文 → 韩文', value: 'zh2ko' },
          ]"
        />
      </div>

      <a-divider :style="{ margin: '12px 0' }" />
      <div class="textarea-wrap">
        <a-textarea
          v-model:value="content"
          :placeholder="inputPlaceholder"
          :disabled="loading"
          :maxlength="MAX_CONTENT_CHARS"
          show-count
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
          @click="translate"
        >
          <LoadingOutlined v-if="loading" class="btn-icon btn-spin" />
          <span v-if="loading">翻译中…</span>
          <span v-else>翻译</span>
        </button>
      </div>
      <p v-if="loading" class="loading-hint">请耐心等待 1～2 分钟</p>
    </a-card>

    <a-card v-if="result" class="result-card">
      <template #title>
        <span>翻译结果</span>
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

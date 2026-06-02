<!-- 纲目翻译测试：连接 test_B 独立后端 http://localhost:8002 -->
<script setup>
import { ref, computed } from "vue";
import ToolsHeader from "./ToolsHeader.vue";

const apiBase = "http://localhost:8002";
const MAX_CONTENT_CHARS = 100_000;

const direction = ref("zh2en");
const content = ref("");
const loading = ref(false);
const error = ref(null);
const result = ref(null);
const toast = ref("");

const inputPlaceholder = computed(() => {
  if (direction.value === "zh2en") return "请粘贴中文纲目全文…";
  if (direction.value === "en2zh") return "请粘贴英文纲目全文…";
  return "请粘贴中文纲目全文…";
});

const resultTitle = computed(() => {
  if (direction.value === "zh2en") return "英文纲目";
  if (direction.value === "en2zh") return "中文纲目";
  return "韩文纲目";
});

const charCount = computed(() => (content.value || "").length);

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
    error.value = "请先粘贴纲目正文";
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
    };
    const res = await fetch(`${apiBase}/api/test_b/translate/translate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
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
        detail = detail
          .map((x) => x?.msg || x?.message || JSON.stringify(x))
          .join("；");
      }
      error.value =
        detail || errorData.error || errorData.message || "翻译失败，请稍后重试";
      return;
    }
    const data = await res.json();
    if (data.error && !data.result) {
      error.value = data.error;
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
      showToast("翻译完成！");
    } else {
      error.value = "翻译失败，请稍后重试";
    }
  } catch (err) {
    error.value =
      (err && err.message) ||
      (typeof err === "string" ? err : "") ||
      "网络错误，请稍后重试";
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
</script>

<template>
  <ToolsHeader title="纲目翻译测试（test_B）" />
  <div v-if="toast" class="toast">{{ toast }}</div>
  <div class="box">
    <section class="card">
      <p class="hint">
        独立后端 <code>{{ apiBase }}</code>：粘贴纲目后点「翻译」即可。
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
            :class="{ active: direction === 'zh2ko' }"
            @click="direction = 'zh2ko'"
          >
            中文 → 韩文
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
          <span class="char-count"
            >{{ charCount.toLocaleString() }} /
            {{ MAX_CONTENT_CHARS.toLocaleString() }}</span
          >
          <button
            type="button"
            class="clear-btn"
            :disabled="!content || loading"
            @click="content = ''; result = null; error = null"
          >
            清空
          </button>
        </div>
      </div>
      <div class="action-row">
        <button
          type="button"

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
          <span v-if="loading" class="spin">⟳</span>
          <span>{{ loading ? "翻译中…" : "翻译" }}</span>
        </button>
      </div>
      <p v-if="loading" class="loading-hint">请耐心等待 1～2 分钟</p>
    </section>

    <p v-if="error" class="error">{{ error }}</p>

    <section v-if="result" class="card result-card">
      <div class="result-head">
        <span>{{ resultTitle }}</span>
        <button type="button" class="copy-btn" @click="copyResult">复制</button>
      </div>
      <pre class="result-body">{{ result }}</pre>
    </section>
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

.box :deep(.ant-card) {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.06);
}

.hint {
  color: #555;
  margin: 0;
  font-size: 0.95em;
  line-height: 1.5;
}
.hint code {
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
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
.action-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}
.spin {
  display: inline-block;
  animation: spin 1s linear infinite;
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

<template>
  <div class="container">
    <button class="btn btn-back" type="button" @click="goBack">← 返回</button>
    <h1 class="title">AI 纲目制作练习</h1>

    <label class="label">纲目主题</label>
    <input
      v-model="query"
      class="input"
      type="text"
      placeholder="请输入纲目主题"
      :disabled="loading"
    />

    <label class="label">纲目性质</label>
    <div class="nature-row">
      <button
        v-for="opt in natureOptions"
        :key="opt"
        type="button"
        class="btn btn-nature"
        :class="{ active: outlineNature === opt }"
        :disabled="loading"
        @click="outlineNature = opt"
      >
        {{ opt }}
      </button>
    </div>

    <label class="label">负担说明（可选）</label>
    <textarea
      v-model="burdenDescription"
      class="textarea"
      rows="4"
      placeholder="可填写负担说明…"
      :disabled="loading"
    />

    <div class="btn-row">
      <button class="btn btn-primary" type="button" :disabled="loading" @click="generate">
        {{ loading ? "生成中…" : "生成纲目" }}
      </button>
    </div>
    <p v-if="emptyError" class="error-msg">请先输入纲目主题</p>
    <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>

    <div v-if="result" class="result-box">
      <div class="result-header">
        <span>生成结果</span>
        <button class="btn btn-copy" type="button" @click="copyResult">
          {{ copied ? "已复制" : "复制" }}
        </button>
      </div>
      <pre class="result-pre">{{ result }}</pre>
      <FormatDownloadBar
        :text="fullText()"
        direction="zh"
        api-endpoint="/api/practice/kg_rag/format_download"
      />
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";
import FormatDownloadBar from "./FormatDownloadBar.vue";

const natureOptions = ["一般性", "真理启示", "生命经历", "应用实行"];

const query = ref("");
const outlineNature = ref("一般性");
const burdenDescription = ref("");
const result = ref("");
const loading = ref(false);
const emptyError = ref(false);
const errorMsg = ref("");
const copied = ref(false);

function goBack() {
  window.location.hash = "/tools";
}

function fullText() {
  const topic = query.value.trim();
  const body = result.value || "";
  return topic ? `${topic}\n\n${body}` : body;
}

async function generate() {
  emptyError.value = false;
  errorMsg.value = "";
  result.value = "";
  if (!query.value.trim()) {
    emptyError.value = true;
    return;
  }
  loading.value = true;
  try {
    const res = await fetch("/api/practice/kg_rag/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query.value.trim(),
        outline_nature: outlineNature.value,
        burden_description: burdenDescription.value.trim(),
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      errorMsg.value = data.detail || data.error || `请求失败（${res.status}）`;
    } else if (data.error) {
      errorMsg.value = data.error;
    } else if (data.answer) {
      result.value = data.answer;
    } else {
      errorMsg.value = "未返回纲目内容";
    }
  } catch (e) {
    errorMsg.value = e?.message || "网络错误，请稍后重试";
  } finally {
    loading.value = false;
  }
}

async function copyResult() {
  if (!result.value) return;
  try {
    await navigator.clipboard.writeText(result.value);
    copied.value = true;
    setTimeout(() => {
      copied.value = false;
    }, 2000);
  } catch (_) {
    /* ignore */
  }
}

</script>

<style scoped>
:global(body) {
  background-color: #f7f5f0;
}

.container {
  max-width: 920px;
  margin: 0 auto;
  padding: 28px 24px;
  background: #f7f5f0;
  color: #2d2d2d;
  font-family: sans-serif;
}

.title {
  font-size: 22px;
  font-weight: 700;
  color: #2d2d2d;
  text-align: center;
  margin-bottom: 24px;
  padding-bottom: 12px;
  border-bottom: 2px solid #dde3e9;
}

.label {
  display: block;
  margin-bottom: 8px;
  font-weight: 600;
  color: #2d2d2d;
  font-size: 15px;
}

.input {
  width: 100%;
  box-sizing: border-box;
  padding: 12px 16px;
  font-size: 15px;
  line-height: 1.6;
  margin-bottom: 20px;
  border: 1.5px solid #dde3e9;
  border-radius: 8px;
  background: #fdfcfb;
  color: #2d2d2d;
  outline: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.input:focus {
  border-color: #2c5f8a;
  box-shadow: 0 0 0 3px rgba(44, 95, 138, 0.1);
}
.input:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.nature-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 20px;
}

.btn-nature {
  padding: 8px 20px;
  font-size: 14px;
  font-weight: 500;
  border: 1.5px solid #dde3e9;
  border-radius: 20px;
  background: #fff;
  color: #555;
  cursor: pointer;
  transition: all 0.2s ease;
}
.btn-nature:hover:not(.active):not(:disabled) {
  border-color: #2c5f8a;
  color: #2c5f8a;
}
.btn-nature.active {
  background: #2c5f8a;
  color: #fff;
  border-color: #2c5f8a;
  box-shadow: 0 2px 6px rgba(44, 95, 138, 0.25);
}
.btn-nature:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 12px 16px;
  font-size: 15px;
  line-height: 1.8;
  margin-bottom: 20px;
  border: 1.5px solid #dde3e9;
  border-radius: 8px;
  background: #fdfcfb;
  color: #2d2d2d;
  resize: vertical;
  outline: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.textarea:focus {
  border-color: #2c5f8a;
  box-shadow: 0 0 0 3px rgba(44, 95, 138, 0.1);
}
.textarea:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.btn-row {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}

.btn {
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-primary {
  background: #2c5f8a;
  color: #fff;
  font-weight: 500;
  border-radius: 6px;
  padding: 10px 36px;
  font-size: 16px;
  border: none;
}
.btn-primary:hover:not(:disabled) {
  background: #1e4a6e;
}
.btn-primary:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.btn-back {
  background: transparent;
  color: #6b6b6b;
  border: 1.5px solid #dde3e9;
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 13px;
  margin-bottom: 20px;
  cursor: pointer;
}
.btn-back:hover {
  border-color: #2c5f8a;
  color: #2c5f8a;
}

.btn-copy {
  border: 1.5px solid #2c5f8a;
  color: #2c5f8a;
  background: #fff;
  border-radius: 4px;
  padding: 5px 14px;
  font-size: 12px;
  cursor: pointer;
}
.btn-copy:hover {
  background: #e8f0f7;
}

.error-msg {
  color: #c0392b;
  margin-top: 8px;
  font-size: 13px;
}

.result-box {
  margin-top: 24px;
  padding: 20px;
  border: 1px solid #dde3e9;
  border-radius: 10px;
  background: #ffffff;
  box-shadow: 0 2px 12px rgba(44, 95, 138, 0.08);
}

.result-header {
  color: #2c5f8a;
  font-weight: 600;
  font-size: 14px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.result-pre {
  white-space: pre-wrap;
  line-height: 1.8;
  color: #2d2d2d;
  font-size: 15px;
  margin: 0;
  font-family: inherit;
}
</style>

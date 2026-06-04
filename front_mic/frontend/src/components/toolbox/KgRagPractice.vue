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
      <div class="download-row">
        <button
          class="btn btn-download"
          type="button"
          :disabled="downloadingDocx"
          @click="download('docx')"
        >
          {{ downloadingDocx ? "下载中…" : "下载 DOCX" }}
        </button>
        <button
          class="btn btn-download"
          type="button"
          :disabled="downloadingPdf"
          @click="download('pdf')"
        >
          {{ downloadingPdf ? "下载中…" : "下载 PDF" }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";

const natureOptions = ["一般性", "真理启示", "生命经历", "应用实行"];

const query = ref("");
const outlineNature = ref("一般性");
const burdenDescription = ref("");
const result = ref("");
const loading = ref(false);
const emptyError = ref(false);
const errorMsg = ref("");
const copied = ref(false);
const downloadingDocx = ref(false);
const downloadingPdf = ref(false);

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

function doDownload(data, format) {
  const baseName = (query.value.trim() || "outline_zh").replace(/[\\/:*?"<>|]/g, "_");
  if (format === "docx" && data.docx_base64) {
    const bin = Uint8Array.from(atob(data.docx_base64), (c) => c.charCodeAt(0));
    const blob = new Blob([bin], {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = data.filename || `${baseName}.docx`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } else if (format === "pdf") {
    if (data.pdf_base64) {
      const bin = Uint8Array.from(atob(data.pdf_base64), (c) => c.charCodeAt(0));
      const blob = new Blob([bin], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = data.filename || `${baseName}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } else if (data.docx_base64) {
      const bin = Uint8Array.from(atob(data.docx_base64), (c) => c.charCodeAt(0));
      const blob = new Blob([bin], {
        type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = (data.filename || baseName).replace(/\.pdf$/i, ".docx");
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      errorMsg.value = "PDF 转换失败，已下载 DOCX";
    }
  }
}

async function download(format) {
  if (!result.value) return;
  const token = localStorage.getItem("token");
  if (!token) {
    window.location.hash = "/login";
    return;
  }
  if (format === "docx") downloadingDocx.value = true;
  else downloadingPdf.value = true;
  try {
    const res = await fetch("/api/ai_search/format_outline_only", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        direction: "en2zh",
        translated_text: fullText(),
        output_format: format,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      errorMsg.value = data.detail || data.error || "下载失败";
      return;
    }
    doDownload(data, format);
  } catch (e) {
    errorMsg.value = e?.message || "下载失败";
  } finally {
    if (format === "docx") downloadingDocx.value = false;
    else downloadingPdf.value = false;
  }
}
</script>

<style scoped>
.container {
  max-width: 1100px;
  margin: 32px auto;
  padding: 40px;
  background: #f8f9fa;
  border-radius: 12px;
  color: #1a1a2e;
  font-family: sans-serif;
}
.title {
  text-align: center;
  font-size: 24px;
  margin-bottom: 24px;
  color: #5c4db1;
  font-weight: 600;
}
.label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #495057;
}
.input {
  width: 100%;
  box-sizing: border-box;
  background: #fff;
  border: 1px solid #ced4da;
  border-radius: 8px;
  color: #212529;
  font-size: 15px;
  padding: 12px;
  margin-bottom: 16px;
}
.nature-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}
.btn-nature {
  padding: 8px 16px;
  border-radius: 8px;
  background: #e9ecef;
  color: #495057;
  border: 1px solid #dee2e6;
  font-size: 14px;
  cursor: pointer;
}
.btn-nature.active {
  background: #5c4db1;
  color: #fff;
  font-weight: bold;
  border-color: #5c4db1;
}
.btn-nature:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.textarea {
  width: 100%;
  box-sizing: border-box;
  background: #fff;
  border: 1px solid #ced4da;
  border-radius: 8px;
  color: #212529;
  font-size: 15px;
  padding: 12px;
  resize: vertical;
  margin-bottom: 16px;
}
.btn-row {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}
.btn {
  padding: 10px 24px;
  border: none;
  border-radius: 8px;
  font-size: 15px;
  cursor: pointer;
}
.btn-primary {
  background: #5c4db1;
  color: #fff;
  font-weight: bold;
}
.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.btn-back {
  background: transparent;
  color: #6c757d;
  border: 1px solid #ced4da;
  margin-bottom: 16px;
  padding: 6px 16px;
  font-size: 13px;
}
.btn-copy {
  background: #e9ecef;
  color: #495057;
  padding: 6px 16px;
  font-size: 13px;
}
.btn-download {
  background: #5c4db1;
  color: #fff;
  font-size: 14px;
}
.btn-download:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.error-msg {
  color: #dc3545;
  margin-top: 12px;
}
.result-box {
  margin-top: 24px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #dee2e6;
  padding: 16px;
}
.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-weight: bold;
  color: #5c4db1;
}
.result-pre {
  white-space: pre-wrap;
  line-height: 1.8;
  color: #212529;
  font-size: 15px;
  margin: 0;
  font-family: inherit;
}
.download-row {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}
</style>

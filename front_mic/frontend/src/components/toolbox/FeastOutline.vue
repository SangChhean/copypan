<script setup>
import ToolsHeader from "./ToolsHeader.vue";
import { ref, computed } from "vue";
import { DownloadOutlined, CopyOutlined } from "@ant-design/icons-vue";
import { toastSuccess, toastWarning } from "../utils/Dialog";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";

// 五类节期纲目（多选）
const feastOutlineTypes = [
  { label: "纲目的原文", value: "original", desc: "刷格式" },
  { label: "带经文的纲目", value: "with_scripture", desc: "经文汇集 + 刷格式" },
  { label: "晨兴信息选读的纲目", value: "morning_revival", desc: "Claude 生成 + 刷格式" },
  { label: "听抄稿的纲目", value: "transcript", desc: "原纲目 + 听抄稿重点" },
  { label: "复合的纲目", value: "composite", desc: "听抄稿纲目 + 晨兴纲目融合" },
];

const selectedTypes = ref([]);
// 三个统一输入框
const inputOutline = ref("");       // ① 纲目原文
const inputMorningRevival = ref(""); // ② 晨兴信息选读
const inputTranscript = ref("");     // ③ 听抄稿

const loading = ref(false);
const results = ref([]); // { type, type_label, content }
const formatDownloading = ref(false);

// 按类型分组结果（用于刷格式并下载）
const originalResults = computed(() => results.value.filter((r) => r.type === "original"));
const withScriptureResults = computed(() => results.value.filter((r) => r.type === "with_scripture"));
const morningRevivalResults = computed(() => results.value.filter((r) => r.type === "morning_revival"));
const transcriptResults = computed(() => results.value.filter((r) => r.type === "transcript"));
const compositeResults = computed(() => results.value.filter((r) => r.type === "composite"));

function getAuthHeaders() {
  const token = localStorage.getItem("token") || null;
  if (!token) {
    window.location.hash = "/login";
    return null;
  }
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
}

function getTypeLabel(value) {
  return feastOutlineTypes.find((t) => t.value === value)?.label || value;
}

function toggleType(value) {
  const i = selectedTypes.value.indexOf(value);
  if (i > -1) selectedTypes.value.splice(i, 1);
  else selectedTypes.value.push(value);
}

// 校验：选中某类型时所需输入是否已填
function canGenerate() {
  const o = (inputOutline.value || "").trim();
  const m = (inputMorningRevival.value || "").trim();
  const t = (inputTranscript.value || "").trim();
  if (selectedTypes.value.length === 0) return false;
  if (selectedTypes.value.includes("original") && !o) return false;
  if (selectedTypes.value.includes("with_scripture") && !o) return false;
  if (selectedTypes.value.includes("morning_revival") && !m) return false;
  if (selectedTypes.value.includes("transcript") && (!o || !t)) return false;
  if (selectedTypes.value.includes("composite")) {
    // 复合需要先有晨兴纲目和听抄稿纲目，本轮生成时会自动跑
    if (!m || !o || !t) return false;
  }
  return true;
}

// 批量生成
async function generateAll() {
  if (!canGenerate()) {
    toastWarning("请至少选择一种类型，并填齐对应输入（纲目原文/晨兴/听抄稿）");
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;

  const o = (inputOutline.value || "").trim();
  const m = (inputMorningRevival.value || "").trim();
  const t = (inputTranscript.value || "").trim();

  loading.value = true;
  results.value = [];
  const newResults = [];
  const errors = [];

  try {
    // 1. 纲目的原文：直接用 ① 作为结果
    if (selectedTypes.value.includes("original") && o) {
      newResults.push({ type: "original", type_label: getTypeLabel("original"), content: o });
    }

    // 2. 带经文的纲目：经文汇集 ①
    if (selectedTypes.value.includes("with_scripture") && o) {
      try {
        const res = await fetch(`${apiBase}/api/ai_search/feast_outline/scripture_text`, {
          method: "POST",
          headers,
          body: JSON.stringify({ content: o }),
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok && data.content != null) {
          newResults.push({
            type: "with_scripture",
            type_label: getTypeLabel("with_scripture"),
            content: data.content,
          });
        } else {
          errors.push(`带经文的纲目: ${data.detail || data.error || "失败"}`);
        }
      } catch (err) {
        errors.push(`带经文的纲目: ${err.message || "网络错误"}`);
      }
    }

    // 3. 晨兴信息选读的纲目、4. 听抄稿的纲目：可并行
    let morningRevivalOutline = "";
    let transcriptOutline = "";

    const runMorningRevival = async () => {
      if (!selectedTypes.value.includes("morning_revival") && !selectedTypes.value.includes("composite")) return "";
      if (!m) return "";
      const res = await fetch(`${apiBase}/api/ai_search/feast_outline/generate/morning_revival`, {
        method: "POST",
        headers,
        body: JSON.stringify({ content: m }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.outline != null) return data.outline;
      errors.push(`晨兴信息选读的纲目: ${data.detail || data.error || "失败"}`);
      return "";
    };

    const runTranscript = async () => {
      if (!selectedTypes.value.includes("transcript") && !selectedTypes.value.includes("composite")) return "";
      if (!o || !t) return "";
      const res = await fetch(`${apiBase}/api/ai_search/feast_outline/generate/transcript`, {
        method: "POST",
        headers,
        body: JSON.stringify({ original_outline: o, transcript: t }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.outline != null) return data.outline;
      errors.push(`听抄稿的纲目: ${data.detail || data.error || "失败"}`);
      return "";
    };

    const [out1, out2] = await Promise.all([runMorningRevival(), runTranscript()]);
    morningRevivalOutline = out1;
    transcriptOutline = out2;

    if (selectedTypes.value.includes("morning_revival") && morningRevivalOutline) {
      newResults.push({
        type: "morning_revival",
        type_label: getTypeLabel("morning_revival"),
        content: morningRevivalOutline,
      });
    }
    if (selectedTypes.value.includes("transcript") && transcriptOutline) {
      newResults.push({
        type: "transcript",
        type_label: getTypeLabel("transcript"),
        content: transcriptOutline,
      });
    }

    // 5. 复合的纲目：需要听抄稿纲目 + 晨兴纲目
    if (selectedTypes.value.includes("composite") && transcriptOutline && morningRevivalOutline) {
      try {
        const res = await fetch(`${apiBase}/api/ai_search/feast_outline/generate/composite`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            transcript_outline: transcriptOutline,
            morning_revival_outline: morningRevivalOutline,
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok && data.outline) {
          newResults.push({
            type: "composite",
            type_label: getTypeLabel("composite"),
            content: data.outline,
          });
        } else {
          errors.push(`复合的纲目: ${data.detail || data.error || "失败"}`);
        }
      } catch (err) {
        errors.push(`复合的纲目: ${err.message || "网络错误"}`);
      }
    } else if (selectedTypes.value.includes("composite") && (!transcriptOutline || !morningRevivalOutline)) {
      errors.push("复合的纲目: 需先生成听抄稿纲目与晨兴纲目（请确保 ①②③ 已填并勾选对应类型）");
    }

    results.value = newResults;
    if (newResults.length) toastSuccess(`成功生成 ${newResults.length} 类节期纲目`);
    if (errors.length) toastWarning(errors.join("；"));
  } finally {
    loading.value = false;
  }
}

// 刷格式并下载（按类型）
async function downloadFormat(typeKey) {
  const typeToResults = {
    original: originalResults.value,
    with_scripture: withScriptureResults.value,
    morning_revival: morningRevivalResults.value,
    transcript: transcriptResults.value,
    composite: compositeResults.value,
  };
  const list = typeToResults[typeKey] || [];
  const filenameMap = {
    original: "节期纲目_原文.docx",
    with_scripture: "节期纲目_带经文.docx",
    morning_revival: "节期纲目_晨兴信息选读.docx",
    transcript: "节期纲目_听抄稿.docx",
    composite: "节期纲目_复合.docx",
  };
  if (!list.length) {
    toastWarning(`暂无${getTypeLabel(typeKey)}结果`);
    return;
  }
  const contents = list.map((r) => (r.content || "").trim()).filter(Boolean);
  if (!contents.length) {
    toastWarning("所选结果内容为空");
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;
  formatDownloading.value = true;
  try {
    const res = await fetch(`${apiBase}/api/ai_search/feast_outline/format_download`, {
      method: "POST",
      headers,
      body: JSON.stringify({ contents, outline_type: typeKey, filename: filenameMap[typeKey] }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      toastWarning(data.detail || data.error || "下载失败");
      return;
    }
    const b64 = data.docx_base64;
    const filename = data.filename || filenameMap[typeKey];
    if (!b64) {
      toastWarning(data.error || "未返回文件");
      return;
    }
    const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const blob = new Blob([bin], {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    toastSuccess(`已下载：${filename}`);
  } catch (err) {
    toastWarning(err.message || "下载失败");
  } finally {
    formatDownloading.value = false;
  }
}

function copyResult(content) {
  if (!content) return;
  navigator.clipboard.writeText(content).then(() => toastSuccess("已复制到剪贴板"));
}
</script>

<template>
  <ToolsHeader title="节期纲目" />
  <div class="box">
    <a-card>
      <p class="hint">
        节期纲目支持多选类型一起生成。请先选择需要的类型，再在下方填写 ① 纲目原文、② 晨兴信息选读、③ 听抄稿（按类型需要填写），点击「生成节期纲目」后即可在结果中查看并刷格式下载。
      </p>
      <a-divider :style="{ margin: '12px 0' }" />

      <!-- 类型多选 -->
      <div class="type-selection">
        <span class="label">选择类型（可多选）：</span>
        <div class="type-buttons">
          <a-button
            v-for="t in feastOutlineTypes"
            :key="t.value"
            :type="selectedTypes.includes(t.value) ? 'primary' : 'default'"
            @click="toggleType(t.value)"
            class="type-button"
          >
            {{ t.label }}
          </a-button>
        </div>
      </div>

      <!-- 三个输入框 -->
      <a-divider :style="{ margin: '12px 0' }" />
      <div class="label">① 纲目原文</div>
      <a-textarea
        v-model:value="inputOutline"
        placeholder="请粘贴纲目原文（无格式）；用于「纲目的原文」「带经文的纲目」「听抄稿的纲目」等"
        :rows="6"
        :style="{ marginBottom: '12px' }"
      />
      <div class="label">② 晨兴信息选读</div>
      <a-textarea
        v-model:value="inputMorningRevival"
        placeholder="请粘贴晨兴信息选读内容；用于「晨兴信息选读的纲目」及「复合的纲目」"
        :rows="6"
        :style="{ marginBottom: '12px' }"
      />
      <div class="label">③ 听抄稿</div>
      <a-textarea
        v-model:value="inputTranscript"
        placeholder="请粘贴听抄稿内容；用于「听抄稿的纲目」及「复合的纲目」"
        :rows="6"
        :style="{ marginBottom: '16px' }"
      />

      <a-button
        type="primary"
        :loading="loading"
        :disabled="!canGenerate()"
        @click="generateAll"
        :style="{ width: '100%', marginBottom: '20px' }"
      >
        生成节期纲目
      </a-button>

      <!-- 结果与刷格式下载 -->
      <div v-if="results.length > 0" class="results-section">
        <a-divider>生成结果（共 {{ results.length }} 类）</a-divider>
        <div class="format-download-row">
          <span class="format-download-label">刷格式并下载：</span>
          <a-button
            type="primary"
            :loading="formatDownloading"
            :disabled="originalResults.length === 0"
            @click="downloadFormat('original')"
          >
            <DownloadOutlined /> 纲目的原文（{{ originalResults.length }}）
          </a-button>
          <a-button
            type="primary"
            :loading="formatDownloading"
            :disabled="withScriptureResults.length === 0"
            @click="downloadFormat('with_scripture')"
          >
            <DownloadOutlined /> 带经文（{{ withScriptureResults.length }}）
          </a-button>
          <a-button
            type="primary"
            :loading="formatDownloading"
            :disabled="morningRevivalResults.length === 0"
            @click="downloadFormat('morning_revival')"
          >
            <DownloadOutlined /> 晨兴信息选读（{{ morningRevivalResults.length }}）
          </a-button>
          <a-button
            type="primary"
            :loading="formatDownloading"
            :disabled="transcriptResults.length === 0"
            @click="downloadFormat('transcript')"
          >
            <DownloadOutlined /> 听抄稿（{{ transcriptResults.length }}）
          </a-button>
          <a-button
            type="primary"
            :loading="formatDownloading"
            :disabled="compositeResults.length === 0"
            @click="downloadFormat('composite')"
          >
            <DownloadOutlined /> 复合（{{ compositeResults.length }}）
          </a-button>
        </div>
        <div v-for="(r, idx) in results" :key="idx" class="result-card">
          <a-card :title="r.type_label" size="small">
            <template #extra>
              <a-button type="link" size="small" @click="copyResult(r.content)">
                <CopyOutlined /> 复制
              </a-button>
            </template>
            <pre class="result-content">{{ r.content }}</pre>
          </a-card>
        </div>
      </div>
    </a-card>
  </div>
</template>

<style scoped>
.box {
  padding: 1em;
  max-width: 1000px;
  margin: 0 auto;
}

.hint {
  color: #666;
  margin-bottom: 0;
}

.type-selection {
  margin-bottom: 12px;
}

.label {
  font-weight: 600;
  margin-bottom: 4px;
}

.type-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.type-button {
  margin-bottom: 8px;
}

.results-section {
  margin-top: 20px;
}

.format-download-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
  padding: 12px;
  background: #fafafa;
  border-radius: 8px;
}

.format-download-label {
  font-weight: 500;
  margin-right: 4px;
}

.result-card {
  margin-bottom: 16px;
}

.result-content {
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.6;
  margin: 0;
  padding: 12px;
  background: #f5f5f5;
  border-radius: 4px;
  max-height: 400px;
  overflow-y: auto;
}
</style>

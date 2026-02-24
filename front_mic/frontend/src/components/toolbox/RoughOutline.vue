<script setup>
import ToolsHeader from "./ToolsHeader.vue";
import { ref, computed, onMounted } from "vue";
import { LoadingOutlined, CopyOutlined, DownloadOutlined } from "@ant-design/icons-vue";
import { toastSuccess, toastWarning } from "../utils/Dialog";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";

// 毛胚纲目类型（多选）
const selectedTypes = ref([]);
const outlineTypes = [
  { label: "润色版", value: "polish", desc: "使用 Claude Sonnet 4.5 生成2次 + Gemini 3.0 Pro 生成2次，共4篇" },
  { label: "初信版（精粹）", value: "beginner", desc: "使用 Claude Sonnet 4.5" },
  { label: "青少年版", value: "youth", desc: "使用 Claude Sonnet 4.5" },
  { label: "真理加强版", value: "truth", desc: "使用 Claude 4.5" },
  { label: "三分钟分享", value: "sharing", desc: "使用6种AI：Claude 4.5、Gemini 3.0 Pro、Deep Seek-V3.2、Perplexity–search、Chat GPT5.2、Grok 4.1" },
];

// 每种类型对应的 AI 数量（由后端配置返回）
const aiCounts = ref({ polish: 4, beginner: 1, youth: 1, truth: 1, sharing: 6 });
const content = ref("");
const loading = ref(false);
const results = ref([]);
const error = ref(null);
const progressCurrent = ref(0);
const progressTotal = ref(0);
const formatDownloading = ref(false);

// 当前结果按类型分组（用于刷格式并下载）
const polishResults = computed(() => results.value.filter(r => r.type === "polish"));
const beginnerResults = computed(() => results.value.filter(r => r.type === "beginner"));
const youthResults = computed(() => results.value.filter(r => r.type === "youth"));
const truthResults = computed(() => results.value.filter(r => r.type === "truth"));
const sharingResults = computed(() => results.value.filter(r => r.type === "sharing"));

onMounted(async () => {
  try {
    const token = localStorage.getItem("token");
    const res = await fetch(`${apiBase}/api/ai_search/rough_outline_config`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (res.ok) {
      const data = await res.json();
      if (data && typeof data === "object") aiCounts.value = data;
    }
  } catch (_) {}
});

// 切换类型选择
function toggleType(typeValue) {
  const index = selectedTypes.value.indexOf(typeValue);
  if (index > -1) {
    selectedTypes.value.splice(index, 1);
  } else {
    selectedTypes.value.push(typeValue);
  }
}

// 获取类型信息
function getTypeInfo(typeValue) {
  return outlineTypes.find(t => t.value === typeValue);
}

// 复制结果
function copyResult(resultText) {
  if (!resultText) return;
  navigator.clipboard.writeText(resultText).then(() => {
    toastSuccess("已复制到剪贴板");
  });
}

// 生成毛坯纲目：每个纲目单独调用一次 API
async function generateRoughOutline() {
  const text = (content.value || "").trim();
  if (!text) {
    error.value = "请先输入或粘贴原始纲目内容";
    results.value = [];
    return;
  }
  if (selectedTypes.value.length === 0) {
    toastWarning("请至少选择一种纲目类型");
    return;
  }

  const authToken = localStorage.getItem("token") || null;
  if (!authToken) {
    window.location.hash = "/login";
    return;
  }

  // 构建 (类型, ai_index) 列表，每个组合调用一次 API
  const tasks = [];
  for (const typeValue of selectedTypes.value) {
    const count = aiCounts.value[typeValue] ?? 1;
    for (let aiIndex = 0; aiIndex < count; aiIndex++) {
      tasks.push({ typeValue, aiIndex });
    }
  }

  loading.value = true;
  error.value = null;
  results.value = [];
  progressTotal.value = tasks.length;
  progressCurrent.value = 0;

  const allResults = [];
  const errors = [];

  // 并行请求：同时发起所有 API 调用，总耗时 ≈ 最慢一次（后端用 asyncio.to_thread 不阻塞）
  const runOne = async (task, index) => {
    const { typeValue, aiIndex } = task;
    const typeInfo = getTypeInfo(typeValue);
    try {
      const res = await fetch(`${apiBase}/api/ai_search/rough_outline`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({
          outline_type: typeValue,
          content: text,
          ai_index: aiIndex,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        return { index, error: `${typeInfo?.label || typeValue}#${aiIndex + 1}: ${data.detail || data.error || data.message || "生成失败"}` };
      }
      if (data.results && Array.isArray(data.results) && data.results.length > 0) {
        const typedResults = data.results.map((r) => ({ ...r, type_label: typeInfo?.label || typeValue }));
        return { index, results: typedResults };
      }
      return { index, error: `${typeInfo?.label || typeValue}#${aiIndex + 1}: ${data.error || "未返回结果"}` };
    } catch (err) {
      return { index, error: `${typeInfo?.label || typeValue}#${aiIndex + 1}: ${err.message || "网络错误"}` };
    } finally {
      progressCurrent.value += 1;
    }
  };

  const settled = await Promise.all(tasks.map((task, i) => runOne(task, i)));
  // 按原顺序合并结果与错误
  settled.sort((a, b) => a.index - b.index);
  for (const s of settled) {
    if (s.results) allResults.push(...s.results);
    if (s.error) errors.push(s.error);
  }

  loading.value = false;
  progressCurrent.value = 0;
  progressTotal.value = 0;

  if (allResults.length > 0) {
    results.value = allResults;
    toastSuccess(`成功生成 ${allResults.length} 篇毛胚纲目！`);
    if (errors.length > 0) toastWarning(`部分失败: ${errors.join("; ")}`);
  } else {
    error.value = errors.length > 0 ? errors.join("; ") : "未生成任何结果，请稍后重试";
  }
}

// 刷格式并下载：润色版 4 篇或三分钟分享 6 篇合并为一个 DOCX
async function downloadFormatRoughOutline(outlineType) {
  const typeToResults = {
    polish: polishResults.value,
    beginner: beginnerResults.value,
    youth: youthResults.value,
    truth: truthResults.value,
    sharing: sharingResults.value,
  };
  const list = typeToResults[outlineType] || [];
  const typeLabels = { polish: "润色版", beginner: "初信版", youth: "青少年版", truth: "真理加强版", sharing: "三分钟分享" };
  if (!list.length) {
    toastWarning(`暂无${typeLabels[outlineType] || outlineType}结果`);
    return;
  }
  const authToken = localStorage.getItem("token") || null;
  if (!authToken) {
    window.location.hash = "/login";
    return;
  }
  let contents;
  if (outlineType === "polish") {
    // 润色版：两篇 Claude 在前，两篇 Gemini 在后（按 ai_model 区分）
    const sorted = [...list].sort((a, b) => {
      const key = (name) => {
        const n = (name || "").toLowerCase();
        if (n.includes("claude")) return 0;
        if (n.includes("gemini")) return 1;
        return 2;
      };
      return key(a.ai_model) - key(b.ai_model);
    });
    contents = sorted.map(r => (r.content || "").trim()).filter(Boolean);
  } else if (outlineType === "sharing") {
    // 三分钟分享：每篇上一行加「三分钟分享（AI名字）」
    contents = list.map(r => "三分钟分享（" + (r.ai_model || "AI") + "）\n\n" + (r.content || "").trim());
  } else {
    contents = list.map(r => (r.content || "").trim()).filter(Boolean);
  }
  if (!contents.length) {
    toastWarning("所选结果内容为空");
    return;
  }
  formatDownloading.value = true;
  try {
    const res = await fetch(`${apiBase}/api/ai_search/rough_outline_format_and_download`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${authToken}`,
      },
      body: JSON.stringify({ outline_type: outlineType, contents }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      toastWarning(data.detail || data.error || "下载失败");
      return;
    }
    const b64 = data.docx_base64;
    const defaultNames = { polish: "毛胚纲目_润色版.docx", beginner: "毛胚纲目_初信版.docx", youth: "毛胚纲目_青少年版.docx", truth: "毛胚纲目_真理加强版.docx", sharing: "毛胚纲目_三分钟分享.docx" };
    const filename = data.filename || defaultNames[outlineType] || "毛胚纲目.docx";
    if (!b64) {
      toastWarning(data.error || "未返回文件");
      return;
    }
    const bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    const blob = new Blob([bin], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
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
</script>

<template>
  <ToolsHeader title="毛胚纲目" />
  <div class="box">
    <a-card>
      <p class="hint">
        选择毛胚纲目类型（可多选），输入原始纲目内容，系统将使用不同的AI模型生成多篇毛胚纲目供您选择。
      </p>
      <a-divider :style="{ margin: '12px 0' }" />
      
      <!-- 类型选择（多选按钮） -->
      <div class="type-selection">
        <span class="label">纲目类型：</span>
        <div class="type-buttons">
          <a-button
            v-for="type in outlineTypes"
            :key="type.value"
            :type="selectedTypes.includes(type.value) ? 'primary' : 'default'"
            @click="toggleType(type.value)"
            class="type-button"
          >
            {{ type.label }}
          </a-button>
        </div>
      </div>
      <div v-if="selectedTypes.length > 0" class="type-desc">
        <a-typography-text type="secondary">
          已选择：{{ selectedTypes.map(v => getTypeInfo(v)?.label || v).join("、") }}
        </a-typography-text>
      </div>
      
      <a-divider :style="{ margin: '12px 0' }" />
      
      <!-- 输入框 -->
      <a-textarea
        v-model:value="content"
        placeholder="请粘贴原始纲目全文…"
        :rows="8"
        :style="{ marginBottom: '12px' }"
      />
      
      <!-- 错误提示 -->
      <a-alert v-if="error" :message="error" type="error" :style="{ marginBottom: '12px' }" />
      
      <!-- 生成按钮 -->
      <a-button
        type="primary"
        :loading="loading"
        :disabled="!content.trim() || selectedTypes.length === 0"
        @click="generateRoughOutline"
        :style="{ width: '100%', marginBottom: '20px' }"
      >
        <template v-if="loading">
          <LoadingOutlined /> 生成中（{{ progressCurrent }}/{{ progressTotal }}）…
        </template>
        <template v-else>
          生成毛胚纲目
        </template>
      </a-button>
      
      <!-- 结果展示 -->
      <div v-if="results.length > 0" class="results-section">
        <a-divider>生成结果（共 {{ results.length }} 篇）</a-divider>
        <!-- 刷格式并下载：五类均可，各合并为一个 DOCX -->
        <div class="format-download-row">
          <span class="format-download-label">刷格式并下载：</span>
          <a-button
            type="primary"
            :loading="formatDownloading"
            :disabled="polishResults.length === 0"
            @click="downloadFormatRoughOutline('polish')"
          >
            <DownloadOutlined /> 润色版（{{ polishResults.length }} 篇）
          </a-button>
          <a-button
            type="primary"
            :loading="formatDownloading"
            :disabled="beginnerResults.length === 0"
            @click="downloadFormatRoughOutline('beginner')"
          >
            <DownloadOutlined /> 初信版（{{ beginnerResults.length }} 篇）
          </a-button>
          <a-button
            type="primary"
            :loading="formatDownloading"
            :disabled="youthResults.length === 0"
            @click="downloadFormatRoughOutline('youth')"
          >
            <DownloadOutlined /> 青少年版（{{ youthResults.length }} 篇）
          </a-button>
          <a-button
            type="primary"
            :loading="formatDownloading"
            :disabled="truthResults.length === 0"
            @click="downloadFormatRoughOutline('truth')"
          >
            <DownloadOutlined /> 真理加强版（{{ truthResults.length }} 篇）
          </a-button>
          <a-button
            type="primary"
            :loading="formatDownloading"
            :disabled="sharingResults.length === 0"
            @click="downloadFormatRoughOutline('sharing')"
          >
            <DownloadOutlined /> 三分钟分享（{{ sharingResults.length }} 篇）
          </a-button>
        </div>
        <div v-for="(result, index) in results" :key="index" class="result-card">
          <a-card 
            :title="`${result.type_label || result.type || '未知类型'} - ${result.ai_model || 'AI'}`" 
            size="small"
          >
            <template #extra>
              <a-button type="link" size="small" @click="copyResult(result.content)">
                <CopyOutlined /> 复制
              </a-button>
            </template>
            <pre class="result-content">{{ result.content }}</pre>
          </a-card>
        </div>
      </div>
    </a-card>
  </div>
</template>

<style scoped>
.box {
  padding: 1em;
  max-width: 1200px;
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
  font-weight: bold;
  margin-right: 12px;
  display: block;
  margin-bottom: 8px;
}

.type-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.type-button {
  margin-bottom: 8px;
}

.type-desc {
  margin-top: 8px;
  margin-bottom: 12px;
  color: #888;
  font-size: 12px;
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
  max-height: 500px;
  overflow-y: auto;
}
</style>

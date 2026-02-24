<script setup>
import ToolsHeader from "./ToolsHeader.vue";
import { ref } from "vue";
import { DownloadOutlined } from "@ant-design/icons-vue";
import { toastSuccess, toastWarning } from "../utils/Dialog";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";

// 当前选中的类型
const activeTab = ref("original");

// 1. 纲目的原文
const originalContent = ref("");
const originalLoading = ref(false);

// 2. 带经文的纲目
const scriptureContent = ref("");
const scriptureLoading = ref(false);

// 3. 晨兴信息选读的纲目
const morningRevivalContent = ref("");
const morningRevivalLoading = ref(false);

// 4. 听抄稿的纲目
const transcriptOutline = ref("");
const transcriptText = ref("");
const transcriptLoading = ref(false);

// 5. 复合的纲目
const compositeTranscriptOutline = ref("");
const compositeMorningRevivalOutline = ref("");
const compositeLoading = ref(false);

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

function downloadDocx(b64, filename) {
  if (!b64) return;
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
}

// 1. 纲目的原文：刷格式并下载
async function handleOriginal() {
  const content = (originalContent.value || "").trim();
  if (!content) {
    toastWarning("请先粘贴纲目原文");
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;
  originalLoading.value = true;
  try {
    const res = await fetch(`${apiBase}/api/ai_search/feast_outline/original`, {
      method: "POST",
      headers,
      body: JSON.stringify({ content }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      toastWarning(data.detail || data.error || "下载失败");
      return;
    }
    if (data.docx_base64) {
      downloadDocx(data.docx_base64, data.filename || "节期纲目.docx");
    } else {
      toastWarning(data.error || "未返回文件");
    }
  } catch (err) {
    toastWarning(err.message || "下载失败");
  } finally {
    originalLoading.value = false;
  }
}

// 2. 带经文的纲目：经文汇集后刷格式并下载
async function handleWithScripture() {
  const content = (scriptureContent.value || "").trim();
  if (!content) {
    toastWarning("请先粘贴纲目内容");
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;
  scriptureLoading.value = true;
  try {
    const res = await fetch(`${apiBase}/api/ai_search/feast_outline/with_scripture`, {
      method: "POST",
      headers,
      body: JSON.stringify({ content }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      toastWarning(data.detail || data.error || "下载失败");
      return;
    }
    if (data.docx_base64) {
      downloadDocx(data.docx_base64, data.filename || "节期纲目_带经文.docx");
    } else {
      toastWarning(data.error || "未返回文件");
    }
  } catch (err) {
    toastWarning(err.message || "下载失败");
  } finally {
    scriptureLoading.value = false;
  }
}

// 3. 晨兴信息选读的纲目：Claude 生成后刷格式并下载
async function handleMorningRevival() {
  const content = (morningRevivalContent.value || "").trim();
  if (!content) {
    toastWarning("请先粘贴晨兴信息选读内容");
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;
  morningRevivalLoading.value = true;
  try {
    const res = await fetch(`${apiBase}/api/ai_search/feast_outline/morning_revival`, {
      method: "POST",
      headers,
      body: JSON.stringify({ content }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      toastWarning(data.detail || data.error || "生成或下载失败");
      return;
    }
    if (data.docx_base64) {
      downloadDocx(data.docx_base64, data.filename || "节期纲目_晨兴信息选读.docx");
    } else {
      toastWarning(data.error || "未返回文件");
    }
  } catch (err) {
    toastWarning(err.message || "生成或下载失败");
  } finally {
    morningRevivalLoading.value = false;
  }
}

// 4. 听抄稿的纲目：原纲目+听抄稿重点后刷格式并下载
async function handleTranscript() {
  const outline = (transcriptOutline.value || "").trim();
  const transcript = (transcriptText.value || "").trim();
  if (!outline) {
    toastWarning("请先粘贴原纲目");
    return;
  }
  if (!transcript) {
    toastWarning("请先粘贴听抄稿内容");
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;
  transcriptLoading.value = true;
  try {
    const res = await fetch(`${apiBase}/api/ai_search/feast_outline/transcript`, {
      method: "POST",
      headers,
      body: JSON.stringify({ original_outline: outline, transcript }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      toastWarning(data.detail || data.error || "生成或下载失败");
      return;
    }
    if (data.docx_base64) {
      downloadDocx(data.docx_base64, data.filename || "节期纲目_听抄稿.docx");
    } else {
      toastWarning(data.error || "未返回文件");
    }
  } catch (err) {
    toastWarning(err.message || "生成或下载失败");
  } finally {
    transcriptLoading.value = false;
  }
}

// 5. 复合的纲目：晨兴融入听抄稿纲目后刷格式并下载
async function handleComposite() {
  const transcriptOutlineText = (compositeTranscriptOutline.value || "").trim();
  const morningRevivalOutlineText = (compositeMorningRevivalOutline.value || "").trim();
  if (!transcriptOutlineText) {
    toastWarning("请先粘贴听抄稿的纲目");
    return;
  }
  if (!morningRevivalOutlineText) {
    toastWarning("请先粘贴晨兴信息选读的纲目");
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;
  compositeLoading.value = true;
  try {
    const res = await fetch(`${apiBase}/api/ai_search/feast_outline/composite`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        transcript_outline: transcriptOutlineText,
        morning_revival_outline: morningRevivalOutlineText,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      toastWarning(data.detail || data.error || "生成或下载失败");
      return;
    }
    if (data.docx_base64) {
      downloadDocx(data.docx_base64, data.filename || "节期纲目_复合.docx");
    } else {
      toastWarning(data.error || "未返回文件");
    }
  } catch (err) {
    toastWarning(err.message || "生成或下载失败");
  } finally {
    compositeLoading.value = false;
  }
}
</script>

<template>
  <ToolsHeader title="节期纲目" />
  <div class="box">
    <a-card>
      <p class="hint">
        节期纲目提供五类功能：纲目的原文（刷格式）、带经文的纲目（经文汇集+刷格式）、晨兴信息选读的纲目（AI 生成+刷格式）、听抄稿的纲目（原纲目+听抄稿重点+刷格式）、复合的纲目（听抄稿纲目+晨兴纲目融合+刷格式）。选择下方标签页操作并下载 DOCX。
      </p>
      <a-divider :style="{ margin: '12px 0' }" />
      <a-tabs v-model:activeKey="activeTab">
        <a-tab-pane key="original" tab="纲目的原文">
          <p class="tab-desc">粘贴没有格式的纲目，刷为正确格式并下载。</p>
          <a-textarea
            v-model:value="originalContent"
            placeholder="请粘贴纲目原文（无格式）…"
            :rows="10"
            :style="{ marginBottom: '12px' }"
          />
          <a-button
            type="primary"
            :loading="originalLoading"
            :disabled="!originalContent.trim()"
            @click="handleOriginal"
          >
            <DownloadOutlined /> 刷格式并下载
          </a-button>
        </a-tab-pane>
        <a-tab-pane key="scripture" tab="带经文的纲目">
          <p class="tab-desc">粘贴纲目内容，使用经文汇集功能汇集经文后，刷格式并下载。</p>
          <a-textarea
            v-model:value="scriptureContent"
            placeholder="请粘贴纲目内容（将自动经文汇集）…"
            :rows="10"
            :style="{ marginBottom: '12px' }"
          />
          <a-button
            type="primary"
            :loading="scriptureLoading"
            :disabled="!scriptureContent.trim()"
            @click="handleWithScripture"
          >
            <DownloadOutlined /> 汇集经文并刷格式下载
          </a-button>
        </a-tab-pane>
        <a-tab-pane key="morning_revival" tab="晨兴信息选读的纲目">
          <p class="tab-desc">粘贴晨兴信息选读内容，使用 Claude 生成纲目后刷格式并下载。</p>
          <a-textarea
            v-model:value="morningRevivalContent"
            placeholder="请粘贴晨兴信息选读内容…"
            :rows="10"
            :style="{ marginBottom: '12px' }"
          />
          <a-button
            type="primary"
            :loading="morningRevivalLoading"
            :disabled="!morningRevivalContent.trim()"
            @click="handleMorningRevival"
          >
            生成纲目并刷格式下载
          </a-button>
        </a-tab-pane>
        <a-tab-pane key="transcript" tab="听抄稿的纲目">
          <p class="tab-desc">粘贴原纲目和听抄稿内容，Claude 在原纲目基础上加入听抄稿重点，再刷格式并下载。</p>
          <div :style="{ marginBottom: '12px' }">
            <div class="label">原纲目</div>
            <a-textarea
              v-model:value="transcriptOutline"
              placeholder="请粘贴原纲目…"
              :rows="6"
              :style="{ marginBottom: '8px' }"
            />
            <div class="label">听抄稿内容</div>
            <a-textarea
              v-model:value="transcriptText"
              placeholder="请粘贴听抄稿内容…"
              :rows="6"
            />
          </div>
          <a-button
            type="primary"
            :loading="transcriptLoading"
            :disabled="!transcriptOutline.trim() || !transcriptText.trim()"
            @click="handleTranscript"
          >
            生成并刷格式下载
          </a-button>
        </a-tab-pane>
        <a-tab-pane key="composite" tab="复合的纲目">
          <p class="tab-desc">以听抄稿的纲目为基础，将晨兴信息选读的纲目内容融入，Claude 生成复合纲目后刷格式并下载。</p>
          <div :style="{ marginBottom: '12px' }">
            <div class="label">听抄稿的纲目</div>
            <a-textarea
              v-model:value="compositeTranscriptOutline"
              placeholder="请粘贴听抄稿的纲目…"
              :rows="6"
              :style="{ marginBottom: '8px' }"
            />
            <div class="label">晨兴信息选读的纲目</div>
            <a-textarea
              v-model:value="compositeMorningRevivalOutline"
              placeholder="请粘贴晨兴信息选读的纲目…"
              :rows="6"
            />
          </div>
          <a-button
            type="primary"
            :loading="compositeLoading"
            :disabled="!compositeTranscriptOutline.trim() || !compositeMorningRevivalOutline.trim()"
            @click="handleComposite"
          >
            生成复合纲目并刷格式下载
          </a-button>
        </a-tab-pane>
      </a-tabs>
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

.tab-desc {
  color: #555;
  margin-bottom: 12px;
  font-size: 14px;
}

.label {
  font-weight: 600;
  margin-bottom: 4px;
}
</style>

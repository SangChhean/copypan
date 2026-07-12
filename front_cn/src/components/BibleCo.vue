<template>
  <ToolsHeader title="纲目附经文" />
  <div class="cn-content-wrap">
    <div class="cn-content-card">
    <template v-if="false">
    <div class="direction-row">
      <span class="dir-label">语言：</span>
      <div class="cn-dir-toggle">
        <button
          type="button"
          class="cn-dir-btn"
          :class="{ active: lang === 'zh' }"
          @click="lang = 'zh'"
        >中文</button>
        <button
          type="button"
          class="cn-dir-btn"
          :class="{ active: lang === 'en' }"
          @click="lang = 'en'"
        >English</button>
      </div>
    </div>
    <a-divider :style="{ margin: '12px 0' }" />
    </template>
    <a-textarea
      v-model:value="input"
      placeholder="请输入内容"
      :rows="8"
      class="bibco-input"
    />
    <a-divider :style="{ margin: '12px 0' }" />
    <div class="action-row">
      <a-button class="cn-btn-ghost clear-btn" @click="input = ''">清空</a-button>
      <a-button type="primary" @click="search">汇集</a-button>
      <a-button
        v-if="hasResults && lang === 'en'"
        type="primary"
        :loading="formatDownloading"
        @click="downloadFormat"
      >刷格式下载</a-button>
      <a-button
        v-if="hasResults && lang === 'zh'"
        type="primary"
        :loading="formatDownloadingZh"
        @click="downloadFormatZh"
      >刷格式下载</a-button>
    </div>
    <a-divider :style="{ margin: '12px 0' }" />
    <div class="cn-result bibco-result">
      <div v-for="item in showData" :key="item.text">
        <div v-text="item.text" class="outline" v-if="item.text.trim()"></div>
        <div v-for="ver in item.vers" :key="ver.source + ver.text">
          <span class="ver_s">{{ ver.source }}　</span>
          <span class="ver_t">{{ ver.text }}</span>
        </div>
      </div>
    </div>
    </div>
  </div>
</template>

<script setup>
import ToolsHeader from "@/components/ToolsHeader.vue";
import { ref, computed } from "vue";
import http from "@/utils/http.js";
import { getToken } from "@/utils/auth.js";

const input = ref("");
const showData = ref([]);
const lang = ref("zh");
const formatDownloading = ref(false);
const formatDownloadingZh = ref(false);

const hasResults = computed(() => showData.value.length > 0);

function buildFormatContents() {
  const lines = [];
  for (const item of showData.value) {
    const lineText = (item.text || "")
      .replace(/\r\n/g, " ")
      .replace(/\r/g, " ")
      .replace(/\n/g, " ")
      .trim();
    if (lineText) lines.push(lineText);
    if (item.vers) {
      for (const ver of item.vers) {
        const src = (ver.source || "").trim();
        const txt = (ver.text || "").trim();
        if (!src && !txt) continue;
        lines.push(`${src}\t${txt}`);
      }
    }
  }
  return lines.join("\n");
}

function buildFormatContentsZh() {
  const lines = [];
  for (const item of showData.value) {
    const lineText = (item.text || "")
      .replace(/\r\n/g, " ")
      .replace(/\r/g, " ")
      .replace(/\n/g, " ")
      .trim();
    if (lineText) lines.push(lineText);
    if (item.vers) {
      for (const ver of item.vers) {
        const src = (ver.source || "").trim();
        const txt = (ver.text || "").trim();
        if (!src && !txt) continue;
        lines.push(`　${src}　${txt}`);
      }
    }
  }
  return lines.join("\n");
}

async function triggerDocxDownload(url, formData, defaultFilename) {
  if (!getToken()) {
    window.location.hash = "/login";
    return;
  }

  const res = await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${getToken()}` },
    body: formData,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(data.error || data.detail || "下载失败");
    return;
  }
  const b64 = data.docx_base64;
  const filename = data.filename || defaultFilename;
  if (!b64) {
    alert(data.error || "未返回文件");
    return;
  }
  const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const blob = new Blob([bin], {
    type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  });
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(blobUrl);
}

const search = () => {
  if (!input.value.trim()) {
    showData.value = [];
    return;
  }
  if (!getToken()) {
    window.location.hash = "/login";
    return;
  }
  const formData = new FormData();
  formData.append("input", input.value);
  formData.append("lang", lang.value);
  http.post("/api/getvers", formData).then((res) => {
    showData.value = res.data;
  });
};

async function downloadFormat() {
  const contents = buildFormatContents();
  if (!contents.trim()) return;

  formatDownloading.value = true;
  try {
    const formData = new FormData();
    formData.append("contents", contents);
    formData.append("filename", "英文纲目附经文");
    await triggerDocxDownload("/api/getvers/format_download", formData, "英文纲目附经文.docx");
  } finally {
    formatDownloading.value = false;
  }
}

async function downloadFormatZh() {
  const contents = buildFormatContentsZh();
  if (!contents.trim()) return;

  formatDownloadingZh.value = true;
  try {
    const formData = new FormData();
    formData.append("contents", contents);
    formData.append("filename", "中文纲目附经文");
    await triggerDocxDownload("/api/getvers/format_download_zh", formData, "中文纲目附经文.docx");
  } finally {
    formatDownloadingZh.value = false;
  }
}
</script>

<style scoped>
.direction-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.dir-label {
  font-size: 14px;
  color: var(--cn-text-primary);
}

.bibco-input {
  width: 100%;
}

.bibco-input :deep(textarea.ant-input) {
  min-height: 160px;
  width: 100%;
}

.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.clear-btn {
  border: 0.5px solid var(--cn-border) !important;
  color: var(--cn-text-secondary) !important;
  background: transparent !important;
}

.clear-btn:hover:not(:disabled) {
  border-color: var(--cn-gold) !important;
  color: var(--cn-gold) !important;
}

.bibco-result {
  width: 100%;
  min-height: 320px;
  margin-top: 8px;
}

.outline {
  padding: 0.5em 0;
  margin: 0.5em 0;
  font-weight: 500;
  color: var(--cn-text-primary);
}

.ver_s {
  font-weight: 500;
  color: var(--cn-gold);
}

:deep(.ant-radio-button-wrapper) {
  background: #ffffff !important;
  border-color: #CCE4F5 !important;
  color: #4A6A84 !important;
}
:deep(.ant-radio-button-wrapper-checked) {
  background: #EBF4FB !important;
  border-color: #1B6CA8 !important;
  color: #1B6CA8 !important;
}
:deep(.ant-radio-button-wrapper:hover) {
  color: #1B6CA8 !important;
}
:deep(.ant-radio-button-wrapper-checked::before),
:deep(.ant-radio-button-wrapper-checked:not(.ant-radio-button-wrapper-disabled)::before) {
  background: #CCE4F5 !important;
}
</style>

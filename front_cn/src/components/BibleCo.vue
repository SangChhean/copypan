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
    formData.append("filename", "英文经文汇集");
    await triggerDocxDownload("/api/getvers/format_download", formData, "英文经文汇集.docx");
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
    formData.append("filename", "中文经文汇集");
    await triggerDocxDownload("/api/getvers/format_download_zh", formData, "中文经文汇集.docx");
  } finally {
    formatDownloadingZh.value = false;
  }
}
</script>

<template>
  <ToolsHeader title="经文汇集" />
  <div class="cn-page-body bibco-body">
    <a-space class="lang-switch">
      <a-button
        :type="lang === 'zh' ? 'primary' : 'default'"
        :class="{ 'cn-btn-ghost': lang !== 'zh' }"
        @click="lang = 'zh'"
      >中文</a-button>
      <a-button
        :type="lang === 'en' ? 'primary' : 'default'"
        :class="{ 'cn-btn-ghost': lang !== 'en' }"
        @click="lang = 'en'"
      >English</a-button>
    </a-space>
    <a-divider :style="{ margin: '12px 0' }" />
    <a-textarea v-model:value="input" placeholder="请输入内容" :rows="12" />
    <a-divider :style="{ margin: '12px 0' }" />
    <a-space>
      <a-button danger @click="input = ''">清空</a-button>
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
    </a-space>
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
</template>

<style scoped>
.bibco-body {
  padding-top: 20px;
}

.bibco-result {
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
</style>

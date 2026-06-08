<script setup>
import { ref, reactive, computed } from "vue";
import { useRouter } from "vue-router";
import { LeftOutlined, DownloadOutlined, CopyOutlined } from "@ant-design/icons-vue";

const router = useRouter();
const keyword = ref("");
const ministryContent = ref("");
const feastContent = ref("");
const toast = ref("");

const results = reactive({
  ministry: {
    skeletonLoading: false,
    outlineLoading: false,
    sourceLoading: false,
    skeleton_json: [],
    skeleton_text: "",
    outline: "",
    outline_with_source: "",
    error: "",
  },
  feast: {
    skeletonLoading: false,
    outlineLoading: false,
    sourceLoading: false,
    skeleton_json: [],
    skeleton_text: "",
    outline: "",
    outline_with_source: "",
    error: "",
  },
});

const canGenerate = computed(() =>
  keyword.value.trim() &&
  (ministryContent.value.trim() || feastContent.value.trim())
);

const isGenerating = computed(() =>
  results.ministry.skeletonLoading ||
  results.ministry.outlineLoading ||
  results.feast.skeletonLoading ||
  results.feast.outlineLoading
);

function showToast(msg) {
  toast.value = msg;
  setTimeout(() => { if (toast.value === msg) toast.value = ""; }, 2500);
}

function copyText(text) {
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => showToast("已复制到剪贴板"));
}

async function generateOne(birdType, content) {
  const r = results[birdType];
  r.error = "";
  r.skeleton_json = [];
  r.skeleton_text = "";
  r.outline = "";
  r.outline_with_source = "";

  // Step A：骨架
  r.skeletonLoading = true;
  try {
    const res = await fetch("/api/testa/bird_view/skeleton", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        keyword: keyword.value.trim(),
        type: birdType,
        content,
      }),
    });
    if (!res.ok) throw new Error("骨架生成失败");
    const data = await res.json();
    r.skeleton_json = data.skeleton_json || [];
    r.skeleton_text = data.skeleton_text || "";
  } catch (e) {
    r.error = e.message || "骨架生成失败，请重试";
    return;
  } finally {
    r.skeletonLoading = false;
  }

  // Step B：纲目（串行，用上一步的 skeleton_text）
  r.outlineLoading = true;
  try {
    const res = await fetch("/api/testa/bird_view/outline", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        keyword: keyword.value.trim(),
        type: birdType,
        content,
        skeleton: r.skeleton_text,
      }),
    });
    if (!res.ok) throw new Error("纲目生成失败");
    const data = await res.json();
    console.log('[outline before]', birdType, 'outlineLoading:', r.outlineLoading, 'outline:', r.outline);
    r.outline = data.outline || "";
    console.log('[outline after]', birdType, 'outlineLoading:', r.outlineLoading, 'outline length:', r.outline.length);
  } catch (e) {
    r.error = e.message || "纲目生成失败，请重试";
  } finally {
    r.outlineLoading = false;
  }
}

async function generateAll() {
  if (!canGenerate.value) return;
  const tasks = [];
  if (ministryContent.value.trim())
    tasks.push(generateOne("ministry", ministryContent.value));
  if (feastContent.value.trim())
    tasks.push(generateOne("feast", feastContent.value));
  await Promise.allSettled(tasks);
  showToast("生成完成！");
}

async function generateSource(birdType) {
  const r = results[birdType];
  if (!r.outline) return;
  const content = birdType === "ministry" ? ministryContent.value : feastContent.value;
  r.sourceLoading = true;
  try {
    const res = await fetch("/api/testa/bird_view/source", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        keyword: keyword.value.trim(),
        type: birdType,
        content,
        outline: r.outline,
      }),
    });
    if (!res.ok) throw new Error("加出处失败");
    const data = await res.json();
    r.outline_with_source = data.outline_with_source || "";
    showToast("加出处完成！");
  } catch (e) {
    r.error = "加出处失败，请重试";
  } finally {
    r.sourceLoading = false;
  }
}

const formatLoading = reactive({ ministry: false, feast: false });

async function formatAndDownload(birdType) {
  const r = results[birdType];
  const text = r.outline_with_source || r.outline;
  if (!text) return;
  formatLoading[birdType] = true;
  try {
    const res = await fetch("/api/testa/translate/format_download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, lang: "zh" }),
    });
    if (!res.ok) { showToast("下载失败"); return; }
    let filename = `${keyword.value || "鸟瞰纲目"}.docx`;
    const disposition = res.headers.get("Content-Disposition");
    if (disposition) {
      const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
      if (utf8Match) filename = decodeURIComponent(utf8Match[1]);
      else {
        const asciiMatch = disposition.match(/filename="([^"]+)"/i);
        if (asciiMatch) filename = asciiMatch[1];
      }
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    showToast("下载失败");
  } finally {
    formatLoading[birdType] = false;
  }
}
</script>

<template>
  <div class="page">
    <div v-if="toast" class="toast">{{ toast }}</div>

    <div class="header">
      <a-button type="text" class="back-btn" @click="router.back()">
        <template #icon><LeftOutlined /></template>
      </a-button>
      <span class="header-title">词典-鸟瞰纲目（testA）</span>
    </div>

    <!-- 输入卡片 -->
    <div class="card">
      <div class="field" style="margin-bottom: 14px;">
        <label class="field-label">纲目重点 <span class="required">*</span></label>
        <a-input
          v-model:value="keyword"
          placeholder="请输入关键词，如：光"
          :disabled="isGenerating"
        />
      </div>

      <div class="input-grid">
        <div class="field">
          <label class="field-label">
            职事信息 <span class="optional">（可选）</span>
          </label>
          <a-textarea
            v-model:value="ministryContent"
            placeholder="粘贴职事信息原文…"
            :disabled="isGenerating"
            :auto-size="{ minRows: 4, maxRows: 8 }"
          />
        </div>
        <div class="field">
          <label class="field-label">
            节期纲目 <span class="optional">（可选）</span>
          </label>
          <a-textarea
            v-model:value="feastContent"
            placeholder="粘贴节期纲目原文…"
            :disabled="isGenerating"
            :auto-size="{ minRows: 4, maxRows: 8 }"
          />
        </div>
      </div>

      <div class="divider" />

      <div class="action-row">
        <a-button
          class="generate-btn"
          :disabled="!canGenerate || isGenerating"
          :loading="isGenerating"
          @click="generateAll"
        >
          {{ isGenerating ? "生成中…" : "并发生成" }}
        </a-button>
      </div>
    </div>

    <!-- 结果区 -->
    <div class="results-grid">

      <!-- 职事信息列（始终占位） -->
      <div class="result-col">
        <template v-if="results.ministry.skeletonLoading || results.ministry.skeleton_json.length || results.ministry.outline || results.ministry.outlineLoading">
        <!-- 骨架 -->
        <div class="result-card" v-if="results.ministry.skeletonLoading || results.ministry.skeleton_json.length">
          <div class="result-card-title">
            <span class="badge badge-ministry">职事信息</span>骨架
          </div>
          <div v-if="results.ministry.skeletonLoading" class="loading-text">
            <a-spin size="small" /> 骨架生成中…
          </div>
          <ul v-else class="skeleton-list">
            <li
              v-for="(item, idx) in results.ministry.skeleton_json"
              :key="idx"
              class="skeleton-item"
            >
              <span class="step-num">{{ idx + 1 }}.</span>
              <span>{{ item.step }}</span>
            </li>
          </ul>
        </div>

        <!-- 纲目 -->
        <div class="result-card" v-if="results.ministry.outlineLoading || results.ministry.outline">
          <div class="result-card-title">
            <span class="badge badge-ministry">职事信息</span>纲目
          </div>
          <div v-if="results.ministry.outlineLoading" class="loading-text">
            <a-spin size="small" /> 纲目生成中…
          </div>
          <pre v-else class="outline-pre">{{ results.ministry.outline }}</pre>
          <div v-if="results.ministry.outline" class="btn-row">
            <button class="copy-btn" @click="copyText(results.ministry.outline)">
              <i class="ti ti-copy" aria-hidden="true"></i> 复制
            </button>
            <a-button
              class="source-btn"
              :loading="results.ministry.sourceLoading"
              @click="generateSource('ministry')"
            >
              加出处
            </a-button>
          </div>
        </div>

        <!-- 带出处版 -->
        <div class="result-card" v-if="results.ministry.outline_with_source">
          <div class="result-card-title">
            <span class="badge badge-ministry">职事信息</span>带出处版
          </div>
          <pre class="outline-pre">{{ results.ministry.outline_with_source }}</pre>
          <div class="btn-row">
            <button class="copy-btn" @click="copyText(results.ministry.outline_with_source)">
              <i class="ti ti-copy" aria-hidden="true"></i> 复制
            </button>
          </div>
          <div class="format-bar">
            <a-button
              class="format-btn"
              :loading="formatLoading.ministry"
              @click="formatAndDownload('ministry')"
            >
              <template #icon><DownloadOutlined /></template>
              刷格式并下载
            </a-button>
          </div>
        </div>

        <!-- 无带出处版时的下载按钮 -->
        <div class="format-bar mx" v-if="results.ministry.outline && !results.ministry.outline_with_source">
          <a-button
            class="format-btn"
            :loading="formatLoading.ministry"
            @click="formatAndDownload('ministry')"
          >
            <template #icon><DownloadOutlined /></template>
            刷格式并下载
          </a-button>
        </div>

        <div v-if="results.ministry.error" class="error-msg">{{ results.ministry.error }}</div>
        </template>
        <div v-else-if="feastContent.trim() && !results.ministry.skeletonLoading && !results.ministry.skeleton_json.length" class="empty-col">
          <span style="font-size: 13px; color: #8c8c8c;">职事信息未输入</span>
        </div>
      </div>

      <!-- 节期纲目列（始终占位） -->
      <div class="result-col">
        <template v-if="results.feast.skeletonLoading || results.feast.skeleton_json.length || results.feast.outline || results.feast.outlineLoading">
        <!-- 骨架 -->
        <div class="result-card" v-if="results.feast.skeletonLoading || results.feast.skeleton_json.length">
          <div class="result-card-title">
            <span class="badge badge-feast">节期纲目</span>骨架
          </div>
          <div v-if="results.feast.skeletonLoading" class="loading-text">
            <a-spin size="small" /> 骨架生成中…
          </div>
          <ul v-else class="skeleton-list">
            <li
              v-for="(item, idx) in results.feast.skeleton_json"
              :key="idx"
              class="skeleton-item"
            >
              <span class="step-num">{{ idx + 1 }}.</span>
              <span>{{ item.step }}</span>
            </li>
          </ul>
        </div>

        <!-- 纲目 -->
        <div class="result-card" v-if="results.feast.outlineLoading || results.feast.outline">
          <div class="result-card-title">
            <span class="badge badge-feast">节期纲目</span>纲目
          </div>
          <div v-if="results.feast.outlineLoading" class="loading-text">
            <a-spin size="small" /> 纲目生成中…
          </div>
          <pre v-else class="outline-pre">{{ results.feast.outline }}</pre>
          <div v-if="results.feast.outline" class="btn-row">
            <button class="copy-btn" @click="copyText(results.feast.outline)">
              <i class="ti ti-copy" aria-hidden="true"></i> 复制
            </button>
            <a-button
              class="source-btn"
              :loading="results.feast.sourceLoading"
              @click="generateSource('feast')"
            >
              加出处
            </a-button>
          </div>
        </div>

        <!-- 带出处版 -->
        <div class="result-card" v-if="results.feast.outline_with_source">
          <div class="result-card-title">
            <span class="badge badge-feast">节期纲目</span>带出处版
          </div>
          <pre class="outline-pre">{{ results.feast.outline_with_source }}</pre>
          <div class="btn-row">
            <button class="copy-btn" @click="copyText(results.feast.outline_with_source)">
              <i class="ti ti-copy" aria-hidden="true"></i> 复制
            </button>
          </div>
          <div class="format-bar">
            <a-button
              class="format-btn"
              :loading="formatLoading.feast"
              @click="formatAndDownload('feast')"
            >
              <template #icon><DownloadOutlined /></template>
              刷格式并下载
            </a-button>
          </div>
        </div>

        <!-- 无带出处版时的下载按钮 -->
        <div class="format-bar mx" v-if="results.feast.outline && !results.feast.outline_with_source">
          <a-button
            class="format-btn"
            :loading="formatLoading.feast"
            @click="formatAndDownload('feast')"
          >
            <template #icon><DownloadOutlined /></template>
            刷格式并下载
          </a-button>
        </div>

        <div v-if="results.feast.error" class="error-msg">{{ results.feast.error }}</div>
        </template>
        <div v-else-if="ministryContent.trim() && !results.feast.skeletonLoading && !results.feast.skeleton_json.length" class="empty-col">
          <span style="font-size: 13px; color: #8c8c8c;">节期纲目未输入</span>
        </div>
      </div>

      <!-- 两列都未输入时的提示 -->
      <div
        v-if="!ministryContent.trim() && !feastContent.trim()"
        class="empty-hint"
        style="grid-column: 1 / -1;"
      >
        请在上方输入职事信息或节期纲目原文后点「并发生成」
      </div>

    </div>
  </div>
</template>

<style scoped>
.toast {
  position: fixed;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: #52c41a;
  color: #fff;
  padding: 8px 24px;
  border-radius: 20px;
  font-size: 14px;
  z-index: 9999;
  pointer-events: none;
}
.page {
  min-height: 100vh;
  background: #f5f5f5;
  padding-bottom: 40px;
}
.header {
  background: #001529;
  padding: 0 20px;
  height: 52px;
  display: flex;
  align-items: center;
  position: relative;
}
.back-btn { color: #55bbff; font-size: 18px; position: absolute; left: 12px; }
.header-title { color: #fff; font-size: 16px; font-weight: 500; flex: 1; text-align: center; }
.card { background: #fff; border-radius: 8px; padding: 16px 20px; margin: 12px 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.field-label { display: block; font-size: 13px; font-weight: 500; color: #333; margin-bottom: 6px; }
.required { color: #ff4d4f; }
.optional { font-weight: 400; color: #8c8c8c; font-size: 12px; }
.input-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 14px; }
.field { display: flex; flex-direction: column; }
.divider { height: 1px; background: #f0f0f0; margin: 12px 0; }
.action-row { display: flex; justify-content: center; }
.generate-btn {
  background: #1890ff;
  border-color: #1890ff;
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 1px;
  padding: 0 48px;
  height: 36px;
}
.generate-btn:hover { background: #40a9ff; border-color: #40a9ff; }
.results-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; margin: 0 16px; }
.result-col { display: flex; flex-direction: column; gap: 10px; }
.result-card { background: #fff; border-radius: 8px; border: 0.5px solid #e8e8e8; padding: 14px 16px; }
.result-card-title { font-size: 13px; font-weight: 500; color: #333; margin-bottom: 10px; display: flex; align-items: center; gap: 6px; }
.badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; }
.badge-ministry { background: #e6f7ff; color: #1890ff; border: 0.5px solid #91d5ff; }
.badge-feast { background: #f6ffed; color: #52c41a; border: 0.5px solid #b7eb8f; }
.skeleton-list { list-style: none; padding: 0; }
.skeleton-item { font-size: 12px; color: #595959; padding: 4px 0; border-bottom: 0.5px solid #f0f0f0; display: flex; gap: 8px; line-height: 1.6; }
.skeleton-item:last-child { border-bottom: none; }
.step-num { font-size: 11px; font-weight: 500; color: #1890ff; min-width: 18px; }
.outline-pre { font-size: 13px; color: #333; line-height: 1.9; white-space: pre-wrap; word-break: break-word; margin: 0; font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif; }
.btn-row { display: flex; justify-content: space-between; margin-top: 10px; }
.copy-btn { background: #fff; border: 1px solid #d9d9d9; color: #555; padding: 3px 14px; border-radius: 6px; cursor: pointer; font-size: 12px; }
.copy-btn:hover { color: #1890ff; border-color: #1890ff; }
.source-btn { border-color: #1890ff; color: #1890ff; font-size: 12px; }
.loading-text { font-size: 12px; color: #8c8c8c; padding: 8px 0; display: flex; align-items: center; gap: 6px; }
.format-bar { margin-top: 10px; }
.mx { margin: 0 16px 10px; }
.format-btn {
  width: 100%;
  height: 34px;
  background: #1890ff;
  border-color: #1890ff;
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  border-radius: 6px;
}
.format-btn:hover { background: #40a9ff; border-color: #40a9ff; }
.error-msg { margin: 4px 0; color: #cf1322; font-size: 13px; padding: 8px 12px; background: #fff2f0; border-radius: 6px; border: 1px solid #ffccc7; }
.empty-hint { text-align: center; color: #8c8c8c; font-size: 13px; padding: 32px 0; }
.empty-col {
  border: 0.5px dashed #d9d9d9;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 80px;
}
</style>

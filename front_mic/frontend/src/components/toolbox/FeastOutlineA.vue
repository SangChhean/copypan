<script setup>
import { ref, reactive, computed } from "vue";
import { useRouter } from "vue-router";
import { LeftOutlined, DownloadOutlined } from "@ant-design/icons-vue";

const router = useRouter();
const toast = ref("");

const inputLine1 = ref("");
const inputLine2 = ref("");
const inputLine3 = ref("");
const inputMorningRevival = ref("");
const inputOutline = ref("");
const inputTranscript = ref("");
const inputPreface = ref("");
const inputAddendum = ref("");

const results = reactive({
  morning_revival: { content: "", loading: false, error: "" },
  transcript:      { content: "", loading: false, error: "" },
  composite:       { content: "", loading: false, error: "" },
});

const isGenerating = computed(() =>
  results.morning_revival.loading ||
  results.transcript.loading ||
  results.composite.loading
);

const canGenerate = computed(() =>
  inputMorningRevival.value.trim() &&
  inputOutline.value.trim() &&
  inputTranscript.value.trim() &&
  !isGenerating.value
);

function showToast(msg) {
  toast.value = msg;
  setTimeout(() => { if (toast.value === msg) toast.value = ""; }, 2500);
}

function copyText(text) {
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => showToast("已复制到剪贴板"));
}

function clearAll() {
  inputLine1.value = "";
  inputLine2.value = "";
  inputLine3.value = "";
  inputMorningRevival.value = "";
  inputOutline.value = "";
  inputTranscript.value = "";
  inputPreface.value = "";
  inputAddendum.value = "";
  results.morning_revival.content = "";
  results.transcript.content = "";
  results.composite.content = "";
  results.morning_revival.error = "";
  results.transcript.error = "";
  results.composite.error = "";
}

// 找读经行位置，把序言插入读经行之后
function insertAfterScripture(outline, prefaceText) {
  if (!prefaceText) return outline;
  const lines = outline.split("\n");
  const scriptureIdx = lines.findIndex(l =>
    l.trim().startsWith("读经：") || l.trim().startsWith("讀經：")
  );
  if (scriptureIdx === -1) {
    return prefaceText + "\n" + outline;
  }
  lines.splice(scriptureIdx + 1, 0, "", prefaceText);
  return lines.join("\n");
}

async function generateAll() {
  if (!canGenerate.value) return;

  results.morning_revival.content = "";
  results.transcript.content = "";
  results.composite.content = "";
  results.morning_revival.error = "";
  results.transcript.error = "";
  results.composite.error = "";

  // Step 1：四路并发（晨兴 + 听抄正文 + 序言 + 添言）
  results.morning_revival.loading = true;
  results.transcript.loading = true;

  const tasks = [
    fetch("/api/testa/feast_outline/morning_revival", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: inputMorningRevival.value }),
    }).then(r => r.json()),
    fetch("/api/testa/feast_outline/transcript", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        original_outline: inputOutline.value,
        transcript: inputTranscript.value,
      }),
    }).then(r => r.json()),
    inputPreface.value.trim()
      ? fetch("/api/testa/feast_outline/preface", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: inputPreface.value }),
        }).then(r => r.json())
      : Promise.resolve({ outline: "" }),
    inputAddendum.value.trim()
      ? fetch("/api/testa/feast_outline/addendum", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: inputAddendum.value }),
        }).then(r => r.json())
      : Promise.resolve({ outline: "" }),
  ];

  const [mrResult, trResult, prefaceResult, addendumResult] = await Promise.allSettled(tasks);

  results.morning_revival.loading = false;
  results.transcript.loading = false;

  const mrOutline = mrResult.status === "fulfilled" ? (mrResult.value.outline || "") : "";
  const trOutline = trResult.status === "fulfilled" ? (trResult.value.outline || "") : "";
  const prefaceOutline = prefaceResult.status === "fulfilled" ? (prefaceResult.value.outline || "") : "";
  const addendumOutline = addendumResult.status === "fulfilled" ? (addendumResult.value.outline || "") : "";

  if (!mrOutline) results.morning_revival.error = "晨兴纲目生成失败，请重试";
  if (!trOutline) results.transcript.error = "听抄稿纲目生成失败，请重试";

  // 拼接前三行
  const header = (suffix) => {
    const parts = [
      inputLine1.value.trim(),
      inputLine2.value.trim(),
      inputLine3.value.trim() ? `${inputLine3.value.trim()}${suffix}` : "",
    ].filter(Boolean);
    return parts.length ? parts.join("\n") + "\n" : "";
  };

  // 晨兴纲目：无序言添言，直接加前三行
  results.morning_revival.content = mrOutline
    ? header("（晨兴信息选读的纲目）") + mrOutline
    : "";

  // 听抄稿纲目：序言插在读经后，添言加在末尾
  const transcriptWithPreface = insertAfterScripture(trOutline, prefaceOutline);
  const fullTranscriptDisplay = addendumOutline
    ? transcriptWithPreface + "\n\n" + addendumOutline
    : transcriptWithPreface;
  results.transcript.content = trOutline
    ? header("（听抄稿的纲目）") + fullTranscriptDisplay
    : "";

  // Step 2：串行跑复合（只传听抄稿正文纲目，不含序言和添言）
  if (!mrOutline || !trOutline) {
    results.composite.error = "晨兴纲目或听抄稿纲目生成失败，无法生成复合纲目";
    return;
  }

  results.composite.loading = true;
  try {
    const res = await fetch("/api/testa/feast_outline/composite", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        morning_revival_outline: mrOutline,
        transcript_outline: trOutline,
      }),
    });
    const data = await res.json();
    const compositeOutline = data.outline || "";
    const compositeWithPreface = insertAfterScripture(compositeOutline, prefaceOutline);
    const fullCompositeDisplay = addendumOutline
      ? compositeWithPreface + "\n\n" + addendumOutline
      : compositeWithPreface;
    results.composite.content = compositeOutline
      ? header("（复合的纲目）") + fullCompositeDisplay
      : "";
    showToast("节期纲目生成完成！");
  } catch (e) {
    results.composite.error = "复合纲目生成失败，请重试";
  } finally {
    results.composite.loading = false;
  }
}

// 刷格式并下载
const formatLoading = reactive({
  morning_revival: false,
  transcript: false,
  composite: false,
});

async function formatAndDownload(type) {
  const content = results[type].content;
  if (!content) return;
  formatLoading[type] = true;
  try {
    const res = await fetch("/api/testa/translate/format_download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: content, lang: "zh" }),
    });
    if (!res.ok) { showToast("下载失败"); return; }
    const typeLabel = { morning_revival: "晨兴纲目", transcript: "听抄稿纲目", composite: "复合纲目" }[type];
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${typeLabel}.docx`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    showToast("下载失败");
  } finally {
    formatLoading[type] = false;
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
      <span class="header-title">节期纲目（testA）</span>
    </div>

    <div class="card">
      <div class="field">
        <label class="field-label">第一行</label>
        <a-input v-model:value="inputLine1" placeholder="如：二○二五年夏季训练" :disabled="isGenerating" />
      </div>
      <div class="field">
        <label class="field-label">第二行</label>
        <a-input v-model:value="inputLine2" placeholder="如：总题：新约中基督与召会的奥秘" :disabled="isGenerating" />
      </div>
      <div class="field">
        <label class="field-label">第三行</label>
        <a-input v-model:value="inputLine3" placeholder="如：第一篇　基督是召会的头" :disabled="isGenerating" />
      </div>
      <div class="divider" />

      <div class="field">
        <label class="field-label">
          <div class="label-dot dot-morning"></div>
          晨兴信息选读原文 <span class="required">*</span>
        </label>
        <a-textarea
          v-model:value="inputMorningRevival"
          placeholder="粘贴晨兴信息选读原文…"
          :disabled="isGenerating"
          :auto-size="{ minRows: 4, maxRows: 10 }"
        />
        <div class="char-row">
          <span class="char-count">{{ (inputMorningRevival || '').length.toLocaleString() }} / 100,000 字</span>
        </div>
      </div>

      <div class="field">
        <label class="field-label">
          <div class="label-dot dot-outline"></div>
          纲目原文 <span class="required">*</span>
        </label>
        <a-textarea
          v-model:value="inputOutline"
          placeholder="粘贴纲目原文…"
          :disabled="isGenerating"
          :auto-size="{ minRows: 3, maxRows: 8 }"
        />
        <div class="char-row">
          <span class="char-count">{{ (inputOutline || '').length.toLocaleString() }} / 100,000 字</span>
        </div>
      </div>

      <div class="field">
        <label class="field-label">
          <div class="label-dot dot-transcript"></div>
          听抄稿 <span class="required">*</span>
        </label>
        <a-textarea
          v-model:value="inputTranscript"
          placeholder="粘贴听抄稿内容…"
          :disabled="isGenerating"
          :auto-size="{ minRows: 4, maxRows: 10 }"
        />
        <div class="char-row">
          <span class="char-count">{{ (inputTranscript || '').length.toLocaleString() }} / 100,000 字</span>
        </div>
      </div>

      <div class="field">
        <label class="field-label">
          <div class="label-dot" style="background:#722ed1"></div>
          序言 <span style="font-size:12px;color:#8c8c8c;font-weight:400">（可选）</span>
        </label>
        <a-textarea
          v-model:value="inputPreface"
          placeholder="粘贴序言内容…（选填）"
          :disabled="isGenerating"
          :auto-size="{ minRows: 3, maxRows: 8 }"
        />
      </div>
      <div class="field">
        <label class="field-label">
          <div class="label-dot" style="background:#eb2f96"></div>
          添言 <span style="font-size:12px;color:#8c8c8c;font-weight:400">（可选）</span>
        </label>
        <a-textarea
          v-model:value="inputAddendum"
          placeholder="粘贴添言内容…（选填）"
          :disabled="isGenerating"
          :auto-size="{ minRows: 3, maxRows: 8 }"
        />
      </div>

      <div class="divider" />

      <div class="action-row">
        <a-button class="clear-btn" :disabled="isGenerating" @click="clearAll">清空</a-button>
        <a-button
          class="generate-btn"
          :disabled="!canGenerate"
          :loading="isGenerating"
          @click="generateAll"
        >
          {{ isGenerating ? "生成中…" : "生成节期纲目" }}
        </a-button>
      </div>
    </div>

    <!-- 晨兴纲目 -->
    <div class="result-card" v-if="results.morning_revival.loading || results.morning_revival.content || results.morning_revival.error">
      <div class="result-head">
        <div class="result-icon" style="background:#1890ff"></div>
        <span class="result-title">晨兴纲目</span>
        <span v-if="results.morning_revival.loading" class="badge badge-loading">生成中…</span>
        <span v-else-if="results.morning_revival.content" class="badge badge-done">已完成</span>
        <button v-if="results.morning_revival.content" class="copy-btn" @click="copyText(results.morning_revival.content)">
          <i class="ti ti-copy" aria-hidden="true"></i> 复制
        </button>
      </div>
      <div class="divider" />
      <div v-if="results.morning_revival.loading" class="loading-text">
        <a-spin size="small" /> 正在生成晨兴纲目，请稍候…
      </div>
      <div v-else-if="results.morning_revival.error" class="error-msg">{{ results.morning_revival.error }}</div>
      <pre v-else class="result-body">{{ results.morning_revival.content }}</pre>
    </div>
    <div v-if="results.morning_revival.content" class="format-bar">
      <a-button class="format-btn" :loading="formatLoading.morning_revival" @click="formatAndDownload('morning_revival')">
        <template #icon><DownloadOutlined /></template>
        刷格式并下载
      </a-button>
    </div>

    <!-- 听抄稿纲目 -->
    <div class="result-card" v-if="results.transcript.loading || results.transcript.content || results.transcript.error">
      <div class="result-head">
        <div class="result-icon" style="background:#52c41a"></div>
        <span class="result-title">听抄稿纲目</span>
        <span v-if="results.transcript.loading" class="badge badge-loading">生成中…</span>
        <span v-else-if="results.transcript.content" class="badge badge-done">已完成</span>
        <button v-if="results.transcript.content" class="copy-btn" @click="copyText(results.transcript.content)">
          <i class="ti ti-copy" aria-hidden="true"></i> 复制
        </button>
      </div>
      <div class="divider" />
      <div v-if="results.transcript.loading" class="loading-text">
        <a-spin size="small" /> 正在生成听抄稿纲目，请稍候…
      </div>
      <div v-else-if="results.transcript.error" class="error-msg">{{ results.transcript.error }}</div>
      <pre v-else class="result-body">{{ results.transcript.content }}</pre>
    </div>
    <div v-if="results.transcript.content" class="format-bar">
      <a-button class="format-btn" :loading="formatLoading.transcript" @click="formatAndDownload('transcript')">
        <template #icon><DownloadOutlined /></template>
        刷格式并下载
      </a-button>
    </div>

    <!-- 复合纲目 -->
    <div class="result-card" v-if="results.morning_revival.loading || results.transcript.loading || results.composite.loading || results.composite.content || results.composite.error || (results.morning_revival.content && results.transcript.content)">
      <div class="result-head">
        <div class="result-icon" style="background:#fa8c16"></div>
        <span class="result-title">复合纲目</span>
        <span v-if="results.composite.loading" class="badge badge-loading">生成中…</span>
        <span v-else-if="results.composite.content" class="badge badge-done">已完成</span>
        <span v-else-if="results.morning_revival.loading || results.transcript.loading" class="badge badge-waiting">等待中</span>
        <button v-if="results.composite.content" class="copy-btn" @click="copyText(results.composite.content)">
          <i class="ti ti-copy" aria-hidden="true"></i> 复制
        </button>
      </div>
      <div class="divider" />
      <div v-if="results.composite.loading" class="loading-text">
        <a-spin size="small" /> 正在生成复合纲目，请稍候…
      </div>
      <div v-else-if="results.composite.error" class="error-msg">{{ results.composite.error }}</div>
      <div v-else-if="results.morning_revival.loading || results.transcript.loading" class="waiting-text">
        等待晨兴纲目和听抄稿纲目生成完成后自动开始…
      </div>
      <pre v-else-if="results.composite.content" class="result-body">{{ results.composite.content }}</pre>
    </div>
    <div v-if="results.composite.content" class="format-bar">
      <a-button class="format-btn" :loading="formatLoading.composite" @click="formatAndDownload('composite')">
        <template #icon><DownloadOutlined /></template>
        刷格式并下载
      </a-button>
    </div>
  </div>
</template>

<style scoped>
.toast {
  position: fixed; top: 20px; left: 50%; transform: translateX(-50%);
  background: #52c41a; color: #fff; padding: 8px 24px;
  border-radius: 20px; font-size: 14px; z-index: 9999; pointer-events: none;
}
.page { min-height: 100vh; background: #f5f5f5; padding-bottom: 40px; }
.header {
  background: #001529; padding: 0 20px; height: 52px;
  display: flex; align-items: center; position: relative;
}
.back-btn { color: #55bbff; font-size: 18px; position: absolute; left: 12px; }
.header-title { color: #fff; font-size: 16px; font-weight: 500; flex: 1; text-align: center; }
.card {
  background: #fff; border-radius: 8px; padding: 16px 20px;
  margin: 12px 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.field { margin-bottom: 14px; }
.field:last-child { margin-bottom: 0; }
.field-label {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; font-weight: 500; color: #333; margin-bottom: 6px;
}
.label-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.dot-morning { background: #1890ff; }
.dot-outline { background: #52c41a; }
.dot-transcript { background: #fa8c16; }
.required { color: #ff4d4f; }
.char-row { display: flex; justify-content: space-between; margin-top: 4px; }
.char-count { font-size: 12px; color: #aaa; }
.divider { height: 1px; background: #f0f0f0; margin: 12px 0; }
.action-row { display: flex; justify-content: center; gap: 10px; }
.clear-btn {
  padding: 0 20px; height: 36px; border-radius: 6px;
  border: 0.5px solid #d9d9d9; background: #fff; color: #666;
  font-size: 13px; font-weight: 500;
}
.generate-btn {
  background: #55bbff; border-color: #55bbff; color: #fff;
  font-size: 14px; font-weight: 500; letter-spacing: 1px;
  padding: 0 40px; height: 36px; border-radius: 6px;
}
.generate-btn:hover { background: #7cccff; border-color: #7cccff; }
.result-card {
  background: #fff; border-radius: 8px; border: 0.5px solid #e8e8e8;
  padding: 14px 16px; margin: 0 16px 0;
}
.result-head { display: flex; align-items: center; gap: 8px; }
.result-icon { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.result-title { font-size: 13px; font-weight: 500; color: #333; flex: 1; }
.badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; }
.badge-loading { background: #fff7e6; color: #d46b08; border: 0.5px solid #ffd591; }
.badge-done    { background: #f6ffed; color: #389e0d; border: 0.5px solid #b7eb8f; }
.badge-waiting { background: #f5f5f5; color: #8c8c8c; border: 0.5px solid #d9d9d9; }
.copy-btn {
  background: #fff; border: 1px solid #d9d9d9; color: #555;
  padding: 3px 12px; border-radius: 6px; cursor: pointer; font-size: 12px;
}
.copy-btn:hover { color: #1890ff; border-color: #1890ff; }
.result-body {
  font-size: 13px; color: #333; line-height: 1.9;
  white-space: pre-wrap; word-break: break-word; margin: 0;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}
.loading-text {
  font-size: 12px; color: #8c8c8c; padding: 8px 0;
  display: flex; align-items: center; gap: 6px;
}
.waiting-text { font-size: 12px; color: #8c8c8c; padding: 8px 0; text-align: center; }
.error-msg {
  color: #cf1322; font-size: 13px; padding: 8px 12px;
  background: #fff2f0; border-radius: 6px; border: 1px solid #ffccc7;
}
.format-bar { margin: 8px 16px 12px; }
.format-btn {
  width: 100%; height: 34px; background: #1890ff; border-color: #1890ff;
  color: #fff; font-size: 13px; font-weight: 500; border-radius: 6px;
}
.format-btn:hover { background: #40a9ff; border-color: #40a9ff; }
</style>

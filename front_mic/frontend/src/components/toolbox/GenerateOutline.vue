<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { DownloadOutlined, LeftOutlined } from "@ant-design/icons-vue";

const router = useRouter();

const query = ref("");
const outlineNature = ref("一般性");
const burdenDescription = ref("");
const loading = ref(false);
const error = ref(null);
const answer = ref(null);
const chunksUsed = ref(0);
const chunksData = ref([]);
const showChunks = ref(false);
const toast = ref("");

// 版本切换
const mode = ref("2.0"); // '2.0' | '3.5'

// 3.5 推荐重点
const conceptMode = ref("ai"); // 'ai' | 'manual'
const conceptLoading = ref(false);
const conceptCandidates = ref(null); // { revelation, experience, practice }
const selectedRevelation = ref([]);
const selectedExperience = ref([]);
const selectedPractice = ref([]);
const manualRevelation = ref("");
const manualExperience = ref("");
const manualPractice = ref("");

// 3.5 结果
const answer35 = ref(null);
const chunksUsed35 = ref(0);
const expandedCount35 = ref(0);
const chunks35 = ref([]);
const expandedChunks35 = ref([]);
const showChunks35 = ref(false);
const showExpandedChunks35 = ref(false);
const formatLoading35 = ref(false);
const loading35 = ref(false);
const error35 = ref(null);

const outlineNatureOptions = ["一般性", "真理启示", "生命经历", "应用实行"];

function showToast(msg) {
  toast.value = msg;
  setTimeout(() => {
    if (toast.value === msg) toast.value = "";
  }, 2500);
}

function switchMode(m) {
  mode.value = m;
  error35.value = null;
}

function copyResult() {
  if (!answer.value) return;
  const text = query.value ? `${query.value}\n\n${answer.value}` : answer.value;
  navigator.clipboard.writeText(text).then(() => showToast("已复制到剪贴板"));
}

function copyResult35() {
  if (!answer35.value) return;
  const text = query.value ? `${query.value}\n\n${answer35.value}` : answer35.value;
  navigator.clipboard.writeText(text).then(() => showToast("已复制到剪贴板"));
}

const formatLoading = ref(false);

async function formatAndDownload() {
  const text = answer.value;
  if (!text) return;
  const fullText = query.value.trim()
    ? `${query.value.trim()}\n${text}`
    : text;
  formatLoading.value = true;
  try {
    const res = await fetch("/api/testa/translate/format_download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: fullText, lang: "zh" }),
    });
    if (!res.ok) {
      showToast("下载失败");
      return;
    }
    const safeName = (query.value || "纲目").replace(/[\\/:*?"<>|]/g, "");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${safeName}.docx`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    showToast("下载失败");
  } finally {
    formatLoading.value = false;
  }
}

async function formatAndDownload35() {
  if (!answer35.value) return;
  const fullText = query.value.trim()
    ? `${query.value.trim()}\n${answer35.value}`
    : answer35.value;
  formatLoading35.value = true;
  try {
    const res = await fetch("/api/testa/translate/format_download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: fullText, lang: "zh" }),
    });
    if (!res.ok) {
      showToast("下载失败");
      return;
    }
    const safeName = (query.value || "纲目").replace(/[\\/:*?"<>|]/g, "");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${safeName}.docx`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    showToast("下载失败");
  } finally {
    formatLoading35.value = false;
  }
}

function clearAll() {
  query.value = "";
  outlineNature.value = "一般性";
  burdenDescription.value = "";
  answer.value = null;
  error.value = null;
  chunksUsed.value = 0;
  chunksData.value = [];
  showChunks.value = false;
  conceptCandidates.value = null;
  selectedRevelation.value = [];
  selectedExperience.value = [];
  selectedPractice.value = [];
  manualRevelation.value = "";
  manualExperience.value = "";
  manualPractice.value = "";
  answer35.value = null;
  error35.value = null;
  chunksUsed35.value = 0;
  expandedCount35.value = 0;
  chunks35.value = [];
  expandedChunks35.value = [];
  showChunks35.value = false;
  showExpandedChunks35.value = false;
}

function toggleChunks() {
  showChunks.value = !showChunks.value;
}

async function extractConcepts() {
  if (!query.value.trim()) {
    error35.value = "请先输入纲目主题";
    return;
  }
  conceptLoading.value = true;
  conceptCandidates.value = null;
  error35.value = null;
  try {
    const res = await fetch("/api/testa/generate_outline/step1", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query.value.trim(),
        outline_nature: outlineNature.value,
        burden_description: burdenDescription.value,
      }),
    });
    if (!res.ok) throw new Error("概念抽取失败");
    const data = await res.json();
    conceptCandidates.value = {
      revelation: [...(data.revelation || [])],
      experience: [...(data.experience || [])],
      practice: [...(data.practice || [])],
    };
    selectedRevelation.value = [...(data.revelation || [])];
    selectedExperience.value = [...(data.experience || [])];
    selectedPractice.value = [...(data.practice || [])];
  } catch (e) {
    error35.value = e.message || "概念抽取失败，请重试";
  } finally {
    conceptLoading.value = false;
  }
}

function toggleConcept(layer, word) {
  const map = { revelation: selectedRevelation, experience: selectedExperience, practice: selectedPractice };
  const arr = map[layer];
  const idx = arr.value.indexOf(word);
  if (idx >= 0) arr.value.splice(idx, 1);
  else arr.value.push(word);
}

function parseManual(str) {
  return str.split(/[，,、\n]/).map((s) => s.trim()).filter(Boolean);
}

async function generate35() {
  if (!query.value.trim()) {
    error35.value = "请先输入纲目主题";
    return;
  }
  loading35.value = true;
  error35.value = null;
  answer35.value = null;

  let preset_revelation = [];
  let preset_experience = [];
  let preset_practice = [];

  if (conceptMode.value === "ai" && conceptCandidates.value) {
    preset_revelation = selectedRevelation.value;
    preset_experience = selectedExperience.value;
    preset_practice = selectedPractice.value;
  } else if (conceptMode.value === "manual") {
    preset_revelation = parseManual(manualRevelation.value);
    preset_experience = parseManual(manualExperience.value);
    preset_practice = parseManual(manualPractice.value);
  }

  try {
    const res = await fetch("/api/testa/generate_outline/query35", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query.value.trim(),
        outline_nature: outlineNature.value,
        burden_description: burdenDescription.value,
        preset_revelation,
        preset_experience,
        preset_practice,
      }),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      error35.value = errData.detail || "生成失败，请稍后重试";
      return;
    }
    const data = await res.json();
    if (data.answer) {
      answer35.value = data.answer;
      chunksUsed35.value = data.chunks_used || 0;
      expandedCount35.value = data.expanded_results_count || 0;
      chunks35.value = data.chunks || [];
      expandedChunks35.value = data.expanded_chunks || [];
      showToast("纲目生成完成！");
    } else {
      error35.value = "生成失败，请稍后重试";
    }
  } catch (e) {
    error35.value = (e && e.message) || "网络错误，请稍后重试";
  } finally {
    loading35.value = false;
  }
}

async function generate() {
  const text = (query.value || "").trim();
  if (!text) {
    error.value = "请先输入纲目主题";
    answer.value = null;
    return;
  }
  loading.value = true;
  error.value = null;
  answer.value = null;
  chunksUsed.value = 0;
  chunksData.value = [];
  showChunks.value = false;

  try {
    const res = await fetch("/api/testa/generate_outline/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: text,
        outline_nature: outlineNature.value || "一般性",
        burden_description: burdenDescription.value || "",
        audience: "",
      }),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      error.value = errData.detail || errData.error || "生成失败，请稍后重试";
      return;
    }
    const data = await res.json();
    if (data.answer) {
      answer.value = data.answer;
      chunksUsed.value = data.chunks_used || 0;
      chunksData.value = data.chunks || [];
      showToast("纲目生成完成！");
    } else {
      error.value = "生成失败，请稍后重试";
    }
  } catch (err) {
    error.value = (err && err.message) || "网络错误，请稍后重试";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="page">
    <div v-if="toast" class="toast">{{ toast }}</div>

    <!-- 顶栏 -->
    <div class="header">
      <a-button type="text" class="back-btn" @click="router.back()">
        <template #icon><LeftOutlined /></template>
      </a-button>
      <span class="header-title">PanAI 纲目生成</span>
    </div>

    <!-- 版本切换 -->
    <div class="version-bar">
      <div class="ver-btn" :class="{ active: mode === '2.0' }" @click="switchMode('2.0')">PanAI 2.0</div>
      <div class="ver-btn" :class="{ active: mode === '3.5' }" @click="switchMode('3.5')">PanAI 3.5</div>
    </div>

    <!-- 输入卡片 -->
    <div class="card" v-show="mode === '2.0' || mode === '3.5'">
      <div class="field">
        <label class="field-label">纲目主题 <span class="required">*</span></label>
        <a-input
          v-model:value="query"
          placeholder="请输入纲目主题，如：基督是我们的生命"
          :disabled="loading || loading35"
          size="large"
        />
      </div>

      <div class="field">
        <label class="field-label">纲目性质</label>
        <div class="seg-group">
          <div
            v-for="opt in outlineNatureOptions"
            :key="opt"
            class="seg-btn"
            :class="{ active: outlineNature === opt, disabled: loading || loading35 }"
            @click="!(loading || loading35) && (outlineNature = opt)"
          >
            {{ opt }}
          </div>
        </div>
      </div>

      <div class="field">
        <label class="field-label">
          负担说明
          <span class="optional">（可选）</span>
        </label>
        <a-textarea
          v-model:value="burdenDescription"
          placeholder="请输入负担说明…"
          :disabled="loading || loading35"
          :auto-size="{ minRows: 2, maxRows: 4 }"
        />
      </div>

      <div class="divider" />

      <div class="action-row" v-show="mode === '2.0'">
        <a-button class="clear-btn" :disabled="loading" @click="clearAll">
          清空
        </a-button>
        <a-button
          type="primary"
          class="generate-btn"
          :loading="loading"
          :disabled="loading"
          @click="generate"
        >
          {{ loading ? "生成中…" : "生成纲目" }}
        </a-button>
      </div>
    </div>

    <!-- 3.5 推荐重点 -->
    <div class="card concept-card" v-show="mode === '3.5'">
      <div class="concept-header">
        <span class="field-label" style="margin-bottom: 0">推荐重点</span>
        <div class="mode-toggle">
          <div class="mode-btn" :class="{ active: conceptMode === 'ai' }" @click="conceptMode = 'ai'">自动推荐</div>
          <div class="mode-btn" :class="{ active: conceptMode === 'manual' }" @click="conceptMode = 'manual'">手动输入</div>
        </div>
      </div>

      <!-- AI 推荐模式 -->
      <template v-if="conceptMode === 'ai'">
        <div v-if="conceptCandidates" class="concept-layers">
          <div class="concept-layer">
            <div class="layer-header">
              <div class="layer-dot dot-revelation"></div>
              <span class="layer-label">真理启示</span>
            </div>
            <div class="tags">
              <span
                v-for="word in conceptCandidates.revelation"
                :key="word"
                class="tag tag-revelation"
                :class="{ unchecked: !selectedRevelation.includes(word) }"
                @click="toggleConcept('revelation', word)"
              >{{ word }}</span>
            </div>
          </div>
          <div class="concept-layer">
            <div class="layer-header">
              <div class="layer-dot dot-experience"></div>
              <span class="layer-label">生命经历</span>
            </div>
            <div class="tags">
              <span
                v-for="word in conceptCandidates.experience"
                :key="word"
                class="tag tag-experience"
                :class="{ unchecked: !selectedExperience.includes(word) }"
                @click="toggleConcept('experience', word)"
              >{{ word }}</span>
            </div>
          </div>
          <div class="concept-layer">
            <div class="layer-header">
              <div class="layer-dot dot-practice"></div>
              <span class="layer-label">应用实行</span>
            </div>
            <div class="tags">
              <span
                v-for="word in conceptCandidates.practice"
                :key="word"
                class="tag tag-practice"
                :class="{ unchecked: !selectedPractice.includes(word) }"
                @click="toggleConcept('practice', word)"
              >{{ word }}</span>
            </div>
          </div>
        </div>
        <div v-else-if="conceptLoading" class="concept-loading">
          <a-spin size="small" /> 概念抽取中…
        </div>
        <div v-else class="concept-hint">点「推荐重点」自动抽取概念，或直接点「生成纲目」跳过</div>
      </template>

      <!-- 手动输入模式 -->
      <template v-if="conceptMode === 'manual'">
        <div class="concept-layer">
          <div class="layer-label">真理启示</div>
          <a-input v-model:value="manualRevelation" placeholder="用逗号分隔，如：基督，生命，赐生命的灵" />
        </div>
        <div class="concept-layer">
          <div class="layer-label">生命经历</div>
          <a-input v-model:value="manualExperience" placeholder="用逗号分隔" />
        </div>
        <div class="concept-layer">
          <div class="layer-label">应用实行</div>
          <a-input v-model:value="manualPractice" placeholder="用逗号分隔" />
        </div>
      </template>

      <div class="concept-action-row">
        <button
          v-if="conceptMode === 'ai'"
          class="recommend-btn"
          :disabled="conceptLoading"
          @click="extractConcepts"
        >
          <i class="ti ti-sparkles" aria-hidden="true"></i>
          {{ conceptLoading ? "推荐中…" : "推荐重点" }}
        </button>
        <div class="right-btns">
          <a-button class="clear-btn" :disabled="loading35" @click="clearAll">清空</a-button>
          <a-button type="primary" class="generate-btn" :loading="loading35" @click="generate35">
            {{ loading35 ? "生成中…" : "生成纲目" }}
          </a-button>
        </div>
      </div>
    </div>

    <!-- 2.0 错误提示 -->
    <div v-if="error && mode === '2.0'" class="error-msg">{{ error }}</div>

    <!-- 2.0 结果卡片 -->
    <template v-if="mode === '2.0'">
      <div v-if="answer" class="card result-card">
        <div class="result-head">
          <span class="result-title-text">生成结果</span>
          <span class="chunks-badge" @click="toggleChunks">
            参考段落 {{ chunksUsed }} 条
          </span>
          <button class="copy-btn" @click="copyResult">复制</button>
        </div>
        <div class="divider" />
        <div class="result-topic">{{ query }}</div>
        <pre class="result-body">{{ answer }}</pre>
      </div>
      <div v-if="answer" class="format-bar">
        <a-button class="format-download-btn" :loading="formatLoading" @click="formatAndDownload">
          <template #icon><DownloadOutlined /></template>
          刷格式并下载
        </a-button>
      </div>

      <div v-if="answer && showChunks" class="card chunks-card">
        <div class="chunks-title">参考段落</div>
        <div v-for="(chunk, idx) in chunksData" :key="idx" class="chunk-item">
          <div class="chunk-source">
            出处：<span>{{ chunk.book_title }}</span>
            {{ chunk.message_number ? ` 第${chunk.message_number}篇` : "" }}
            {{ chunk.message_title || "" }}
          </div>
          <div class="chunk-text">
            {{ (chunk.text || "").slice(0, 50) }}…
          </div>
        </div>
      </div>
    </template>

    <!-- 3.5 结果区 -->
    <div v-show="mode === '3.5'">
      <div v-if="error35" class="error-msg">{{ error35 }}</div>

      <div v-if="answer35" class="card result-card">
        <div class="result-head">
          <span class="result-title">生成结果</span>
          <span class="chunks-badge" @click="showChunks35 = !showChunks35">
            主检索 {{ chunksUsed35 }} 条
          </span>
          <span class="chunks-badge expanded-badge" @click="showExpandedChunks35 = !showExpandedChunks35">
            路3扩展 {{ expandedCount35 }} 条
          </span>
          <button class="copy-btn" @click="copyResult35">复制</button>
        </div>
        <div class="divider" />
        <div class="result-topic">{{ query }}</div>
        <pre class="result-body">{{ answer35 }}</pre>
      </div>

      <div v-if="answer35" class="format-bar">
        <a-button class="format-download-btn" :loading="formatLoading35" @click="formatAndDownload35">
          <template #icon><DownloadOutlined /></template>
          刷格式并下载
        </a-button>
      </div>

      <div v-if="answer35 && showChunks35" class="card chunks-card">
        <div class="chunks-title">主检索段落</div>
        <div v-for="(chunk, idx) in chunks35" :key="idx" class="chunk-item">
          <div class="chunk-source">
            出处：<span>{{ chunk.book_title }}</span>
            {{ chunk.message_number ? ` 第${chunk.message_number}篇` : "" }}
            {{ chunk.message_title || "" }}
          </div>
          <div class="chunk-text">{{ (chunk.text || "").slice(0, 50) }}…</div>
        </div>
      </div>

      <div v-if="answer35 && showExpandedChunks35" class="card chunks-card">
        <div class="chunks-title">路3扩展段落</div>
        <div v-for="(chunk, idx) in expandedChunks35" :key="idx" class="chunk-item">
          <div class="chunk-source">
            出处：<span>{{ chunk.book_title }}</span>
            {{ chunk.message_number ? ` 第${chunk.message_number}篇` : "" }}
            {{ chunk.message_title || "" }}
            <span class="route3-tag" v-if="chunk.expanded_from">{{ chunk.expanded_from }}</span>
          </div>
          <div class="chunk-text">{{ (chunk.text || "").slice(0, 50) }}…</div>
        </div>
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
.back-btn {
  color: #55bbff;
  font-size: 18px;
  position: absolute;
  left: 12px;
}
.header-title {
  color: #fff;
  font-size: 16px;
  font-weight: 500;
  flex: 1;
  text-align: center;
}
.version-bar {
  display: flex;
  gap: 8px;
  padding: 16px 16px 0;
}
.ver-btn {
  flex: 1;
  padding: 9px 0;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  border: 1px solid #d9d9d9;
  background: #fff;
  color: #8c8c8c;
  text-align: center;
  cursor: pointer;
  user-select: none;
}
.ver-btn.active {
  background: #1890ff;
  border-color: #1890ff;
  color: #fff;
}
.card {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  margin: 12px 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
.field {
  margin-bottom: 14px;
}
.field:last-child {
  margin-bottom: 0;
}
.field-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: #333;
  margin-bottom: 6px;
}
.required {
  color: #ff4d4f;
}
.optional {
  font-weight: 400;
  color: #8c8c8c;
  font-size: 12px;
}
.seg-group {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.seg-btn {
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid #d9d9d9;
  background: #fff;
  color: #555;
  font-size: 13px;
  cursor: pointer;
  user-select: none;
  transition: all 0.15s;
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
.seg-btn.disabled {
  opacity: 0.65;
  cursor: not-allowed;
}
.divider {
  height: 1px;
  background: #f0f0f0;
  margin: 12px 0;
}
.action-row {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}
.clear-btn {
  font-weight: 500;
  border-color: #d9d9d9;
  color: #666;
}
.clear-btn:hover {
  border-color: #ff4d4f;
  color: #ff4d4f;
}
.generate-btn {
  background: #1890ff;
  border-color: #1890ff;
  min-width: 110px;
  font-weight: 500;
}
.generate-btn:hover {
  background: #40a9ff;
  border-color: #40a9ff;
}
.error-msg {
  margin: 0 16px 12px;
  color: #cf1322;
  font-size: 13px;
  padding: 8px 12px;
  background: #fff2f0;
  border-radius: 6px;
  border: 1px solid #ffccc7;
}
.result-card {
  margin-top: 0;
}
.result-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.result-title-text,
.result-title {
  font-size: 14px;
  font-weight: 500;
  color: #333;
  flex: 1;
}
.chunks-badge {
  font-size: 11px;
  color: #1890ff;
  background: #e6f7ff;
  border: 1px solid #91d5ff;
  border-radius: 10px;
  padding: 2px 10px;
  cursor: pointer;
  user-select: none;
}
.chunks-badge:hover {
  background: #bae7ff;
}
.copy-btn {
  background: #fff;
  border: 1px solid #d9d9d9;
  color: #555;
  padding: 3px 14px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}
.copy-btn:hover {
  color: #1890ff;
  border-color: #1890ff;
}
.format-bar {
  margin: 0 16px 12px;
}
.format-download-btn {
  width: 100%;
  height: 38px;
  background: #55bbff;
  border-color: #55bbff;
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  border-radius: 6px;
}
.format-download-btn:hover {
  background: #7cccff;
  border-color: #7cccff;
  color: #fff;
}
.result-topic {
  text-align: center;
  font-weight: 500;
  font-size: 15px;
  color: #333;
  padding: 10px 0 6px;
}
.result-body {
  font-size: 14px;
  color: #333;
  line-height: 1.9;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
}
.chunks-card {
  margin-top: 0;
}
.chunks-title {
  font-size: 13px;
  font-weight: 500;
  color: #333;
  margin-bottom: 10px;
}
.chunk-item {
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}
.chunk-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}
.chunk-source {
  font-size: 12px;
  color: #8c8c8c;
  margin-bottom: 3px;
}
.chunk-source span {
  color: #1890ff;
  font-weight: 500;
}
.chunk-text {
  font-size: 12px;
  color: #aaa;
  line-height: 1.6;
}
.concept-card {
  margin-top: 0;
}
.concept-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.mode-toggle {
  display: flex;
  background: #f5f5f5;
  border-radius: 8px;
  padding: 3px;
  gap: 2px;
}
.mode-btn {
  padding: 5px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  color: #8c8c8c;
  cursor: pointer;
  border: none;
  background: transparent;
  transition: all 0.15s;
  user-select: none;
}
.mode-btn.active {
  background: #fff;
  color: #1890ff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}
.concept-layers {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 20px;
}
.concept-layer {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.layer-header {
  display: flex;
  align-items: center;
  gap: 6px;
}
.layer-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot-revelation {
  background: #2f54eb;
}
.dot-experience {
  background: #389e0d;
}
.dot-practice {
  background: #d46b08;
}
.layer-label {
  font-size: 12px;
  font-weight: 500;
  color: #8c8c8c;
  letter-spacing: 0.3px;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.tag {
  display: inline-flex;
  align-items: center;
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  user-select: none;
  transition: all 0.15s;
}
.tag-revelation {
  background: #f0f5ff;
  border: 1px solid #adc6ff;
  color: #2f54eb;
}
.tag-experience {
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  color: #389e0d;
}
.tag-practice {
  background: #fff7e6;
  border: 1px solid #ffd591;
  color: #d46b08;
}
.tag.unchecked {
  opacity: 0.3;
  background: #f5f5f5;
  border-color: #d9d9d9;
  color: #8c8c8c;
}
.concept-hint {
  font-size: 13px;
  color: #8c8c8c;
  padding: 8px 0;
  margin-bottom: 14px;
}
.concept-loading {
  font-size: 13px;
  color: #8c8c8c;
  padding: 8px 0;
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 14px;
}
.concept-action-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.recommend-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  border-radius: 8px;
  border: 1px solid #1890ff;
  background: #e6f7ff;
  color: #1890ff;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}
.recommend-btn:hover {
  background: #bae7ff;
}
.recommend-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.right-btns {
  display: flex;
  gap: 8px;
}
.expanded-badge {
  background: #fff7e6;
  color: #d46b08;
  border-color: #ffd591;
}
.route3-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: #fff7e6;
  color: #d46b08;
  border: 0.5px solid #ffd591;
  margin-left: 4px;
}
</style>

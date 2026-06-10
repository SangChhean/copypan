<script setup>
import { ref, computed, watch, nextTick } from "vue";
import { LoadingOutlined, CopyOutlined } from "@ant-design/icons-vue";

const NATURE_OPTIONS = ["一般性", "真理启示", "生命经历", "应用实行"];

const query = ref("");
const outlineNature = ref("");
const referenceExcerpt = ref("");  // 原稿内容（原 burdenDescription）
const burdenResult = ref("");      // 生成的负担说明（可编辑）
const burdenLoading = ref(false);
const burdenCandidates = ref([]);  // 情境B三条候选
const selectedCandidate = ref(0);  // 选中的候选索引
const referenceExcerptEl = ref(null);
const burdenResultEl = ref(null);

const loading = ref(false);
const error = ref(null);
const answer = ref(null);
const chunksUsed = ref(0);
const chunks = ref([]);
const concepts = ref({ revelation: [], experience: [], practice: [] });
const showChunks = ref(false);
const copied = ref(false);
const downloading = ref(false);

const analyzeLoading = ref(false);
const analyzed = ref(false);
const rewrittenQueries = ref([]);
const expandedNodes = ref([]);
const addingLayer = ref("");
const addingWord = ref("");

const hasSkeleton = ref(false);
const skeletonSteps = ref(0);
const skeletonPreview = ref([]);

const canGenerate = computed(
  () => !!query.value.trim() && !!outlineNature.value && !loading.value
);

const conceptLayers = computed(() => [
  { key: "revelation", label: "真理启示", words: concepts.value.revelation },
  { key: "experience", label: "生命经历", words: concepts.value.experience },
  { key: "practice", label: "应用实行", words: concepts.value.practice },
]);

function selectNature(nature) {
  outlineNature.value = nature;
}

async function generateBurden() {
  // 校验原稿内容去标点后>10字
  const cleaned = referenceExcerpt.value
    .replace(/[，。！？、；：""''「」【】《》\s]/gu, "")
    .replace(/\p{P}/gu, "");
  if (cleaned.length <= 10) {
    alert("请输入超过10个字的原稿内容");
    return;
  }
  burdenLoading.value = true;
  burdenCandidates.value = [];
  burdenResult.value = "";

  try {
    const res = await fetch("/api/panai2/generate_burden", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query.value,
        outline_nature: outlineNature.value,
        audience: "",
        reference_excerpt: referenceExcerpt.value,
      }),
    });
    const data = await res.json();

    if (data.scenario === "A") {
      // 情境A：直接填入负担说明框
      burdenResult.value = data.result || "";
      burdenCandidates.value = [];
    } else {
      // 情境B：显示三条候选
      burdenCandidates.value = data.candidates || [];
      if (burdenCandidates.value.length > 0) {
        selectedCandidate.value = 0;
        burdenResult.value = burdenCandidates.value[0];
      }
    }
  } catch (err) {
    error.value = (err && err.message) || "网络错误，请稍后重试";
  } finally {
    burdenLoading.value = false;
  }
}

async function doAnalyze() {
  if (!query.value.trim() || !outlineNature.value) return;
  analyzeLoading.value = true;
  analyzed.value = false;
  error.value = null;
  try {
    const res = await fetch("/api/panai2/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query.value,
        outline_nature: outlineNature.value,
        burden_description: burdenResult.value,
      }),
    });
    const data = await res.json();
    concepts.value = data.concepts || { revelation: [], experience: [], practice: [] };
    rewrittenQueries.value = data.rewritten_queries || [];
    expandedNodes.value = data.expanded_nodes || [];
    analyzed.value = true;
  } catch (err) {
    error.value = (err && err.message) || "网络错误，请稍后重试";
  } finally {
    analyzeLoading.value = false;
  }
}

function removeWord(layerKey, idx) {
  concepts.value[layerKey].splice(idx, 1);
  syncExpandedNodes();
}

function startAdd(layerKey) {
  addingLayer.value = layerKey;
  addingWord.value = "";
}

function confirmAdd() {
  if (!addingWord.value.trim()) {
    addingLayer.value = "";
    return;
  }
  concepts.value[addingLayer.value].push(addingWord.value.trim());
  syncExpandedNodes();
  addingLayer.value = "";
  addingWord.value = "";
}

function syncExpandedNodes() {
  expandedNodes.value = [
    ...concepts.value.revelation,
    ...concepts.value.experience,
    ...concepts.value.practice,
  ];
}

function resetAnalyze() {
  analyzed.value = false;
  concepts.value = { revelation: [], experience: [], practice: [] };
  rewrittenQueries.value = [];
  expandedNodes.value = [];
  answer.value = "";
  chunks.value = [];
  hasSkeleton.value = false;
  skeletonSteps.value = 0;
  skeletonPreview.value = [];
}

async function doGenerate() {
  if (!query.value.trim() || !outlineNature.value) return;
  loading.value = true;
  error.value = null;
  answer.value = null;
  chunksUsed.value = 0;
  chunks.value = [];
  showChunks.value = false;
  try {
    const res = await fetch("/api/panai2/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query.value,
        outline_nature: outlineNature.value,
        burden_description: burdenResult.value,
        expanded_nodes: expandedNodes.value,
        rewritten_queries: rewrittenQueries.value,
      }),
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      let detail = errorData.detail;
      if (Array.isArray(detail)) {
        detail = detail.map((x) => x?.msg || JSON.stringify(x)).join("；");
      }
      error.value = detail || errorData.error || "生成失败，请稍后重试";
      return;
    }
    const data = await res.json();
    answer.value = data.answer;
    chunksUsed.value = data.chunks_used || 0;
    chunks.value = data.chunks || [];
    hasSkeleton.value = data.has_skeleton || false;
    skeletonSteps.value = data.skeleton_steps || 0;
    skeletonPreview.value = data.skeleton_preview || [];
  } catch (err) {
    error.value = (err && err.message) || "网络错误，请稍后重试";
  } finally {
    loading.value = false;
  }
}

function copyAnswer() {
  if (!answer.value) return;
  navigator.clipboard.writeText(answer.value).then(() => {
    copied.value = true;
    setTimeout(() => {
      copied.value = false;
    }, 2000);
  });
}

function resizeTextarea(el) {
  if (!el) return;
  el.style.height = "auto";
  el.style.height = el.scrollHeight + "px";
}

function autoResize(e) {
  resizeTextarea(e.target);
}

watch([referenceExcerpt, burdenResult], async () => {
  await nextTick();
  resizeTextarea(referenceExcerptEl.value);
  resizeTextarea(burdenResultEl.value);
});

function parseFilename(disposition, fallback) {
  if (!disposition) return fallback;
  const m = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (m && m[1]) {
    try {
      return decodeURIComponent(m[1]);
    } catch (e) {
      return fallback;
    }
  }
  const m2 = /filename="?([^";]+)"?/i.exec(disposition);
  return m2 && m2[1] ? m2[1] : fallback;
}

async function downloadFormat() {
  if (!answer.value || downloading.value) return;
  downloading.value = true;
  try {
    const header = "\u200b\n\u200b\n" + query.value + "\n";
    const text = header + answer.value;
    const res = await fetch("/api/testb/format/zh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error("下载失败");
    const filename = parseFilename(
      res.headers.get("Content-Disposition"),
      "纲目.docx"
    );
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (e) {
    alert("下载失败，请重试");
  } finally {
    downloading.value = false;
  }
}
</script>

<template>
  <div class="box">
    <a-card>
      <p class="hint">
        输入纲目主题、选择纲目性质（可填负担说明），点击「生成纲目」即可。
      </p>
      <a-divider :style="{ margin: '12px 0' }" />

      <div class="field">
        <span class="label">主题：</span>
        <input
          v-model="query"
          type="text"
          class="query-input"
          placeholder="输入纲目主题"
          :disabled="loading"
        />
      </div>

      <div class="field">
        <span class="label">纲目性质：</span>
        <div class="nature-row">
          <button
            v-for="n in NATURE_OPTIONS"
            :key="n"
            type="button"
            class="nature-btn"
            :class="{ active: outlineNature === n }"
            :disabled="loading"
            @click="selectNature(n)"
          >
            {{ n }}
          </button>
        </div>
      </div>

      <div class="field field-col">
        <span class="label">原稿内容：</span>
        <textarea
          ref="referenceExcerptEl"
          v-model="referenceExcerpt"
          class="burden-area"
          placeholder="可选：粘贴原稿内容，用于生成负担说明"
          :disabled="loading"
          @input="autoResize"
        />
      </div>

      <!-- 生成负担说明 -->
      <div class="action-row">
        <button
          type="button"
          class="action-btn"
          :disabled="burdenLoading"
          @click="generateBurden"
        >
          <LoadingOutlined v-if="burdenLoading" class="btn-icon btn-spin" />
          {{ burdenLoading ? "生成中..." : "生成负担说明" }}
        </button>
      </div>

      <!-- 情境B候选 -->
      <div v-if="burdenCandidates.length > 0" class="candidates-box">
        <div
          v-for="(c, i) in burdenCandidates"
          :key="i"
          :class="['candidate-item', selectedCandidate === i ? 'selected' : '']"
          @click="selectedCandidate = i; burdenResult = c"
        >
          <span class="candidate-label">候选{{ ['一','二','三'][i] }}</span>
          {{ c }}
        </div>
      </div>

      <div class="field field-col">
        <span class="label">负担说明：</span>
        <textarea
          ref="burdenResultEl"
          v-model="burdenResult"
          class="burden-area"
          placeholder="生成后可在此编辑"
          :disabled="loading"
          @input="autoResize"
        />
      </div>

      <!-- 第一阶段按钮 -->
      <div v-if="!analyzed" class="action-row">
        <button
          type="button"
          class="action-btn"
          :disabled="analyzeLoading || !canGenerate"
          @click="doAnalyze"
        >
          <LoadingOutlined v-if="analyzeLoading" class="btn-icon btn-spin" />
          {{ analyzeLoading ? "分析中..." : "确认，推荐重点" }}
        </button>
      </div>

      <!-- 分析结果区 -->
      <div v-if="analyzed" class="analyze-result">
        <div class="concept-section">
          <div class="concept-row" v-for="layer in conceptLayers" :key="layer.key">
            <span class="layer-label">{{ layer.label }}：</span>
            <div class="concept-tags-wrap">
              <span :class="['concept-tag', `tag-${layer.key}`]" v-for="(word, idx) in layer.words" :key="idx">
                {{ word }}
                <span class="remove-btn" @click="removeWord(layer.key, idx)">×</span>
              </span>
              <template v-if="addingLayer === layer.key">
                <input
                  v-model="addingWord"
                  class="add-input"
                  placeholder="输入概念词"
                  @keyup.enter="confirmAdd"
                />
                <span class="confirm-btn" @click="confirmAdd">确认</span>
              </template>
              <span v-else class="add-btn" @click="startAdd(layer.key)">+ 添加</span>
            </div>
          </div>
        </div>
        <div class="rewrite-section">
          <div class="rewrite-title">【改写句】</div>
          <div v-for="(q, i) in rewrittenQueries" :key="i" class="rewrite-item">· {{ q }}</div>
        </div>
      </div>

      <!-- 第二阶段按钮 -->
      <div v-if="analyzed" class="action-row">
        <button
          type="button"
          class="action-btn"
          :disabled="loading"
          @click="doGenerate"
        >
          <LoadingOutlined v-if="loading" class="btn-icon btn-spin" />
          {{ loading ? "生成中..." : "生成纲目" }}
        </button>
        <button type="button" class="reset-btn" @click="resetAnalyze">
          重新生成重点
        </button>
      </div>
      <p v-if="loading" class="loading-hint">请耐心等待 1～2 分钟</p>
    </a-card>

    <div v-if="error" class="error">{{ error }}</div>

    <a-card v-if="answer" class="result-card">
      <template #title>
        <span>参考了 {{ chunksUsed }} 条段落</span>
        <div class="result-head-actions">
          <button type="button" class="copy-btn" @click="copyAnswer">
            <CopyOutlined /> {{ copied ? "已复制" : "复制" }}
          </button>
          <button type="button" class="format-btn"
            :disabled="downloading" @click="downloadFormat">
            <LoadingOutlined v-if="downloading" class="btn-spin" />
            {{ downloading ? "下载中…" : "⬇ 刷格式下载" }}
          </button>
        </div>
      </template>

      <div v-if="answer" class="skeleton-info">
        <!-- 有骨架 -->
        <div v-if="hasSkeleton" class="skeleton-header has-skeleton">
          ✅ 有骨架（{{ skeletonSteps }} 步）
        </div>
        <!-- 无骨架降级 -->
        <div v-else class="skeleton-header no-skeleton">
          ⚠️ 降级模式（无骨架）
        </div>
        <!-- 骨架步骤列表 -->
        <div v-if="hasSkeleton" class="skeleton-steps">
          <div
            v-for="(step, i) in skeletonPreview"
            :key="i"
            class="skeleton-step"
          >
            {{ step }}
          </div>
        </div>
      </div>

      <pre class="result-body">{{ answer }}</pre>

      <div v-if="chunks.length" class="chunks-section">
        <div class="chunks-head" @click="showChunks = !showChunks">
          <span>检索段落（共 {{ chunksUsed }} 条）</span>
          <button type="button" class="toggle-btn">
            {{ showChunks ? "收起" : "展开" }}
          </button>
        </div>
        <div v-if="showChunks" class="chunks-list">
          <div
            v-for="(c, idx) in chunks"
            :key="idx"
            class="chunk-item"
            :class="{ 'chunk-route3': c.source === 'skeleton_route' }"
          >
            <div class="chunk-meta">
              [{{ c.chunk_id }}] {{ c.book_title }}
              <template v-if="c.message_number">第{{ c.message_number }}篇</template>
              <template v-if="c.message_title"> {{ c.message_title }}</template>
              <span
                v-if="c.source === 'skeleton_route' && c.expanded_from"
                class="chunk-expanded-from"
              >
                路3 · {{ c.expanded_from }}
              </span>
            </div>
            <div class="chunk-text">{{ c.text }}</div>
          </div>
        </div>
      </div>
    </a-card>
  </div>
</template>

<style scoped>
.box {
  padding: 1em;
  max-width: 720px;
  margin: 0 auto;
}

.box :deep(.ant-card) {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.06);
}

.hint {
  color: #555;
  margin: 0;
  font-size: 0.95em;
  line-height: 1.5;
}

.field {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.field-col {
  align-items: flex-start;
}

.field .label {
  font-weight: 600;
  color: #333;
  font-size: 1em;
  flex-shrink: 0;
}

.query-input {
  flex: 1;
  min-width: 220px;
  padding: 8px 12px;
  font-size: 15px;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  outline: none;
}
.query-input:focus {
  border-color: #1890ff;
}
.query-input:disabled {
  background: #fafafa;
  cursor: not-allowed;
}

.nature-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.nature-btn {
  padding: 8px 20px;
  font-weight: 500;
  font-size: 15px;
  border: 2px solid #d9d9d9;
  border-radius: 6px;
  background: #fafafa;
  cursor: pointer;
}
.nature-btn:hover:not(:disabled) {
  border-color: #52c41a;
  color: #389e0d;
}
.nature-btn.active {
  background: #52c41a;
  border-color: #52c41a;
  color: #fff;
}
.nature-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.burden-area {
  flex: 1;
  min-width: 100%;
  box-sizing: border-box;
  padding: 10px;
  font-family: inherit;
  font-size: 14px;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  min-height: 80px;
  max-height: 600px;
  overflow-y: auto;
  resize: none;
  outline: none;
}
.burden-area:focus {
  border-color: #1890ff;
}
.burden-area:disabled {
  background: #fafafa;
  cursor: not-allowed;
}

.action-row {
  margin-top: 4px;
  padding: 12px 0;
  border-top: 1px solid #f0f0f0;
  display: flex;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 24px;
  font-size: 16px;
  border-radius: 6px;
  border: none;
  background: #1890ff;
  color: #fff;
  cursor: pointer;
}
.action-btn .btn-icon {
  font-size: 18px;
}
.action-btn .btn-spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.action-btn:hover:not(:disabled) {
  background: #40a9ff;
}
.action-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.loading-hint {
  margin: 8px 0 0;
  color: #8c8c8c;
  font-size: 0.9em;
  text-align: center;
}

.error {
  margin-top: 12px;
  color: #cf1322;
  font-size: 0.95em;
}

.result-card {
  margin-top: 20px;
}

.result-card :deep(.ant-card-head) {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}

.result-head-actions {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.copy-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: 13px;
  border-radius: 4px;
  border: 1px solid #d9d9d9;
  background: #fff;
  cursor: pointer;
  color: #555;
}
.copy-btn:hover {
  color: #1890ff;
  border-color: #1890ff;
}

.format-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: 13px;
  border-radius: 4px;
  border: 1px solid #52c41a;
  background: #fff;
  color: #389e0d;
  cursor: pointer;
}
.format-btn:hover:not(:disabled) {
  background: #52c41a;
  color: #fff;
}
.format-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.concepts-box {
  margin-bottom: 14px;
  padding: 10px 12px;
  background: #f5f5f5;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.7;
  color: #595959;
}
.concepts-title {
  font-weight: 600;
  color: #434343;
  margin-bottom: 4px;
}
.concepts-line {
  word-break: break-word;
}

.result-body {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-size: 0.95em;
  line-height: 1.6;
  max-height: 60vh;
  overflow-y: auto;
  tab-size: 4;
  -moz-tab-size: 4;
}

.chunks-section {
  margin-top: 16px;
  border-top: 1px solid #f0f0f0;
  padding-top: 12px;
}
.chunks-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  font-weight: 600;
  color: #333;
}
.toggle-btn {
  padding: 4px 12px;
  font-size: 13px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: #fff;
  color: #555;
  cursor: pointer;
}
.toggle-btn:hover {
  color: #1890ff;
  border-color: #1890ff;
}
.chunks-list {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
}
.chunk-item {
  padding: 10px 0;
  border-bottom: 1px solid #f0f0f0;
}
.chunk-item:last-child {
  border-bottom: none;
}
.chunk-route3 {
  background: #e6f4ff;
  border-bottom: 1px solid #d6e8fb;
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 6px;
}
.chunk-meta {
  position: relative;
  color: #555;
  font-size: 0.82em;
  font-weight: 700;
  margin-bottom: 6px;
  padding: 4px 8px;
  background: #e6f4ff;
  border-radius: 4px;
  display: inline-block;
}
.chunk-route3 .chunk-meta {
  background: #bae0ff;
}
.chunk-expanded-from {
  margin-left: 8px;
  padding: 1px 6px;
  font-size: 0.92em;
  font-weight: 600;
  color: #0958d9;
  background: #fff;
  border: 1px solid #91caff;
  border-radius: 10px;
}
.chunk-text {
  color: #333;
  font-size: 0.92em;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.analyze-result { background: #f5f5f5; border-radius: 8px; padding: 12px; margin: 12px 0; }
.concept-row { margin-bottom: 8px; display: flex; flex-wrap: nowrap; align-items: flex-start; }
.layer-label { font-size: 15px; font-weight: bold; color: #555; min-width: 70px; flex-shrink: 0; padding-top: 3px; }
.concept-tags-wrap { display: flex; flex-wrap: wrap; gap: 6px; flex: 1; }
.concept-tag { border: 1px solid #d0d0d0; border-radius: 12px; padding: 2px 8px; font-size: 14px; display: inline-flex; align-items: center; gap: 4px; }
.tag-revelation { background: #E8F4FD; }
.tag-experience { background: #E8F8F0; }
.tag-practice   { background: #FEF3E8; }
.remove-btn { cursor: pointer; color: #999; font-size: 14px; }
.remove-btn:hover { color: #f00; }
.add-btn { cursor: pointer; color: #1890ff; font-size: 12px; border: 1px dashed #1890ff; border-radius: 12px; padding: 2px 8px; }
.add-input { border: 1px solid #1890ff; border-radius: 8px; padding: 2px 6px; font-size: 12px; width: 80px; }
.confirm-btn { cursor: pointer; color: #fff; background: #1890ff; border-radius: 8px; padding: 2px 8px; font-size: 12px; }
.rewrite-section { margin-top: 10px; border-top: 1px solid #e0e0e0; padding-top: 8px; }
.rewrite-title { font-size: 13px; font-weight: bold; color: #555; margin-bottom: 6px; }
.rewrite-item { font-size: 12px; color: #666; line-height: 1.8; }
.action-row { display: flex; gap: 12px; margin-top: 12px; }
.reset-btn { padding: 8px 20px; font-size: 15px; border-radius: 6px; border: 1px solid #d9d9d9; background: #fff; color: #555; cursor: pointer; }
.reset-btn:hover { border-color: #1890ff; color: #1890ff; }

.candidates-box { background: #fff7e6; border-radius: 8px; padding: 10px; margin-bottom: 8px; }
.candidate-item { padding: 8px; border-radius: 6px; cursor: pointer; margin-bottom: 6px; border: 1px solid #ffd591; font-size: 13px; line-height: 1.6; }
.candidate-item.selected { background: #ffe7ba; border-color: #ffa940; }
.candidate-label { font-weight: bold; margin-right: 6px; color: #d46b08; }

.skeleton-info { margin-bottom: 12px; }
.skeleton-header { padding: 6px 12px; border-radius: 6px; font-size: 13px; font-weight: bold; margin-bottom: 6px; }
.has-skeleton { background: #e6f4ff; color: #1677ff; }
.no-skeleton { background: #fff7e6; color: #d46b08; }
.skeleton-steps { background: #f6ffed; border-radius: 6px; padding: 8px 12px; }
.skeleton-step { font-size: 12px; color: #389e0d; line-height: 1.8; }
</style>

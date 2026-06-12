<script setup>
import { ref, computed, nextTick } from "vue";
import { ArrowLeftOutlined } from "@ant-design/icons-vue";
import { toastSuccess, toastWarning } from "../utils/Dialog";

const goToolbox = () => {
  window.location.hash = "/tools";
};

const questionInput = ref("");
const questionTextarea = ref(null);
const answerPanel = ref(null);
const loading = ref(false);
const error = ref(null);
const autoFollow = ref(true);

const chainExpanded = ref(true);
const rewrittenQuery = ref("");
const surfaceConcepts = ref([]);
const deepConcepts = ref([]);
const rerankCount = ref(null);
const filteredCount = ref(null);

const answerText = ref("");
const found = ref(null);
const elapsedMs = ref(null);

const LINE_HEIGHT = 22;
const INPUT_MAX_LINES = 5;
const SCROLL_BOTTOM_THRESHOLD = 60;

const canAsk = computed(
  () => !!questionInput.value.trim() && !loading.value
);

const showCursor = computed(() => loading.value && found.value !== false);

const showGenerating = computed(
  () => loading.value && !answerText.value && found.value !== false
);

const showIdlePlaceholder = computed(
  () => !answerText.value && found.value !== false && !showGenerating.value
);

const statsLine = computed(() => {
  if (rerankCount.value == null) return "";
  const n = rerankCount.value;
  const m = filteredCount.value != null ? filteredCount.value : "—";
  return `精排 ${n} 条 → 过滤后 ${m} 条`;
});

const elapsedSec = computed(() => {
  if (elapsedMs.value == null) return "";
  return `${(elapsedMs.value / 1000).toFixed(1)} 秒`;
});

const formattedAnswer = computed(() => {
  const text = answerText.value || "";
  if (!text) return { blocks: [], bib: "" };
  const bibIdx = text.indexOf("【引用书目】");
  const body = bibIdx >= 0 ? text.slice(0, bibIdx).trimEnd() : text;
  const bib = bibIdx >= 0 ? text.slice(bibIdx).trim() : "";
  const lines = body.split("\n");
  const blocks = lines.map((line) => {
    const trimmed = line.trimEnd();
    if (trimmed.startsWith("## ")) {
      return { kind: "h2", text: trimmed.replace(/^##\s+/, "") };
    }
    if (trimmed.includes("【核心要点】")) {
      return { kind: "highlight", text: trimmed };
    }
    if (trimmed.startsWith("**") && trimmed.endsWith("**")) {
      return { kind: "subhead", text: trimmed.replace(/^\*\*|\*\*$/g, "") };
    }
    return { kind: "p", text: trimmed };
  });
  return { blocks, bib };
});

function isNearBottom(el) {
  if (!el) return true;
  return el.scrollHeight - el.scrollTop - el.clientHeight <= SCROLL_BOTTOM_THRESHOLD;
}

function onAnswerScroll() {
  const el = answerPanel.value;
  if (!el || !loading.value) return;
  autoFollow.value = isNearBottom(el);
}

function scrollAnswerToBottom() {
  nextTick(() => {
    const el = answerPanel.value;
    if (!el || !autoFollow.value) return;
    el.scrollTop = el.scrollHeight;
  });
}

function scrollAnswerToTop() {
  nextTick(() => {
    const el = answerPanel.value;
    if (el) el.scrollTop = 0;
  });
}

function adjustHeight(el) {
  const target = el?.target || el;
  if (!target) return;
  target.style.height = "auto";
  const scrollH = target.scrollHeight;
  const maxH = LINE_HEIGHT * INPUT_MAX_LINES + 16;
  target.style.height = `${Math.min(scrollH, maxH)}px`;
  target.style.overflowY = scrollH > maxH ? "auto" : "hidden";
}

function onInputGrow(event) {
  adjustHeight(event);
}

function resizeQuestionInput() {
  nextTick(() => {
    if (questionTextarea.value) adjustHeight(questionTextarea.value);
  });
}

function resetChain() {
  rewrittenQuery.value = "";
  surfaceConcepts.value = [];
  deepConcepts.value = [];
  rerankCount.value = null;
  filteredCount.value = null;
}

function clearAll() {
  questionInput.value = "";
  resetChain();
  answerText.value = "";
  found.value = null;
  elapsedMs.value = null;
  error.value = null;
  chainExpanded.value = true;
  autoFollow.value = true;
  resizeQuestionInput();
  scrollAnswerToTop();
}

function handleStreamEvent(ev) {
  const type = ev.type;
  if (type === "step") {
    const stage = ev.stage;
    const data = ev.data || {};
    if (stage === "step1") {
      rewrittenQuery.value = data.rewritten_query || "";
      surfaceConcepts.value = Array.isArray(data.surface) ? data.surface : [];
      deepConcepts.value = Array.isArray(data.deep) ? data.deep : [];
    } else if (stage === "step2") {
      rerankCount.value = data.passage_count ?? 0;
    } else if (stage === "step3") {
      const relevant = data.relevant !== false;
      filteredCount.value = relevant ? (rerankCount.value ?? 0) : 0;
    }
  } else if (type === "token") {
    answerText.value += ev.text || "";
    scrollAnswerToBottom();
  } else if (type === "done") {
    found.value = !!ev.found;
    elapsedMs.value = ev.elapsed_ms ?? null;
    if (ev.answer && !answerText.value) {
      answerText.value = ev.answer;
    }
    if (!ev.found) {
      answerText.value = "";
    }
    loading.value = false;
    scrollAnswerToBottom();
  } else if (type === "error") {
    error.value = ev.message || ev.text || "请求失败";
    loading.value = false;
  }
}

async function askQuestion() {
  const q = questionInput.value.trim();
  if (!q || loading.value) return;

  loading.value = true;
  error.value = null;
  answerText.value = "";
  found.value = null;
  elapsedMs.value = null;
  resetChain();
  autoFollow.value = true;
  scrollAnswerToTop();

  try {
    const res = await fetch("/api/testb/qa/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `请求失败 (${res.status})`);
    }
    if (!res.body) throw new Error("无响应流");

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n");
      buffer = parts.pop() || "";
      for (const line of parts) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data:")) continue;
        try {
          const payload = JSON.parse(trimmed.slice(5).trim());
          handleStreamEvent(payload);
        } catch {
          /* ignore malformed chunk */
        }
      }
    }
    if (buffer.trim().startsWith("data:")) {
      try {
        const payload = JSON.parse(buffer.trim().slice(5).trim());
        handleStreamEvent(payload);
      } catch {
        /* ignore */
      }
    }
  } catch (err) {
    error.value = err.message || "网络错误";
  } finally {
    loading.value = false;
  }
}

function onQuestionKeydown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    askQuestion();
  }
}

function copyAnswer() {
  let text = answerText.value || "";
  const idx = text.indexOf("【引用书目】");
  if (idx >= 0) text = text.slice(0, idx).trimEnd();
  if (!text.trim()) {
    toastWarning("没有可复制的内容");
    return;
  }
  navigator.clipboard
    .writeText(text)
    .then(() => toastSuccess("已复制答案"))
    .catch(() => toastWarning("复制失败"));
}
</script>

<template>
  <div class="mq-page">
    <div class="mq-header">
      <div class="back-btn" title="返回工具箱" @click="goToolbox">
        <ArrowLeftOutlined />
        <span>返回</span>
      </div>
      <h1 class="page-title">职事问答测试</h1>
    </div>

    <div class="chain-panel">
      <div class="chain-head" @click="chainExpanded = !chainExpanded">
        <span class="chain-title">链路信息</span>
        <span class="chain-toggle">{{ chainExpanded ? "收起" : "展开" }}</span>
      </div>
      <div v-show="chainExpanded" class="chain-body">
        <div v-if="rewrittenQuery" class="chain-row">
          <span class="chain-label">改写问题</span>
          <span class="chain-value">{{ rewrittenQuery }}</span>
        </div>
        <div
          v-if="surfaceConcepts.length || deepConcepts.length"
          class="tag-row"
        >
          <span
            v-for="c in surfaceConcepts"
            :key="'s-' + c"
            class="tag tag-surface"
          >{{ c }}</span>
          <span
            v-for="c in deepConcepts"
            :key="'d-' + c"
            class="tag tag-deep"
          >{{ c }}</span>
        </div>
        <div v-if="statsLine" class="chain-stats">{{ statsLine }}</div>
        <div
          v-if="!rewrittenQuery && !statsLine && !loading"
          class="chain-empty"
        >
          提问后将显示检索链路
        </div>
      </div>
    </div>

    <div ref="answerPanel" class="answer-panel" @scroll="onAnswerScroll">
      <div
        class="answer-inner"
        :class="{ 'answer-inner--idle': showIdlePlaceholder }"
      >
        <div v-if="found === false" class="not-found">
          未能在职事信息中找到相关依据
        </div>
        <div v-else-if="formattedAnswer.blocks?.length" class="answer-body">
          <template v-for="(block, i) in formattedAnswer.blocks" :key="i">
            <div v-if="block.text" :class="'ab-' + block.kind">
              {{ block.text }}
            </div>
          </template>
          <div v-if="formattedAnswer.bib" class="ab-bib">
            <hr class="bib-sep" />
            <pre class="bib-text">{{ formattedAnswer.bib }}</pre>
          </div>
          <span v-if="showCursor" class="cursor">|</span>
        </div>
        <div v-else-if="showGenerating" class="answer-wait">
          正在生成答案…<span class="cursor">|</span>
        </div>
        <div v-else-if="showIdlePlaceholder" class="answer-placeholder">
          在下方输入问题开始提问
        </div>
      </div>
    </div>

    <div v-if="error" class="error-bar">{{ error }}</div>

    <div class="info-bar">
      <span class="elapsed">{{ elapsedSec ? `耗时 ${elapsedSec}` : "" }}</span>
      <div class="info-actions">
        <button type="button" class="ghost-btn" @click="copyAnswer">复制答案</button>
        <button type="button" class="ghost-btn" @click="clearAll">清空</button>
      </div>
    </div>

    <div class="input-bar">
      <textarea
        ref="questionTextarea"
        v-model="questionInput"
        class="question-input"
        placeholder="输入问题，Enter 提问，Shift+Enter 换行"
        rows="1"
        :disabled="loading"
        @input="onInputGrow"
        @keydown="onQuestionKeydown"
      />
      <button
        type="button"
        class="ask-btn"
        :disabled="!canAsk"
        @click="askQuestion"
      >
        {{ loading ? "回答中…" : "提问" }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.mq-page {
  height: 100vh;
  max-width: 820px;
  margin: 0 auto;
  padding: 12px 16px;
  color: #312e81;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.mq-header {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
  margin-bottom: 8px;
}

.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border-radius: 6px;
  border: 1px solid #c7d2fe;
  background: #eef2ff;
  color: #312e81;
  cursor: pointer;
  font-size: 14px;
  flex-shrink: 0;
}

.back-btn:hover {
  background: #e0e7ff;
  border-color: #a5b4fc;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #312e81;
}

.chain-panel {
  background: #eef2ff;
  border-radius: 10px;
  flex-shrink: 0;
  max-height: 30vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  margin-bottom: 8px;
}

.chain-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
  flex-shrink: 0;
}

.chain-title {
  font-weight: 600;
  font-size: 14px;
}

.chain-toggle {
  font-size: 13px;
  color: #4f46e5;
}

.chain-body {
  padding: 0 14px 12px;
  overflow-y: auto;
  min-height: 0;
}

.chain-row {
  margin-bottom: 8px;
  font-size: 14px;
  line-height: 1.5;
}

.chain-label {
  color: #6366f1;
  margin-right: 8px;
  font-weight: 600;
}

.chain-value {
  word-break: break-word;
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 13px;
}

.tag-surface {
  background: #4f46e5;
  color: #fff;
}

.tag-deep {
  background: #c7d2fe;
  color: #312e81;
}

.chain-stats {
  font-size: 13px;
  color: #4338ca;
}

.chain-empty {
  font-size: 13px;
  color: #818cf8;
}

.answer-panel {
  flex: 1;
  min-height: 0;
  border: 1px solid #c7d2fe;
  border-radius: 10px;
  background: #fff;
  overflow-y: auto;
  margin-bottom: 8px;
}

.answer-inner {
  padding: 16px;
  line-height: 1.7;
  font-size: 15px;
  min-height: min-content;
}

.answer-inner--idle {
  min-height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.not-found {
  background: #fef2f2;
  color: #b91c1c;
  padding: 16px;
  border-radius: 8px;
  text-align: center;
  width: 100%;
}

.answer-placeholder {
  color: #c7d2fe;
  font-size: 14px;
  text-align: center;
}

.answer-wait {
  color: #a5b4fc;
  font-size: 14px;
  width: 100%;
}

.ab-h2 {
  font-size: 18px;
  font-weight: 700;
  margin: 12px 0 8px;
  color: #312e81;
}

.ab-highlight {
  background: #eef2ff;
  border-left: 3px solid #4f46e5;
  padding: 8px 10px;
  margin: 8px 0;
  border-radius: 0 6px 6px 0;
  font-weight: 500;
}

.ab-subhead {
  font-weight: 600;
  margin: 10px 0 4px;
  color: #3730a3;
}

.ab-p {
  margin: 4px 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.bib-sep {
  border: none;
  border-top: 1px solid #e5e7eb;
  margin: 16px 0 8px;
}

.bib-text {
  font-size: 12px;
  color: #6b7280;
  white-space: pre-wrap;
  margin: 0;
  font-family: inherit;
}

.cursor {
  display: inline-block;
  animation: blink 1s step-end infinite;
  color: #4f46e5;
  font-weight: 300;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.error-bar {
  color: #b91c1c;
  font-size: 14px;
  margin-bottom: 6px;
  flex-shrink: 0;
}

.info-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  min-height: 32px;
  flex-shrink: 0;
}

.elapsed {
  font-size: 13px;
  color: #6366f1;
}

.info-actions {
  display: flex;
  gap: 8px;
}

.ghost-btn {
  padding: 4px 12px;
  border-radius: 6px;
  border: 1px solid #c7d2fe;
  background: #eef2ff;
  color: #312e81;
  cursor: pointer;
  font-size: 13px;
}

.ghost-btn:hover {
  background: #e0e7ff;
}

.input-bar {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  border: 1px solid #4f46e5;
  border-radius: 12px;
  padding: 10px 12px;
  background: #fff;
  flex-shrink: 0;
}

.question-input {
  flex: 1;
  border: none;
  outline: none;
  resize: none;
  font-size: 15px;
  line-height: 22px;
  color: #312e81;
  background: transparent;
  min-height: 22px;
  max-height: 126px;
  font-family: inherit;
}

.ask-btn {
  flex-shrink: 0;
  padding: 8px 20px;
  border: none;
  border-radius: 8px;
  background: #4f46e5;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.ask-btn:disabled {
  background: #a5b4fc;
  cursor: not-allowed;
}
</style>

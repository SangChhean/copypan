<script setup>
import { ref, nextTick, onMounted, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { LeftOutlined } from "@ant-design/icons-vue";

const router = useRouter();
const toast = ref("");
const inputQuestion = ref("");
const loading = ref(false);
const messages = ref([]);
const chatRef = ref(null);

const REF_RE = /\[(\d+)\]/g;

function showToast(msg) {
  toast.value = msg;
  setTimeout(() => { if (toast.value === msg) toast.value = ""; }, 2500);
}

function formatError(data, status) {
  if (!data) return `请求失败（HTTP ${status}）`;
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail.map((d) => d.msg || JSON.stringify(d)).join("；");
  }
  return data.message || JSON.stringify(data);
}

function parseAnswerSegments(text) {
  if (!text) return [];
  const segments = [];
  let lastIndex = 0;
  let m;
  const re = /\[(\d+)\]/g;
  while ((m = re.exec(text)) !== null) {
    if (m.index > lastIndex) {
      segments.push({ type: "text", content: text.slice(lastIndex, m.index) });
    }
    segments.push({ type: "ref", num: parseInt(m[1], 10), label: m[0] });
    lastIndex = re.lastIndex;
  }
  if (lastIndex < text.length) {
    segments.push({ type: "text", content: text.slice(lastIndex) });
  }
  return segments;
}

function getSourceText(msg, num) {
  const src = msg.sources?.[num - 1];
  return src ? src : "无出处信息";
}

function closeAllRefs() {
  for (let i = 0; i < messages.value.length; i++) {
    const msg = messages.value[i];
    if (msg && msg.openRef != null) {
      messages.value[i].openRef = null;
    }
  }
}

function toggleRef(msgIdx, refNum, event) {
  event.stopPropagation();
  const msg = messages.value[msgIdx];
  const next = msg.openRef === refNum ? null : refNum;
  messages.value[msgIdx].openRef = next;
}

async function scrollToBottom() {
  await nextTick();
  const el = chatRef.value;
  if (el) el.scrollTop = el.scrollHeight;
}

function copyAnswer(text) {
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => showToast("已复制到剪贴板"));
}

async function ask() {
  const question = inputQuestion.value.trim();
  if (!question) {
    showToast("请输入问题");
    return;
  }
  if (loading.value) return;

  const idx = messages.value.length;
  messages.value.push({ question, pending: true });
  inputQuestion.value = "";
  loading.value = true;
  await scrollToBottom();

  const start = performance.now();
  try {
    const res = await fetch("/api/testa/qa_simple/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json().catch(() => ({}));
    const elapsed = (performance.now() - start) / 1000;

    if (!res.ok) {
      messages.value[idx] = {
        question,
        pending: false,
        error: formatError(data, res.status),
        elapsed,
      };
    } else {
      const answer = data.answer || "";
      const entry = {
        question,
        pending: false,
        answer,
        segments: parseAnswerSegments(answer),
        sourcesCount: data.sources_count ?? 0,
        sources: [],
        openRef: null,
        elapsed,
      };
      const rawSources = Array.isArray(data.sources) ? data.sources : [];
      for (let i = 0; i < rawSources.length; i++) {
        entry.sources[i] = rawSources[i];
      }
      messages.value[idx] = entry;
    }
  } catch (e) {
    messages.value[idx] = {
      question,
      pending: false,
      error: e.message || "网络请求失败",
      elapsed: (performance.now() - start) / 1000,
    };
  } finally {
    loading.value = false;
    await scrollToBottom();
  }
}

function onKeydown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    ask();
  }
}

onMounted(() => document.addEventListener("click", closeAllRefs));
onUnmounted(() => document.removeEventListener("click", closeAllRefs));
</script>

<template>
  <div class="page">
    <div v-if="toast" class="toast">{{ toast }}</div>

    <div class="header">
      <a-button type="text" class="back-btn" @click="router.back()">
        <template #icon><LeftOutlined /></template>
      </a-button>
      <span class="header-title">QA 问答</span>
    </div>

    <div ref="chatRef" class="chat-area">
      <div v-if="messages.length === 0" class="chat-empty">
        输入问题开始对话，将基于职事文献检索作答。
      </div>

      <div v-for="(msg, idx) in messages" :key="idx" class="turn">
        <div class="question-row">
          <div class="question-bubble">{{ msg.question }}</div>
        </div>

        <div v-if="msg.pending" class="answer-row">
          <div class="answer-pending">回答中...</div>
        </div>

        <div v-else-if="msg.error" class="answer-row">
          <div class="answer-error">{{ msg.error }}</div>
          <div v-if="msg.elapsed != null" class="answer-meta">
            耗时 {{ msg.elapsed.toFixed(1) }} 秒
          </div>
        </div>

        <div v-else class="answer-row">
          <div class="answer-card">
            <button type="button" class="copy-btn" @click="copyAnswer(msg.answer)">
              复制
            </button>
            <div class="answer-body">
              <template v-for="(seg, si) in msg.segments" :key="si">
                <span v-if="seg.type === 'text'" class="answer-text">{{ seg.content }}</span>
                <span v-else class="ref-wrap">
                  <button
                    type="button"
                    class="ref-btn"
                    :class="{ active: msg.openRef === seg.num }"
                    @click="toggleRef(idx, seg.num, $event)"
                  >
                    {{ seg.label }}
                  </button>
                  <div
                    v-if="msg.openRef === seg.num"
                    class="ref-popover"
                    @click.stop
                  >
                    {{ getSourceText(msg, seg.num) }}
                  </div>
                </span>
              </template>
            </div>
            <div class="answer-meta">
              耗时 {{ msg.elapsed.toFixed(1) }} 秒 · 参考了 {{ msg.sourcesCount }} 条段落
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="input-bar">
      <a-input
        v-model:value="inputQuestion"
        placeholder="输入你的问题…"
        :disabled="loading"
        class="question-input"
        @keydown="onKeydown"
      />
      <a-button
        type="primary"
        class="ask-btn"
        :disabled="loading"
        @click="ask"
      >
        {{ loading ? "回答中..." : "提问" }}
      </a-button>
    </div>
  </div>
</template>

<style scoped>
.toast {
  position: fixed;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: #3f51b5;
  color: #fff;
  padding: 8px 24px;
  border-radius: 20px;
  font-size: 14px;
  z-index: 9999;
  pointer-events: none;
}
.page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f5f5;
}
.header {
  background: linear-gradient(135deg, #303f9f 0%, #5c6bc0 100%);
  padding: 0 20px;
  height: 52px;
  display: flex;
  align-items: center;
  position: relative;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(63, 81, 181, 0.35);
}
.back-btn {
  color: #c5cae9;
  font-size: 18px;
  position: absolute;
  left: 12px;
}
.header-title {
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  flex: 1;
  text-align: center;
  letter-spacing: 0.5px;
}
.chat-area {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  padding-bottom: 8px;
}
.chat-empty {
  text-align: center;
  color: #8c8c8c;
  font-size: 14px;
  margin-top: 40px;
  line-height: 1.6;
}
.turn {
  margin-bottom: 20px;
}
.question-row {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 10px;
}
.question-bubble {
  max-width: 85%;
  background: #e8eaf6;
  color: #1a237e;
  border: 1px solid #c5cae9;
  border-radius: 12px 12px 4px 12px;
  padding: 10px 14px;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.answer-row {
  display: flex;
  justify-content: flex-start;
}
.answer-card {
  position: relative;
  max-width: 92%;
  background: #fff;
  border-radius: 12px 12px 12px 4px;
  padding: 12px 14px 10px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  border: 1px solid #e8eaf6;
}
.copy-btn {
  position: absolute;
  top: 8px;
  right: 10px;
  border: 1px solid #c5cae9;
  background: #fff;
  color: #3f51b5;
  border-radius: 4px;
  font-size: 12px;
  padding: 2px 10px;
  cursor: pointer;
}
.copy-btn:hover {
  background: #e8eaf6;
}
.answer-body {
  font-size: 14px;
  line-height: 1.7;
  color: #333;
  word-break: break-word;
  padding-right: 48px;
}
.answer-text {
  white-space: pre-wrap;
}
.ref-wrap {
  position: relative;
  display: inline;
}
.ref-btn {
  display: inline;
  margin: 0 1px;
  padding: 0 4px;
  border: 1px solid #3f51b5;
  border-radius: 4px;
  background: #e8eaf6;
  color: #303f9f;
  font-size: 12px;
  line-height: 1.4;
  cursor: pointer;
  vertical-align: baseline;
}
.ref-btn:hover,
.ref-btn.active {
  background: #c5cae9;
}
.ref-popover {
  position: absolute;
  left: 0;
  bottom: calc(100% + 6px);
  z-index: 100;
  min-width: 180px;
  max-width: 320px;
  padding: 8px 10px;
  background: #fff;
  border: 1px solid #c5cae9;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(63, 81, 181, 0.18);
  font-size: 12px;
  line-height: 1.5;
  color: #333;
  white-space: normal;
  word-break: break-word;
}
.answer-meta {
  margin-top: 10px;
  font-size: 12px;
  color: #8c8c8c;
}
.answer-pending {
  background: #fff;
  border: 1px dashed #c5cae9;
  border-radius: 12px;
  padding: 12px 16px;
  color: #5c6bc0;
  font-size: 14px;
}
.answer-error {
  background: #fff1f0;
  border: 1px solid #ffa39e;
  border-radius: 12px;
  padding: 12px 16px;
  color: #cf1322;
  font-size: 14px;
  line-height: 1.6;
  max-width: 92%;
}
.input-bar {
  flex-shrink: 0;
  display: flex;
  gap: 10px;
  padding: 12px 16px 20px;
  background: #fff;
  border-top: 1px solid #e8e8e8;
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.04);
}
.question-input {
  flex: 1;
}
.ask-btn {
  background: #3f51b5;
  border-color: #3f51b5;
  min-width: 88px;
}
.ask-btn:hover,
.ask-btn:focus {
  background: #303f9f !important;
  border-color: #303f9f !important;
}
</style>

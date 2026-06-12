<template>
  <div class="qa-practice-wrap">
    <ToolsHeader />

    <div class="page-body">
      <header class="page-header">
        <h1 class="page-title">职事信息问答练习</h1>
        <p class="page-subtitle">
          基于职事文献的检索问答 · 四步流水线（概念抽取 → 混合检索 → 相关性判断 → 答案生成）
        </p>
      </header>

      <section class="ask-section">
        <textarea
          v-model="question"
          class="question-input"
          rows="3"
          placeholder="输入职事问题，如：什么是神圣的生命？"
          :disabled="loading"
          @keydown.ctrl.enter.prevent="submit"
        />
        <button
          type="button"
          class="submit-btn"
          :disabled="loading || !question.trim()"
          @click="submit"
        >
          {{ loading ? "查考职事信息中…" : "提问" }}
        </button>
      </section>

      <section v-if="result" class="pipeline-card">
        <div class="pipeline-row">
          <span class="pipeline-label">检索句</span>
          <span class="pipeline-value">{{ result.rewritten_query }}</span>
        </div>
        <div v-if="result.surface_concepts?.length" class="pipeline-row">
          <span class="pipeline-label">字面概念</span>
          <span class="tag-list">
            <span
              v-for="c in result.surface_concepts"
              :key="'s-' + c"
              class="concept-tag concept-tag--surface"
            >{{ c }}</span>
          </span>
        </div>
        <div v-if="result.deep_concepts?.length" class="pipeline-row">
          <span class="pipeline-label">内在概念</span>
          <span class="tag-list">
            <span
              v-for="c in result.deep_concepts"
              :key="'d-' + c"
              class="concept-tag concept-tag--deep"
            >{{ c }}</span>
          </span>
        </div>
        <p v-if="result.relevant === false" class="relevance-warn">
          检索结果与问题相关性不足，未进入答案生成
        </p>
      </section>

      <section v-if="result?.answer" class="answer-card">
        <pre class="answer-text">{{ result.answer }}</pre>
      </section>

      <section v-if="result?.sources?.length" class="sources-section">
        <button
          type="button"
          class="sources-toggle"
          @click="sourcesOpen = !sourcesOpen"
        >
          参考段落（{{ result.sources_count }} 条）{{ sourcesOpen ? "▴" : "▾" }}
        </button>
        <div v-show="sourcesOpen" class="sources-list">
          <div
            v-for="src in result.sources"
            :key="src.index"
            class="source-item"
          >
            <div class="source-ref">[{{ src.index }}] {{ src.source_zh }}</div>
            <div class="source-preview">{{ src.preview }}</div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue"
import axios from "axios"
import { message } from "ant-design-vue"
import ToolsHeader from "./ToolsHeader.vue"

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || ""

const question = ref("")
const loading = ref(false)
const result = ref(null)
const sourcesOpen = ref(false)

async function submit() {
  const q = question.value.trim()
  if (!q || loading.value) return

  loading.value = true
  result.value = null
  sourcesOpen.value = false

  try {
    const res = await axios.post(
      `${apiBase}/api/testc/qa/query`,
      { question: q },
      { timeout: 120000 },
    )
    result.value = res.data
  } catch {
    message.error("提问失败，请检查后端服务是否运行")
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.qa-practice-wrap {
  min-height: 100vh;
  background: #f7f5f0;
}

.page-body {
  max-width: 880px;
  margin: 0 auto;
  padding: 0 28px 48px;
}

.page-header {
  margin-bottom: 32px;
}

.page-title {
  margin: 0 0 10px;
  font-size: 28px;
  font-weight: 600;
  color: #2c5f8a;
  letter-spacing: 0.02em;
}

.page-subtitle {
  margin: 0;
  font-size: 14px;
  color: #7a7268;
  line-height: 1.6;
}

.ask-section {
  margin-bottom: 28px;
}

.question-input {
  display: block;
  width: 100%;
  box-sizing: border-box;
  padding: 14px 16px;
  font-size: 17px;
  line-height: 1.6;
  color: #333;
  background: #fff;
  border: 1px solid #d4cfc6;
  border-radius: 8px;
  resize: vertical;
  font-family: inherit;
}

.question-input:focus {
  outline: none;
  border-color: #2c5f8a;
  box-shadow: 0 0 0 2px rgba(44, 95, 138, 0.15);
}

.question-input:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.submit-btn {
  margin-top: 14px;
  padding: 12px 32px;
  font-size: 17px;
  font-weight: 500;
  color: #fff;
  background: #2c5f8a;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
}

.submit-btn:hover:not(:disabled) {
  background: #234a6e;
}

.submit-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.pipeline-card {
  margin-bottom: 24px;
  padding: 20px 22px;
  background: #edeae3;
  border-radius: 10px;
  border: 1px solid #ddd8ce;
}

.pipeline-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 10px 14px;
  margin-bottom: 14px;
}

.pipeline-row:last-of-type {
  margin-bottom: 0;
}

.pipeline-label {
  flex-shrink: 0;
  font-size: 14px;
  font-weight: 600;
  color: #5c5348;
  min-width: 72px;
}

.pipeline-value {
  flex: 1;
  font-size: 16px;
  line-height: 1.65;
  color: #333;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.concept-tag {
  display: inline-block;
  padding: 4px 12px;
  font-size: 14px;
  border-radius: 16px;
  border: 1px solid #2c5f8a;
  color: #2c5f8a;
  background: #fff;
}

.concept-tag--deep {
  border-color: #6a9bc4;
  color: #4a7a9e;
  background: #f9f8f5;
}

.relevance-warn {
  margin: 16px 0 0;
  padding: 10px 14px;
  font-size: 15px;
  color: #b45309;
  background: #fff7ed;
  border-radius: 6px;
  border-left: 3px solid #f59e0b;
}

.answer-card {
  margin-bottom: 24px;
  padding: 24px 26px;
  background: #fff;
  border-radius: 10px;
  border: 1px solid #e8e4dc;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

.answer-text {
  margin: 0;
  font-size: 17px;
  line-height: 1.85;
  color: #2a2a2a;
  white-space: pre-wrap;
  font-family: inherit;
  word-break: break-word;
}

.sources-section {
  margin-bottom: 24px;
}

.sources-toggle {
  display: block;
  width: 100%;
  padding: 14px 18px;
  font-size: 16px;
  font-weight: 500;
  text-align: left;
  color: #2c5f8a;
  background: #edeae3;
  border: 1px solid #ddd8ce;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
}

.sources-toggle:hover {
  background: #e4e0d8;
}

.sources-list {
  margin-top: 8px;
  padding: 12px 16px;
  background: #fff;
  border: 1px solid #e8e4dc;
  border-radius: 8px;
}

.source-item {
  padding: 12px 0;
  border-bottom: 1px solid #f0ece6;
}

.source-item:last-child {
  border-bottom: none;
}

.source-ref {
  font-size: 14px;
  color: #2c5f8a;
  line-height: 1.5;
  margin-bottom: 4px;
}

.source-preview {
  font-size: 14px;
  color: #888;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>

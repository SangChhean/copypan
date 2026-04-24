<template>
  <div class="debug-root" :class="{ 'debug-root--embedded': embedded }">
    <header v-if="!embedded" class="debug-header">
      <div class="debug-header-inner">
        <a class="debug-back" href="#/">← 返回问答</a>
        <span class="debug-title">🔧 调试面板</span>
      </div>
    </header>

    <main class="debug-main">
      <div class="debug-layout">

        <!-- 左栏：参数控制 + 提问 -->
        <div class="debug-left">

          <!-- 检索参数 -->
          <section class="debug-section">
            <div class="debug-section-title">检索参数</div>
            <div class="debug-param-grid">
              <label>BM25 top_k
                <input type="number" v-model.number="params.bm25_top_k" min="1" max="100" />
              </label>
              <label>Dense top_k
                <input type="number" v-model.number="params.dense_top_k" min="1" max="100" />
              </label>
              <label>扩展路每概念 top_n
                <input type="number" v-model.number="params.expansion_top_n" min="1" max="20" />
              </label>
              <label>Rerank top_n
                <input type="number" v-model.number="params.rerank_top_n" min="1" max="50" />
              </label>
              <label class="full-width">
                <input type="checkbox" v-model="params.skip_cache" /> 跳过缓存
              </label>
            </div>
          </section>

          <!-- 提问 -->
          <section class="debug-section">
            <div class="debug-section-title">提问</div>
            <a-textarea
              v-model:value="question"
              :auto-size="{ minRows: 3, maxRows: 8 }"
              placeholder="输入问题..."
              :disabled="loading"
            />
            <a-button
              type="primary"
              :loading="loading"
              :disabled="!question.trim()"
              style="margin-top: 10px; width: 100%"
              @click="submit"
            >发送</a-button>
          </section>

          <!-- 基本信息 -->
          <section v-if="result && !result.error" class="debug-section">
            <div class="debug-section-title">基本信息</div>
            <div class="debug-info-grid">
              <div><span class="debug-label">found</span><span :class="result.found ? 'tag-ok' : 'tag-fail'">{{ result.found }}</span></div>
              <div><span class="debug-label">cache_hit</span><span :class="result.cache_hit ? 'tag-ok' : 'tag-gray'">{{ result.cache_hit }}</span></div>
              <div><span class="debug-label">耗时</span><span>{{ (result.total_elapsed_ms/1000).toFixed(1) }}s</span></div>
              <div><span class="debug-label">费用</span><span>${{ result.total_cost_usd }}</span></div>
            </div>
          </section>

          <section v-if="result?.error" class="debug-section">
            <div class="debug-section-title">请求错误</div>
            <pre class="debug-pre">{{ result.error }}</pre>
          </section>
        </div>

        <!-- 右栏：调试信息 -->
        <div class="debug-right">

          <!-- 定向查询 -->
          <section v-if="result && !result.error" class="debug-section">
            <div class="debug-section-title">定向查询预判</div>
            <pre class="debug-pre">{{ formatJson(result.debug?.targeted) }}</pre>
          </section>

          <!-- Surface / Deep -->
          <section v-if="result && !result.error" class="debug-section">
            <div class="debug-section-title">Step 1 概念抽取</div>
            <div class="debug-label">surface</div>
            <pre class="debug-pre">{{ formatJson(result.debug?.surface) }}</pre>
            <div class="debug-label" style="margin-top:8px">deep</div>
            <pre class="debug-pre">{{ formatJson(result.debug?.deep) }}</pre>
            <div class="debug-label" style="margin-top:8px">reasoning</div>
            <pre class="debug-pre">{{ result.debug?.reasoning || '—' }}</pre>
          </section>

          <!-- Firewall -->
          <section v-if="result && !result.error" class="debug-section">
            <div class="debug-section-title">防火墙</div>
            <pre class="debug-pre">{{ formatJson(result.debug?.firewall) }}</pre>
          </section>

          <!-- Step 4 Prompt -->
          <section v-if="result && !result.error" class="debug-section">
            <div class="debug-section-title">Step 4 Prompt（发送给 LLM 的完整内容）</div>
            <pre class="debug-pre debug-pre-scroll">{{ result.debug?.step4_prompt || '—' }}</pre>
          </section>

          <!-- 答案 -->
          <section v-if="result && !result.error" class="debug-section">
            <div class="debug-section-title">答案</div>
            <pre class="debug-pre debug-pre-scroll">{{ result.answer }}</pre>
          </section>

        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import axios from 'axios'

defineProps({
  embedded: {
    type: Boolean,
    default: false,
  },
})

const question = ref('')
const loading = ref(false)
const result = ref(null)

const params = ref({
  bm25_top_k: 30,
  dense_top_k: 30,
  expansion_top_n: 5,
  rerank_top_n: 20,
  skip_cache: true,
})

function formatJson(val) {
  if (val === null || val === undefined) return '—'
  if (typeof val === 'string') return val
  return JSON.stringify(val, null, 2)
}

async function submit() {
  if (!question.value.trim() || loading.value) return
  loading.value = true
  result.value = null
  try {
    const token = localStorage.getItem('qa_token') || ''
    const res = await axios.post(
      '/api/qa/query',
      {
        question: question.value.trim(),
        skip_cache: params.value.skip_cache,
        debug: true,
        params: {
          bm25_top_k: params.value.bm25_top_k,
          dense_top_k: params.value.dense_top_k,
          expansion_top_n: params.value.expansion_top_n,
          rerank_top_n: params.value.rerank_top_n,
        },
      },
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      },
    )
    result.value = res.data
  } catch (e) {
    result.value = { error: e.response?.data?.detail || '请求失败' }
  } finally {
    loading.value = false
  }
}
</script>

<style lang="less" scoped>
.debug-root {
  min-height: 100vh;
  background: #f0f0f0;
  font-family: 'Noto Sans SC', sans-serif;
}
.debug-root--embedded {
  min-height: auto;
  background: transparent;
}
.debug-root--embedded .debug-main {
  padding: 0;
  max-width: none;
  margin: 0;
}
.debug-root--embedded .debug-layout {
  grid-template-columns: 300px 1fr;
}

.debug-header {
  border-bottom: 1px solid #ddd;
  background: #1a1a2e;
  color: #fff;
}
.debug-header-inner {
  max-width: 1400px;
  margin: 0 auto;
  padding: 12px 24px;
  display: flex;
  align-items: center;
  gap: 16px;
}
.debug-back {
  font-size: 13px;
  color: #aaa;
  text-decoration: none;
  &:hover { color: #fff; }
}
.debug-title {
  font-size: 15px;
  font-weight: 600;
  color: #fff;
}

.debug-main {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.debug-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 16px;
  align-items: start;
}

.debug-section {
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 6px;
  padding: 16px;
  margin-bottom: 12px;
}
.debug-section-title {
  font-size: 12px;
  font-weight: 700;
  color: #555;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #eee;
}

.debug-param-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
  label {
    font-size: 12px;
    color: #555;
    display: flex;
    flex-direction: column;
    gap: 4px;
    input[type=number] {
      border: 1px solid #ddd;
      border-radius: 4px;
      padding: 4px 8px;
      font-size: 13px;
      width: 100%;
    }
  }
  .full-width {
    flex-direction: row;
    align-items: center;
    gap: 8px;
  }
}

.debug-info-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
  div {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
  }
}
.debug-label {
  font-size: 11px;
  color: #888;
  min-width: 70px;
}
.tag-ok { color: #389e0d; font-weight: 600; }
.tag-fail { color: #cf1322; font-weight: 600; }
.tag-gray { color: #888; }

.debug-pre {
  background: #f5f5f5;
  border: 1px solid #e8e8e8;
  border-radius: 4px;
  padding: 10px;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
.debug-pre-scroll {
  max-height: 400px;
  overflow-y: auto;
}
</style>

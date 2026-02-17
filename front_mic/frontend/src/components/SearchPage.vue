<template>
  <div class="search-page">
    <!-- 顶部导航栏 -->
    <header class="top-nav">
      <div class="nav-container">
        <div class="nav-logo">Pansearch</div>
        <nav class="nav-links">
          <a href="#/" class="nav-link" :class="{ active: route.path === '/' }">圣经</a>
          <a href="#/reading" class="nav-link">生命读经</a>
          <a href="#/search" class="nav-link active">搜索</a>
          <a href="#/tools" class="nav-link">工具箱</a>
        </nav>
        <div class="nav-actions">
          <a href="#/login" class="nav-btn">登录</a>
        </div>
      </div>
    </header>

    <!-- 搜索区域 -->
    <div class="search-container">
      <!-- Tab 切换（放在搜索框上方，样式低调） -->
      <div class="search-tabs">
      <button
        :class="['search-tab', { active: mode === 'traditional' }]"
        @click="mode = 'traditional'"
      >
        传统搜索
      </button>
      <button
        :class="['search-tab', { active: mode === 'ai' }]"
        @click="enableAIMode"
      >
        AI问答
      </button>
      <div class="search-tab-slider" :class="mode"></div>
    </div>

      <!-- 传统搜索模式 -->
      <div v-show="mode === 'traditional'" class="search-mode-content">
        <div class="search-form">
        <input
          v-model="searchInput"
          type="text"
          class="search-input"
          placeholder="输入关键词…"
          :disabled="loadingTraditional"
          @keydown.enter.prevent="doTraditionalSearch"
        />
        <input
          v-model="searchArgs"
          type="text"
          class="search-args-input"
          placeholder="筛选参数（可选，如 cat1=1&page=1&pageSize=10）"
          :disabled="loadingTraditional"
        />
        <button
          class="search-btn"
          :disabled="loadingTraditional || !searchInput.trim()"
          @click="doTraditionalSearch"
        >
          {{ loadingTraditional ? '搜索中…' : '搜索' }}
        </button>
      </div>
        <!-- 传统搜索结果 -->
        <div v-if="traditionalResult !== null" class="search-result-wrap">
        <div v-if="loadingTraditional" class="search-loading">
          <div class="search-loading-dots"><span></span><span></span><span></span></div>
          <span>搜索中…</span>
        </div>
        <template v-else>
          <div class="search-result-summary">共 {{ traditionalResult.total }} 条</div>
          <ul class="search-result-list">
            <li
              v-for="item in traditionalResult.msg"
              :key="item.id"
              class="search-result-item"
            >
              <div class="search-result-up" v-html="highlight(item.up)"></div>
              <div v-if="item.down" class="search-result-down">{{ item.down }}</div>
              <div v-if="item.title" class="search-result-title">{{ item.title }}</div>
            </li>
          </ul>
          <div v-if="traditionalResult.msg && traditionalResult.msg.length === 0" class="search-result-empty">
            暂无结果
          </div>
        </template>
        </div>
      </div>

      <!-- AI 问答模式 -->
      <div v-show="mode === 'ai'" class="search-mode-content ai-mode">
        <div class="search-form ai-form" @click="expandAIPanel">
          <textarea
            v-model="aiForm.question"
            class="search-input ai-question-input"
            placeholder="点击输入问题，展开下方栏位后补充纲目主题等信息…"
            rows="2"
            :disabled="loadingAI"
            @focus="expandAIPanel"
            @keydown.enter.exact.prevent="doAISearch"
          />
        </div>

        <transition name="ai-meta-panel">
          <div v-if="showAIDetails" class="ai-meta-panel">
            <div class="ai-meta-grid">
              <label class="ai-meta-field">
                <span>纲目主题</span>
                <input
                  v-model="aiForm.outlineTopic"
                  type="text"
                  placeholder="本次纲目的核心题目"
                  :disabled="loadingAI"
                />
              </label>
              <label class="ai-meta-field">
                <span>面对对象</span>
                <input
                  v-model="aiForm.audience"
                  type="text"
                  placeholder="例如：青职弟兄、初信者、小排服事者..."
                  :disabled="loadingAI"
                />
              </label>
              <label class="ai-meta-field full">
                <span>负担说明</span>
                <textarea
                  v-model="aiForm.burdenDescription"
                  rows="2"
                  placeholder="用简短段落说明本次聚会或分享的负担"
                  :disabled="loadingAI"
                />
              </label>
              <div class="ai-meta-field full">
                <span>纲目性质*（必选）</span>
                <div class="ai-nature-btns">
                  <button
                    type="button"
                    v-for="opt in AI_NATURE_OPTIONS"
                    :key="opt"
                    :class="['ai-nature-btn', { active: aiForm.specialNeeds === opt }]"
                    :disabled="loadingAI"
                    @click="aiForm.specialNeeds = aiForm.specialNeeds === opt ? '' : opt"
                  >
                    {{ opt }}
                  </button>
                </div>
              </div>
            </div>

            <div class="ai-depth-select">
              <span>检索深度</span>
              <div class="ai-depth-buttons">
                <button
                  type="button"
                  :class="['ai-depth-btn', { active: aiForm.depth === 'general' }]"
                  :disabled="loadingAI"
                  @click="aiForm.depth = 'general'"
                >
                  一般（快速）
                </button>
                <button
                  type="button"
                  :class="['ai-depth-btn', { active: aiForm.depth === 'deep' }]"
                  :disabled="loadingAI"
                  @click="aiForm.depth = 'deep'"
                >
                  深度（更全面）
                </button>
              </div>
            </div>

          <div class="ai-panel-actions">
            <div v-if="!aiFormValid" class="ai-panel-hint">
              请先填写「问题」「纲目主题」并选择「纲目性质」后再发送。
            </div>
            <label class="ai-checkbox-inline">
              <input type="checkbox" v-model="includeEnglishOutline" :disabled="!ENGLISH_OUTLINE_FEATURE_ENABLED || loadingAI" />
              <span>同时生成英文纲目</span>
            </label>
              <button
                class="search-btn"
                :disabled="loadingAI || !aiFormValid"
                @click="doAISearch"
              >
                {{ loadingAI ? '发送中…' : '发送给 Claude' }}
              </button>
            </div>
          </div>
        </transition>

        <!-- AI 结果：答案卡片 + 来源列表 -->
        <div v-if="aiResult !== null" class="ai-result-wrap">
          <div v-if="loadingAI" class="search-loading">
            <div class="search-loading-dots"><span></span><span></span><span></span></div>
            <span>AI 思考中…</span>
          </div>
          <template v-else>
            <div class="ai-answer-card">
              <div class="ai-answer-label">中文纲目</div>
              <div class="ai-answer-content" v-html="formatAnswer(aiResult.answer)"></div>
              <div v-if="aiResult.cached" class="ai-cached-tag">缓存</div>
              <button type="button" class="ai-copy-btn" @click="copyChinese">复制</button>
            </div>
            <div v-if="includeEnglishOutline" class="ai-answer-card ai-answer-card-en">
              <div class="ai-answer-label">英文纲目</div>
              <div v-if="loadingEnglish" class="ai-answer-content ai-answer-loading-en">正在生成英文纲目…</div>
              <div v-else-if="errorEnglish" class="ai-answer-content ai-answer-error-en">{{ errorEnglish }}</div>
              <div v-else-if="answerEn" class="ai-answer-content" v-html="formatAnswer(answerEn)"></div>
              <button v-if="answerEn" type="button" class="ai-copy-btn" @click="copyEnglish">复制</button>
            </div>
            <div v-if="aiResult.sources && aiResult.sources.length" class="ai-sources">
              <div class="ai-sources-label">参考来源</div>
              <div
                v-for="(src, i) in aiResult.sources"
                :key="i"
                class="ai-source-item"
              >
                <span class="ai-source-type">{{ src.type }}</span>
                <span class="ai-source-ref">{{ src.reference }}</span>
                <p class="ai-source-content">{{ src.content }}</p>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const apiBase = import.meta.env?.VITE_API_BASE || ''

const mode = ref('traditional') // 'traditional' | 'ai'
const searchInput = ref('')
const searchArgs = ref('')
const AI_NATURE_OPTIONS = ['一般性', '高真理浓度', '高生命浓度', '重实行应用']
const aiForm = reactive({
  question: '',
  outlineTopic: '',
  burdenDescription: '',
  specialNeeds: '一般性',
  audience: '',
  depth: 'general'
})
const showAIDetails = ref(false)
const loadingTraditional = ref(false)
const loadingAI = ref(false)
const traditionalResult = ref(null) // { total, msg[] }
const aiResult = ref(null) // { answer, sources[], cached?, ... }
// 暂封英文纲目功能，测试通过后改为 true
const ENGLISH_OUTLINE_FEATURE_ENABLED = false
const includeEnglishOutline = ref(false)
const answerEn = ref(null)
const loadingEnglish = ref(false)
const errorEnglish = ref(null)

const aiFormValid = computed(() => {
  const q = aiForm.question.trim().length > 0
  const outline = aiForm.outlineTopic.trim().length > 0
  const nature = aiForm.specialNeeds.trim().length > 0
  return q && outline && nature
})

function expandAIPanel() {
  showAIDetails.value = true
}

function enableAIMode() {
  mode.value = 'ai'
  showAIDetails.value = true
}
watch(
  () => route.hash || route.path,
  () => {
    if (route.path === '/search' && route.hash === '#ai') {
      enableAIMode()
    }
  },
  { immediate: true }
)

function highlight(text) {
  if (!text) return ''
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>')
}

async function doTraditionalSearch() {
  const input = searchInput.value?.trim()
  if (!input || loadingTraditional.value) return
  loadingTraditional.value = true
  traditionalResult.value = null
  try {
    const form = new FormData()
    form.append('input', input)
    form.append('args', searchArgs.value || '')
    const res = await fetch(`${apiBase}/search`, {
      method: 'POST',
      credentials: 'include',
      body: form
    })
    const data = await res.json().catch(() => ({ total: 0, msg: [] }))
    traditionalResult.value = { total: data.total ?? 0, msg: data.msg ?? [] }
  } catch (e) {
    traditionalResult.value = { total: 0, msg: [] }
  } finally {
    loadingTraditional.value = false
  }
}

function formatAnswer(text) {
  if (!text) return ''
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>')
}

async function fetchTranslate(chineseOutline) {
  if (!chineseOutline || !chineseOutline.trim()) return
  loadingEnglish.value = true
  errorEnglish.value = null
  answerEn.value = null
  try {
    const res = await fetch(`${apiBase}/api/ai_search/translate_outline`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ chinese_outline: chineseOutline })
    })
    const data = await res.json().catch(() => ({}))
    if (data.answer_en) {
      answerEn.value = data.answer_en
    } else {
      errorEnglish.value = data.error || '英文纲目生成失败'
    }
  } catch (e) {
    errorEnglish.value = e.message || '翻译请求失败，请稍后重试'
  } finally {
    loadingEnglish.value = false
  }
}

function copyChinese() {
  const text = aiResult.value?.answer
  if (!text) return
  navigator.clipboard.writeText(text).then(() => {}).catch(() => {})
}

function copyEnglish() {
  const text = answerEn.value
  if (!text) return
  navigator.clipboard.writeText(text).then(() => {}).catch(() => {})
}

async function doAISearch() {
  const question = aiForm.question?.trim()
  if (!question || loadingAI.value || !aiFormValid.value) {
    showAIDetails.value = true
    return
  }
  loadingAI.value = true
  aiResult.value = null
  answerEn.value = null
  errorEnglish.value = null
  const payload = {
    question,
    max_results: 10,
    depth: aiForm.depth,
    outline_topic: aiForm.outlineTopic.trim(),
    burden_description: aiForm.burdenDescription.trim(),
    special_needs: aiForm.specialNeeds.trim(),
    audience: aiForm.audience.trim()
  }
  try {
    const res = await fetch(`${apiBase}/api/ai_search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(payload)
    })
    const data = await res.json().catch(() => ({}))
    aiResult.value = {
      answer: data.answer || '暂无回答。',
      sources: data.sources || [],
      cached: !!data.cached
    }
    if (includeEnglishOutline.value) {
      fetchTranslate(aiResult.value.answer)
    }
    aiForm.question = ''
  } catch (e) {
    aiResult.value = { answer: '请求失败，请稍后重试。', sources: [], cached: false }
  } finally {
    loadingAI.value = false
  }
}
</script>

<style scoped>
/* ========== 整体布局 ========== */
.search-page {
  min-height: 100vh;
  background: #eee;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}

/* ========== 顶部导航栏 ========== */
.top-nav {
  background: #fff;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  position: sticky;
  top: 0;
  z-index: 100;
}

.nav-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 60px;
}

.nav-logo {
  font-size: 1.25rem;
  font-weight: 700;
  color: #1677ff;
  cursor: pointer;
}

.nav-links {
  display: flex;
  gap: 32px;
  flex: 1;
  justify-content: center;
}

.nav-link {
  text-decoration: none;
  color: #666;
  font-size: 0.95rem;
  padding: 8px 12px;
  border-radius: 6px;
  transition: all 0.2s;
}

.nav-link:hover {
  color: #1677ff;
  background: #f0f7ff;
}

.nav-link.active {
  color: #1677ff;
  font-weight: 600;
}

.nav-actions {
  display: flex;
  gap: 12px;
}

.nav-btn {
  text-decoration: none;
  padding: 6px 16px;
  border-radius: 6px;
  font-size: 0.9rem;
  color: #1677ff;
  border: 1px solid #1677ff;
  transition: all 0.2s;
}

.nav-btn:hover {
  background: #1677ff;
  color: #fff;
}

/* ========== 搜索容器 ========== */
.search-container {
  max-width: 900px;
  margin: 24px auto;
  padding: 0 20px;
}

/* ========== Tab 切换（低调样式，放搜索框上方） ========== */
.search-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 16px;
  border-bottom: 2px solid #e0e0e0;
  position: relative;
}

.search-tab {
  padding: 10px 20px;
  border: none;
  background: transparent;
  font-size: 0.9rem;
  color: #888;
  cursor: pointer;
  position: relative;
  transition: all 0.2s;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
}

.search-tab:hover {
  color: #1677ff;
}

.search-tab.active {
  color: #1677ff;
  font-weight: 500;
  border-bottom-color: #1677ff;
}

.search-tab-slider {
  display: none;
}

/* ========== 搜索模式内容区 ========== */
.search-mode-content {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

/* ========== 搜索表单 ========== */
.search-form {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
  align-items: flex-start;
}

.search-form.ai-form {
  flex-direction: column;
}

.ai-meta-panel {
  margin-top: 12px;
  padding: 16px;
  border: 1px solid #e6f4ff;
  border-radius: 8px;
  background: #fafdff;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ai-meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px 16px;
}

.ai-meta-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 0.85rem;
  color: #555;
}

.ai-meta-field.full {
  grid-column: 1 / -1;
}

.ai-meta-field input,
.ai-meta-field textarea {
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 0.9rem;
  font-family: inherit;
  resize: none;
  transition: border-color 0.2s;
}

.ai-meta-field input:focus,
.ai-meta-field textarea:focus {
  outline: none;
  border-color: #1677ff;
  box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.08);
}

.ai-nature-btns {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.ai-nature-btn {
  border: 1px solid #d9d9d9;
  background: #fff;
  color: #555;
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.9rem;
  transition: all 0.2s;
}

.ai-nature-btn:hover:not(:disabled):not(.active) {
  border-color: #1677ff;
  color: #1677ff;
}

.ai-nature-btn.active {
  background: #1677ff;
  border-color: #1677ff;
  color: #fff;
}

.ai-nature-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.ai-depth-select {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.ai-depth-buttons {
  display: flex;
  gap: 8px;
}

.ai-depth-btn {
  border: 1px solid #d9d9d9;
  background: #fff;
  color: #555;
  padding: 8px 16px;
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.2s;
}

.ai-depth-btn.active {
  background: #1677ff;
  border-color: #1677ff;
  color: #fff;
  box-shadow: 0 4px 12px rgba(22, 119, 255, 0.25);
}

.ai-depth-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.ai-panel-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.ai-panel-hint {
  font-size: 0.85rem;
  color: #fa8c16;
}

.ai-meta-panel-enter-active,
.ai-meta-panel-leave-active {
  transition: all 0.2s ease;
}

.ai-meta-panel-enter-from,
.ai-meta-panel-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

.search-input,
.search-args-input,
.ai-question-input {
  padding: 10px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  font-size: 0.9rem;
  transition: border-color 0.2s;
}

.search-input {
  flex: 2;
  min-width: 250px;
}

.search-args-input {
  flex: 1;
  min-width: 200px;
  font-size: 0.85rem;
  color: #666;
}

.ai-question-input {
  width: 100%;
  min-height: 70px;
  resize: vertical;
  font-family: inherit;
}

.search-input:focus,
.search-args-input:focus,
.ai-question-input:focus {
  outline: none;
  border-color: #1677ff;
  box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.1);
}

.search-input:disabled,
.ai-question-input:disabled {
  background: #f5f5f5;
  cursor: not-allowed;
}

.search-btn {
  padding: 10px 28px;
  background: #1677ff;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 0.9rem;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
  font-weight: 500;
}

.search-btn:hover:not(:disabled) {
  background: #4096ff;
  box-shadow: 0 2px 8px rgba(22, 119, 255, 0.3);
}

.search-btn:disabled {
  background: #d9d9d9;
  color: #999;
  cursor: not-allowed;
}

/* ========== 加载状态 ========== */
.search-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px 20px;
  color: #666;
  font-size: 0.9rem;
}

.search-loading-dots {
  display: flex;
  gap: 5px;
}

.search-loading-dots span {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #1677ff;
  animation: search-dot-bounce 1.4s ease-in-out infinite both;
}

.search-loading-dots span:nth-child(1) { animation-delay: -0.32s; }
.search-loading-dots span:nth-child(2) { animation-delay: -0.16s; }
.search-loading-dots span:nth-child(3) { animation-delay: 0s; }

@keyframes search-dot-bounce {
  0%, 80%, 100% { 
    transform: scale(0); 
    opacity: 0.5; 
  }
  40% { 
    transform: scale(1); 
    opacity: 1; 
  }
}

/* ========== 传统搜索结果（原样式） ========== */
.search-result-wrap {
  margin-top: 0;
}

.search-result-summary {
  padding: 12px 16px;
  background: #fafafa;
  border-radius: 6px;
  font-size: 0.85rem;
  color: #666;
  margin-bottom: 16px;
  font-weight: 500;
}

.search-result-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.search-result-item {
  padding: 16px;
  border-bottom: 1px solid #f0f0f0;
  transition: background 0.2s;
}

.search-result-item:hover {
  background: #fafafa;
}

.search-result-item:last-child {
  border-bottom: none;
}

.search-result-up {
  font-size: 1rem;
  line-height: 1.8;
  color: #333;
  margin-bottom: 6px;
}

/* 高亮样式（匹配老项目 em 标签） */
.search-result-up :deep(em) {
  font-style: normal;
  color: tomato;
  font-weight: 600;
}

.search-result-down {
  font-size: 0.9rem;
  color: #666;
  line-height: 1.6;
  margin-top: 6px;
}

.search-result-title {
  font-size: 0.8rem;
  color: #999;
  margin-top: 8px;
  font-style: italic;
}

.search-result-empty {
  text-align: center;
  color: #bbb;
  padding: 60px 20px;
  font-size: 0.95rem;
}

/* ========== AI 答案区域 ========== */
.ai-result-wrap {
  margin-top: 0;
}

.ai-answer-card {
  position: relative;
  padding: 20px;
  background: linear-gradient(135deg, #f0f7ff 0%, #e6f4ff 100%);
  border-radius: 8px;
  border: 1px solid #d6e9ff;
  margin-bottom: 20px;
  box-shadow: 0 2px 8px rgba(22, 119, 255, 0.08);
}

.ai-answer-label {
  display: inline-block;
  font-size: 0.75rem;
  color: #1677ff;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 10px;
  padding: 4px 10px;
  background: #fff;
  border-radius: 4px;
}

.ai-answer-content {
  font-size: 1rem;
  line-height: 1.8;
  color: #333;
}

.ai-cached-tag {
  position: absolute;
  top: 16px;
  right: 16px;
  font-size: 0.7rem;
  color: #999;
  background: rgba(255, 255, 255, 0.9);
  padding: 4px 8px;
  border-radius: 4px;
}

.ai-copy-btn {
  margin-top: 10px;
  padding: 6px 14px;
  font-size: 0.85rem;
  color: #1677ff;
  background: #fff;
  border: 1px solid #1677ff;
  border-radius: 6px;
  cursor: pointer;
}
.ai-copy-btn:hover {
  background: #e6f4ff;
}

.ai-checkbox-inline {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-right: 12px;
  cursor: pointer;
  font-size: 0.9rem;
}
.ai-checkbox-inline input { margin: 0; }

.ai-answer-loading-en,
.ai-answer-error-en {
  color: #666;
  padding: 12px 0;
}
.ai-answer-error-en {
  color: #c41e3a;
}

/* AI 来源列表 */
.ai-sources {
  margin-top: 0;
}

.ai-sources-label {
  font-size: 0.85rem;
  color: #666;
  font-weight: 600;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 2px solid #f0f0f0;
}

.ai-source-item {
  padding: 14px 16px;
  background: #fafafa;
  border-radius: 6px;
  margin-bottom: 10px;
  border-left: 3px solid #1677ff;
  transition: all 0.2s;
}

.ai-source-item:hover {
  background: #f5f5f5;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.ai-source-type {
  display: inline-block;
  font-size: 0.75rem;
  color: #fff;
  background: #1677ff;
  padding: 2px 8px;
  border-radius: 3px;
  margin-right: 10px;
  font-weight: 500;
}

.ai-source-ref {
  font-weight: 600;
  color: #333;
  font-size: 0.9rem;
}

.ai-source-content {
  margin: 10px 0 0;
  color: #666;
  line-height: 1.7;
  font-size: 0.9rem;
}

/* ========== 响应式 ========== */
@media (max-width: 768px) {
  .nav-links {
    gap: 16px;
  }
  
  .nav-link {
    font-size: 0.85rem;
    padding: 6px 8px;
  }
  
  .search-container {
    padding: 0 12px;
  }
  
  .search-form {
    flex-direction: column;
  }
  
  .search-input,
  .search-args-input {
    width: 100%;
  }
}
</style>

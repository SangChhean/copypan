<template>
  <div class="container">
    <!-- 页面标题 -->
    <h2 class="title">纲目翻译（练习版）</h2>

    <!-- 方向切换按钮 -->
    <div class="direction-toggle">
      <button
        :class="['toggle-btn', direction === 'zh2en' ? 'active' : '']"
        @click="direction = 'zh2en'"
      >
        中文 → 英文
      </button>
      <button
        :class="['toggle-btn', direction === 'en2zh' ? 'active' : '']"
        @click="direction = 'en2zh'"
      >
        英文 → 中文
      </button>
    </div>

    <!-- 输入区：多行文本框 -->
    <textarea
      v-model="content"
      class="input-area"
      placeholder="请粘贴纲目内容..."
      rows="12"
    />

    <!-- 空内容提示 -->
    <p v-if="emptyError" class="error-text">请先输入内容</p>

    <!-- 翻译按钮 -->
    <button
      class="translate-btn"
      :disabled="loading"
      @click="handleTranslate"
    >
      {{ loading ? '翻译中…' : '翻译' }}
    </button>

    <!-- 错误信息（请求失败） -->
    <p v-if="requestError" class="error-text">{{ requestError }}</p>

    <!-- 结果区 -->
    <div v-if="result" class="result-box">
      <!-- 结果区右上角复制按钮 -->
      <button class="copy-btn" @click="handleCopy">
        {{ copied ? '已复制' : '复制' }}
      </button>
      <!-- 翻译结果内容 -->
      <pre class="result-text">{{ result }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

// 翻译方向，默认中翻英
const direction = ref('zh2en')

// 用户输入的纲目内容
const content = ref('')

// 翻译结果
const result = ref('')

// 加载状态
const loading = ref(false)

// 空内容校验提示
const emptyError = ref(false)

// 请求失败的错误信息
const requestError = ref('')

// 复制按钮状态
const copied = ref(false)

// 点击「翻译」按钮
async function handleTranslate() {
  // 重置状态
  emptyError.value = false
  requestError.value = ''
  result.value = ''

  // 第一步：检查内容是否为空
  if (!content.value.trim()) {
    emptyError.value = true
    return
  }

  // 第二步：发起请求
  loading.value = true
  try {
    const res = await fetch('/api/practice/translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        direction: direction.value,
        content: content.value,
      }),
    })

    // 第三步：处理非 2xx 响应
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}))
      requestError.value = errData.detail || `请求失败（${res.status}）`
      return
    }

    // 第四步：解析并展示结果
    const data = await res.json()
    if (data.error) {
      requestError.value = data.error
    } else {
      result.value = data.result
    }
  } catch (e) {
    // 网络错误等异常
    requestError.value = '网络错误，请稍后重试'
  } finally {
    loading.value = false
  }
}

// 点击「复制」按钮
async function handleCopy() {
  if (!result.value) return
  try {
    await navigator.clipboard.writeText(result.value)
    copied.value = true
    // 2 秒后恢复按钮文字
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    // 部分浏览器不支持 clipboard API，静默失败
  }
}
</script>

<style scoped>
.container {
  max-width: 760px;
  margin: 40px auto;
  padding: 0 20px;
  font-family: sans-serif;
}

.title {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 20px;
  color: #222;
}

/* 切换按钮组 */
.direction-toggle {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}

.toggle-btn {
  padding: 6px 18px;
  border: 1px solid #ccc;
  border-radius: 4px;
  background: #f5f5f5;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.15s, border-color 0.15s;
}

.toggle-btn.active {
  background: #1a6ef5;
  border-color: #1a6ef5;
  color: #fff;
}

/* 输入区 */
.input-area {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 12px;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 14px;
  line-height: 1.6;
  resize: vertical;
  outline: none;
  transition: border-color 0.15s;
}

.input-area:focus {
  border-color: #1a6ef5;
}

/* 错误文字 */
.error-text {
  margin: 6px 0 0;
  color: #d0021b;
  font-size: 13px;
}

/* 翻译按钮 */
.translate-btn {
  margin-top: 14px;
  padding: 8px 28px;
  background: #1a6ef5;
  color: #fff;
  border: none;
  border-radius: 4px;
  font-size: 15px;
  cursor: pointer;
  transition: opacity 0.15s;
}

.translate-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 结果区 */
.result-box {
  position: relative;
  margin-top: 24px;
  padding: 16px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: #fafafa;
}

/* 复制按钮（右上角） */
.copy-btn {
  position: absolute;
  top: 10px;
  right: 12px;
  padding: 4px 14px;
  font-size: 12px;
  border: 1px solid #ccc;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  transition: background 0.15s;
}

.copy-btn:hover {
  background: #f0f0f0;
}

/* 结果文字 */
.result-text {
  margin: 0;
  padding-right: 60px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 14px;
  line-height: 1.7;
  color: #333;
}
</style>
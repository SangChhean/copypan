<template>
  <div class="page">

    <div class="topbar">
      <button class="back-btn" @click="$router.push('/tools')">
        <span class="arrow">←</span> 返回工具箱
      </button>
      <span class="page-title">经文汇集</span>
      <span class="badge">零 AI 成本</span>
    </div>

    <div class="body">

      <!-- 输入区 -->
      <div class="input-card">
        <div class="section-label">纲目文字</div>
        <textarea
          v-model="inputText"
          class="textarea-input"
          placeholder="粘贴纲目，每行一条，自动识别所有经文引用…"
        ></textarea>
        <div class="hint">支持格式：约三16 · 约壹一5 · 创一1-3 · 约翰三章16节 · 马太福音五章6节</div>
        <div class="actions">
          <button class="btn-primary" @click="collect" :disabled="loading">
            {{ loading ? '汇集中…' : '汇集经文' }}
          </button>
          <button class="btn-ghost" @click="clear">清空</button>
        </div>
      </div>

      <!-- 结果区 -->
      <div class="result-card" v-if="results.length">
        <div class="result-label">汇集结果</div>
        <div class="result-scroll" ref="resultScroll">
          <div
            v-for="(row, idx) in results"
            :key="idx"
            class="outline-block"
          >
            <!-- 纲目行：检测序号列宽，动态对齐 -->
            <div class="outline-row">
              <span class="outline-seq" :ref="el => seqEls[idx] = el">{{ getSeq(row.text) }}</span>
              <span class="outline-txt">{{ getBody(row.text) }}</span>
            </div>
            <!-- 经文行：padding-left 与纲目首字对齐 -->
            <div
              v-for="(ver, vi) in row.vers"
              :key="vi"
              class="verse-row"
              :style="{ paddingLeft: seqWidths[idx] + 'px' }"
            >
              <span class="verse-src">{{ ver.source }}</span>
              <span class="verse-sep">|</span>
              <span class="verse-txt">{{ ver.text }}</span>
            </div>
          </div>
        </div>
      </div>

    </div>

    <!-- 底部复制栏 -->
    <div class="bottom-bar" v-if="results.length">
      <button class="copy-btn" @click="copyAll">
        {{ copied ? '已复制 ✓' : '复制全部内容' }}
      </button>
    </div>

  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'

const inputText = ref('')
const results = ref([])
const loading = ref(false)
const copied = ref(false)
const seqEls = ref([])
const seqWidths = ref([])
const resultScroll = ref(null)

// 提取序号部分（行首的壹/一/二/1./A. 等 + 紧跟的全角空格）
function getSeq(line) {
  const m = line.match(/^(\s*[壹贰叁肆伍陆柒捌玖拾一二三四五六七八九十百\d]+[.．、\s　]*)/u)
  return m ? m[1] : ''
}

// 提取序号后的正文部分
function getBody(line) {
  const seq = getSeq(line)
  return line.slice(seq.length)
}

// 测量所有序号列的实际像素宽度，写入 seqWidths
async function measureSeqs() {
  await nextTick()
  seqWidths.value = seqEls.value.map(el => (el ? el.offsetWidth : 0))
}

async function collect() {
  if (!inputText.value.trim()) return
  loading.value = true
  results.value = []
  copied.value = false
  try {
    const res = await fetch('/api/testb/bible_co/process', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: inputText.value })
    })
    if (!res.ok) {
      alert('接口返回错误：' + res.status + ' ' + res.statusText)
      return
    }
    results.value = await res.json()
    await measureSeqs()
  } catch (e) {
    console.error('经文汇集请求失败', e)
    alert('请求失败：' + e.message)
  } finally {
    loading.value = false
  }
}

function clear() {
  inputText.value = ''
  results.value = []
  copied.value = false
  seqWidths.value = []
}

function copyAll() {
  // 复制格式：纲目行 \n 出处\t经文 \n 出处\t经文 \n\n 下一条…
  const lines = []
  for (const row of results.value) {
    lines.push(row.text)
    for (const ver of row.vers) {
      lines.push(`${ver.source}\t${ver.text}`)
    }
    lines.push('')   // 每条纲目之间空一行
  }
  // 去掉末尾多余空行
  while (lines.length && lines[lines.length - 1] === '') lines.pop()
  navigator.clipboard.writeText(lines.join('\n')).then(() => {
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  })
}
</script>

<style scoped>
* { box-sizing: border-box; margin: 0; padding: 0; }

.page {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: #F5F5F3;
  font-family: inherit;
}

.topbar {
  background: #fff;
  border-bottom: 0.5px solid rgba(0,0,0,0.1);
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}
.back-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #666;
  background: none;
  border: 0.5px solid rgba(0,0,0,0.2);
  border-radius: 8px;
  padding: 5px 10px;
  cursor: pointer;
}
.back-btn:hover { background: #f0f0f0; }
.arrow { font-size: 14px; }
.page-title { font-size: 15px; font-weight: 500; color: #1a1a1a; }
.badge {
  background: #EEEDFE;
  color: #3C3489;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 20px;
  margin-left: auto;
}

.body {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
}

.section-label {
  font-size: 12px;
  color: #888;
  margin-bottom: 6px;
  font-weight: 500;
  letter-spacing: 0.02em;
}

.input-card {
  background: #fff;
  border: 0.5px solid rgba(0,0,0,0.1);
  border-radius: 12px;
  padding: 14px;
  display: flex;
  flex-direction: column;
}
.textarea-input {
  background: #F5F5F3;
  border: 0.5px solid rgba(0,0,0,0.1);
  border-radius: 8px;
  padding: 10px 12px;
  height: 40vh;
  resize: none;
  font-size: 13px;
  line-height: 1.85;
  color: #1a1a1a;
  font-family: inherit;
  overflow-y: auto;
}
.textarea-input:focus { outline: none; border-color: #534AB7; }
.hint { font-size: 12px; color: #aaa; margin-top: 6px; }
.actions { display: flex; gap: 8px; margin-top: 10px; }

.btn-primary {
  background: #534AB7;
  color: #EEEDFE;
  border: none;
  border-radius: 8px;
  padding: 7px 18px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}
.btn-primary:hover:not(:disabled) { background: #3C3489; }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }

.btn-ghost {
  background: none;
  color: #666;
  border: 0.5px solid rgba(0,0,0,0.2);
  border-radius: 8px;
  padding: 7px 14px;
  font-size: 13px;
  cursor: pointer;
}
.btn-ghost:hover { background: #f0f0f0; }

.result-card {
  background: #fff;
  border: 0.5px solid rgba(0,0,0,0.1);
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.result-label {
  font-size: 12px;
  color: #888;
  font-weight: 500;
  letter-spacing: 0.02em;
  padding: 12px 14px 6px;
  flex-shrink: 0;
}
.result-scroll {
  height: 40vh;
  overflow-y: auto;
  padding: 0 14px 14px;
}

.outline-block { margin-bottom: 10px; }

/* 纲目行：flex，序号 + 正文 */
.outline-row {
  display: flex;
  background: #EEEDFE;
  border-left: 3px solid #534AB7;
  border-radius: 0 8px 8px 0;
  margin-bottom: 3px;
  padding: 6px 10px;
  font-size: 13px;
  line-height: 1.75;
  color: #3C3489;
  font-weight: 500;
}
.outline-seq { flex-shrink: 0; white-space: pre; }
.outline-txt { flex: 1; }

/* 经文行：padding-left 由 JS 动态计算（与纲目首字对齐） */
.verse-row {
  display: flex;
  align-items: baseline;
  font-size: 13px;
  line-height: 1.75;
  padding-top: 2px;
  padding-bottom: 2px;
  padding-right: 10px;
  /* padding-left 由 :style 绑定 */
}
.verse-src {
  color: #534AB7;
  font-weight: 500;
  flex-shrink: 0;
  font-size: 13px;
  white-space: nowrap;
}
.verse-sep {
  color: #bbb;
  padding: 0 6px;
  flex-shrink: 0;
  font-size: 12px;
}
.verse-txt { color: #1a1a1a; flex: 1; }

.bottom-bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 10px 16px;
  background: #fff;
  border-top: 0.5px solid rgba(0,0,0,0.1);
  flex-shrink: 0;
}
.copy-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  background: none;
  border: 0.5px solid rgba(0,0,0,0.2);
  border-radius: 8px;
  padding: 5px 14px;
  font-size: 13px;
  color: #666;
  cursor: pointer;
}
.copy-btn:hover { background: #f0f0f0; }
</style>

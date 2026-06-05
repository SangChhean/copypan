<script setup>
import { ref, computed } from "vue";
const window = globalThis;
const apiBase = "";
const goTools = () => {
  window.location.hash = "/tools";
};

const direction = ref("s2t");
const content = ref("");
const loading = ref(false);
const checking = ref(false);
const error = ref(null);
const result = ref(null);
const toast = ref("");
const hits = ref([]); // 易错字命中列表
const downloading = ref(false);

const isS2t = computed(() => direction.value === "s2t");
const inputPlaceholder = computed(() =>
  isS2t.value ? "请粘贴简体中文…" : "请粘贴繁体中文…"
);

function showToast(msg) {
  toast.value = msg;
  setTimeout(() => {
    if (toast.value === msg) toast.value = "";
  }, 2500);
}

function copyResult() {
  if (!result.value) return;
  navigator.clipboard.writeText(result.value).then(() => {
    showToast("已复制");
  });
}

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
  return fallback;
}

// 刷格式下载：type 为 'zh'（简体）或 'zhtw'（繁体）
async function downloadFormat(text, type) {
  if (!text || downloading.value) return;
  downloading.value = true;
  try {
    const res = await fetch(`${apiBase}/api/testb/format/${type}`, {
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

// 全部接受
function acceptAll() {
  if (!result.value) return;
  let text = result.value;
  let count = 0;
  // 按词长降序替换，避免短词截断长词
  const toAccept = [...hits.value]
    .filter(h => h.suggestion && !h.accepted)
    .sort((a, b) => b.word.length - a.word.length);
  for (const hit of toAccept) {
    if (text.includes(hit.word)) {
      text = text.replaceAll(hit.word, hit.suggestion);
      hit.accepted = true;
      count++;
    }
  }
  result.value = text;
  showToast(`已接受 ${count} 条建议`);
}

// 取命中词的上下文（前后10个字）
function getContext(hit) {
  if (!result.value) return { before: "", word: "", after: "" };
  const pos = hit.positions[0];
  const start = Math.max(0, pos - 5);
  const end = Math.min(result.value.length, pos + hit.word.length + 5);
  const before = result.value.slice(start, pos);
  const word = result.value.slice(pos, pos + hit.word.length);
  const after = result.value.slice(pos + hit.word.length, end);
  return { before, word, after };
}

// 接受手动输入
function acceptManual(hit) {
  const val = (hit.manualInput || "").trim();
  if (!val || !result.value) return;
  result.value = result.value.replaceAll(hit.word, val);
  hit.accepted = true;
  showToast(`已替换：${hit.word} → ${val}`);
}

// 扫描易错字
async function checkErrors() {
  if (!result.value) return;
  checking.value = true;
  hits.value = [];
  try {
    const res = await fetch(`${apiBase}/api/testb/check_errors`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: result.value }),
    });
    const data = await res.json();
    hits.value = (data.hits || []).map(h => ({ ...h, accepted: false, manualInput: h.suggestion || "" }));
    if (hits.value.length === 0) {
      showToast("未发现易错字");
    }
  } catch (e) {
    showToast("易错字检查失败，请稍后重试");
  } finally {
    checking.value = false;
  }
}

async function convert() {
  const text = (content.value || "").trim();
  if (!text) {
    error.value = "请先粘贴要转换的内容";
    result.value = null;
    hits.value = [];
    return;
  }
  loading.value = true;
  error.value = null;
  result.value = null;
  hits.value = [];
  const endpoint = isS2t.value
    ? `${apiBase}/api/testb/zh_convert`
    : `${apiBase}/api/testb/zh_to_simplified`;
  const resultField = isS2t.value ? "answer_zh_tw" : "answer_zh_cn";
  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: text }),
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      let detail = errorData.detail;
      if (Array.isArray(detail)) {
        detail = detail.map((x) => x?.msg || x?.message || JSON.stringify(x)).join("；");
      }
      error.value = detail || errorData.error || errorData.message || "转换失败，请稍后重试";
      return;
    }
    const data = await res.json();
    const answer = data[resultField];
    if (data.error && !answer) {
      error.value = data.error;
      return;
    }
    if (answer) {
      result.value = answer;
      showToast("转换完成，正在检查易错字…");
      // 简转繁后自动扫描
      if (isS2t.value) {
        await checkErrors();
      }
    } else {
      error.value = "转换失败，请稍后重试";
    }
  } catch (err) {
    error.value =
      (err && err.message) ||
      (typeof err === "string" ? err : "") ||
      "网络错误，请稍后重试";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div v-if="toast" class="toast">{{ toast }}</div>
  <div class="box">
    <header class="page-header">
      <button type="button" class="back-btn" aria-label="返回" @click="goTools">←</button>
      <h1 class="page-title">简繁互转测试</h1>
    </header>

    <section class="card">
      <p class="hint">独立练习环境：粘贴内容后选择方向，点「转换」即可（无下载、无登录）。</p>
      <hr class="divider" />
      <div class="direction-row">
        <span class="label">转换方向：</span>
        <div class="segmented">
          <button
            type="button"
            class="seg-btn"
            :class="{ active: direction === 's2t' }"
            @click="direction = 's2t'"
          >
            简体 → 繁体
          </button>
          <button
            type="button"
            class="seg-btn"
            :class="{ active: direction === 't2s' }"
            @click="direction = 't2s'"
          >
            繁体 → 简体
          </button>
        </div>
      </div>
      <hr class="divider" />
      <div class="textarea-wrap">
        <textarea
          v-model="content"
          :placeholder="inputPlaceholder"
          class="content-area"
          :disabled="loading"
        />
      </div>
      <div class="action-row">
        <button type="button" class="clear-btn" :disabled="!content || loading" @click="content = ''">
          清空
        </button>
        <button type="button" class="convert-btn" :disabled="loading || !content.trim()" @click="convert">
          <span v-if="loading" class="spin">⟳</span>
          <span>{{ loading ? "转换中…" : "转换" }}</span>
        </button>
      </div>
    </section>

    <p v-if="error" class="error">{{ error }}</p>

    <section v-if="result" class="card result-card">
      <div class="result-head">
        <span>转换结果</span>
        <div class="result-head-actions">
          <button type="button" class="copy-btn" @click="copyResult">复制</button>
          <button type="button" class="format-btn"
            :disabled="downloading"
            @click="downloadFormat(result, isS2t ? 'zhtw' : 'zh')">
            <span v-if="downloading" class="spin">⟳</span>
            {{ downloading ? "下载中…" : "⬇ 刷格式下载" }}
          </button>
          <button type="button" class="recheck-btn" :disabled="checking" @click="checkErrors">
            <span v-if="checking" class="spin">⟳</span>
            {{ checking ? "检查中…" : "重新检查" }}
          </button>
        </div>
      </div>
      <textarea v-model="result" class="result-area" />

      <!-- 易错字列表 -->
      <div v-if="hits.length > 0" class="hits-section">
        <div class="hits-header">
          <span class="hits-title">发现 {{ hits.length }} 处易错字</span>
          <button type="button" class="accept-all-btn"
            :disabled="hits.filter(h => h.suggestion && !h.accepted).length === 0"
            @click="acceptAll">
            全部接受
          </button>
        </div>
        <div class="hits-list">
          <div v-for="(hit, idx) in hits" :key="idx"
            class="hit-item" :class="{ accepted: hit.accepted }">
            <div class="hit-main">
              <template v-if="hit.suggestion">
                <span class="hit-context-inline" v-if="!hit.accepted">
                  <span class="ctx-before">…{{ getContext(hit).before }}</span>
                  <span class="ctx-word">{{ getContext(hit).word }}</span>
                  <span class="ctx-after">{{ getContext(hit).after }}…</span>
                </span>
                <input v-model="hit.manualInput" class="manual-input"
                  :disabled="hit.accepted" />
                <button type="button" class="accept-btn"
                  :disabled="hit.accepted || !hit.manualInput.trim()"
                  @click="acceptManual(hit)">
                  {{ hit.accepted ? "已接受" : "接受" }}
                </button>
              </template>
              <template v-else>
                <span class="hit-context-inline" v-if="!hit.accepted">
                  <span class="ctx-before">…{{ getContext(hit).before }}</span>
                  <span class="ctx-word">{{ getContext(hit).word }}</span>
                  <span class="ctx-after">{{ getContext(hit).after }}…</span>
                </span>
                <input v-model="hit.manualInput" class="manual-input"
                  :placeholder="`替换为…`" :disabled="hit.accepted" />
                <button type="button" class="accept-btn"
                  :disabled="hit.accepted || !hit.manualInput.trim()"
                  @click="acceptManual(hit)">
                  {{ hit.accepted ? "已接受" : "替换" }}
                </button>
              </template>
            </div>
          </div>
        </div>
      </div>
      <div v-else-if="!checking && result" class="no-hits">
        未发现易错字 ✓
      </div>
    </section>
  </div>
</template>

<style scoped>
.toast {
  position: fixed;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.75);
  color: #fff;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  z-index: 1000;
}
.box {
  padding: 1em;
  max-width: 720px;
  margin: 0 auto;
}
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.back-btn {
  width: 36px;
  height: 36px;
  font-size: 20px;
  line-height: 1;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  background: #fff;
  color: #333;
  cursor: pointer;
}
.back-btn:hover {
  border-color: #1890ff;
  color: #1890ff;
}
.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #222;
}
.card {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
.hint {
  color: #555;
  margin: 0;
  font-size: 0.95em;
  line-height: 1.5;
}
.divider {
  border: none;
  border-top: 1px solid #f0f0f0;
  margin: 12px 0;
}
.direction-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.direction-row .label {
  font-weight: 600;
  color: #333;
}
.segmented {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.seg-btn {
  padding: 8px 20px;
  font-weight: 500;
  font-size: 15px;
  border: 2px solid #d9d9d9;
  border-radius: 6px;
  background: #fafafa;
  cursor: pointer;
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
.textarea-wrap {
  margin-top: 8px;
}
.content-area {
  width: 100%;
  box-sizing: border-box;
  height: calc(100vh - 420px);
  min-height: 400px;
  border-radius: 8px;
  border: 1px solid #d9d9d9;
  padding: 10px;
  font-family: inherit;
  font-size: 14px;
  resize: none;
  overflow-y: auto;
}
.action-row {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
  display: flex;
  justify-content: center;
  gap: 16px;
}
.clear-btn {
  padding: 8px 24px;
  font-size: 16px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  background: #fff;
  color: #333;
  cursor: pointer;
}
.clear-btn:hover:not(:disabled) {
  color: #ff4d4f;
  border-color: #ff4d4f;
}
.clear-btn:disabled {
  opacity: 0.5;
  color: #bbb;
  cursor: not-allowed;
}
.convert-btn {
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
.convert-btn:hover:not(:disabled) {
  background: #40a9ff;
}
.convert-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}
.spin {
  display: inline-block;
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.error {
  margin-top: 12px;
  color: #cf1322;
}
.result-card {
  margin-top: 20px;
}
.result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-weight: 600;
}
.copy-btn {
  padding: 4px 10px;
  font-size: 13px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
}
.copy-btn:hover {
  border-color: #1890ff;
  color: #1890ff;
}
.format-btn {
  padding: 4px 10px;
  font-size: 13px;
  border: 1px solid #52c41a;
  border-radius: 4px;
  background: #fff;
  color: #389e0d;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.format-btn:hover:not(:disabled) {
  background: #52c41a;
  color: #fff;
}
.format-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.result-body {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-size: 0.95em;
  line-height: 1.6;
  max-height: 60vh;
  overflow-y: auto;
}
.result-area {
  width: 100%;
  box-sizing: border-box;
  min-height: 200px;
  max-height: 50vh;
  border-radius: 8px;
  border: 1px solid #d9d9d9;
  padding: 10px;
  font-family: inherit;
  font-size: 14px;
  resize: vertical;
  overflow-y: auto;
  line-height: 1.6;
}
.result-head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.recheck-btn {
  padding: 4px 10px;
  font-size: 13px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.recheck-btn:hover:not(:disabled) {
  border-color: #1890ff;
  color: #1890ff;
}
.hits-section {
  margin-top: 16px;
  border-top: 1px solid #f0f0f0;
  padding-top: 12px;
}
.hits-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.hits-title {
  font-weight: 600;
  color: #cf1322;
  font-size: 0.95em;
}
.accept-all-btn {
  padding: 4px 12px;
  font-size: 13px;
  border: 1px solid #52c41a;
  border-radius: 4px;
  background: #fff;
  color: #389e0d;
  cursor: pointer;
}
.accept-all-btn:hover:not(:disabled) {
  background: #52c41a;
  color: #fff;
}
.accept-all-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.hits-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.hit-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: #fff7e6;
  border: 1px solid #ffd591;
  border-radius: 6px;
  font-size: 14px;
}
.hit-item.accepted {
  background: #f6ffed;
  border-color: #b7eb8f;
  opacity: 0.7;
}
.hit-word {
  font-weight: 600;
  color: #cf1322;
  min-width: 40px;
}
.accept-btn {
  margin-left: auto;
  padding: 2px 10px;
  font-size: 13px;
  border: 1px solid #52c41a;
  border-radius: 4px;
  background: #fff;
  color: #389e0d;
  cursor: pointer;
}
.accept-btn:hover:not(:disabled) {
  background: #52c41a;
  color: #fff;
}
.accept-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.hit-no-suggestion {
  color: #8c8c8c;
  font-size: 13px;
}
.no-hits {
  margin-top: 12px;
  color: #52c41a;
  font-size: 0.9em;
  text-align: center;
}
.hit-main {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.hit-context-inline {
  font-size: 13px;
  color: #555;
}
.ctx-before, .ctx-after {
  color: #888;
}
.ctx-word {
  color: #cf1322;
  font-weight: 600;
  background: #fff1f0;
  border-radius: 3px;
  padding: 0 2px;
}
.manual-input {
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 13px;
  width: 100px;
  outline: none;
}
.manual-input:focus {
  border-color: #1890ff;
}
</style>

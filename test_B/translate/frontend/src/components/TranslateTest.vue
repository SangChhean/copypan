<!-- test_B 纲目翻译练习页 · 对接 /api/test_b/translate/translate -->
<script setup>
import { ref, computed } from "vue";
import PageHeader from "./PageHeader.vue";

const apiBase = "";
const MAX_CONTENT_CHARS = 100_000;

// 第一层：中文 / 英文
const sourceLang = ref(null); // "zh" | "en" | null

// 第二层勾选
const zhChecks = ref({ zh2en: false, zh2ko: false });
const enChecks = ref({ en2zh: false, en2zhtw: false, en2es: false });

const content = ref("");
const loading = ref(false);
const error = ref(null);
const results = ref([]); // [{ label, text }]
const toast = ref("");

const inputPlaceholder = computed(() => {
  if (sourceLang.value === "en") return "请粘贴英文纲目全文…";
  if (sourceLang.value === "zh") return "请粘贴中文纲目全文…";
  return "请先选择翻译方向…";
});

const hasChecked = computed(() => {
  if (sourceLang.value === "zh") return Object.values(zhChecks.value).some(Boolean);
  if (sourceLang.value === "en") return Object.values(enChecks.value).some(Boolean);
  return false;
});

function selectSource(lang) {
  if (sourceLang.value === lang) return;
  sourceLang.value = lang;
  zhChecks.value = { zh2en: false, zh2ko: false };
  enChecks.value = { en2zh: false, en2zhtw: false, en2es: false };
  results.value = [];
  error.value = null;
}

function showToast(msg) {
  toast.value = msg;
  setTimeout(() => { if (toast.value === msg) toast.value = ""; }, 2500);
}

const DIRECTION_LABELS = {
  zh2en: "英文纲目",
  zh2ko: "韩文纲目",
  en2zh: "简体中文纲目",
  en2zhtw: "繁体中文纲目",
  en2es: "西班牙文纲目",
};

async function doFetch(direction) {
  const res = await fetch(`${apiBase}/api/test_b/translate/translate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content: content.value.trim(), direction }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    let detail = errorData.detail;
    if (Array.isArray(detail)) detail = detail.map(x => x?.msg || JSON.stringify(x)).join("；");
    throw new Error(detail || errorData.error || "翻译失败");
  }
  const data = await res.json();
  if (data.error && !data.result) throw new Error(data.error);
  return data.result;
}

async function translate() {
  const text = (content.value || "").trim();
  if (!text) { error.value = "请先粘贴纲目内容"; return; }
  if (text.length > MAX_CONTENT_CHARS) { error.value = `正文过长：最多 ${MAX_CONTENT_CHARS.toLocaleString()} 字`; return; }
  if (!hasChecked.value) { error.value = "请至少勾选一个翻译方向"; return; }

  loading.value = true;
  error.value = null;
  results.value = [];

  const checks = sourceLang.value === "zh" ? zhChecks.value : enChecks.value;
  const directions = Object.entries(checks).filter(([, v]) => v).map(([k]) => k);

  try {
    const settled = await Promise.allSettled(directions.map(dir => doFetch(dir)));
    settled.forEach((res, i) => {
      if (res.status === "fulfilled" && res.value) {
        results.value.push({ label: DIRECTION_LABELS[directions[i]], text: res.value });
      } else if (res.status === "rejected") {
        results.value.push({ label: DIRECTION_LABELS[directions[i]], text: null, error: res.reason?.message || "翻译失败" });
      }
    });
    showToast("翻译完成！");
  } catch (e) {
    error.value = e.message || "翻译失败，请稍后重试";
  } finally {
    loading.value = false;
  }
}

function copyText(text) {
  navigator.clipboard.writeText(text).then(() => showToast("已复制"));
}
</script>

<template>
  <PageHeader title="纲目翻译（test_B · ephesians）" />
  <div v-if="toast" class="toast">{{ toast }}</div>
  <div class="box">
    <section class="card">
      <p class="hint">
        独立练习环境：粘贴纲目后选择方向，点「翻译」即可（无下载、无登录）。
        <strong>输入上限 {{ MAX_CONTENT_CHARS.toLocaleString() }} 字</strong>。
      </p>
      <hr class="divider" />

      <!-- 第一层 -->
      <div class="direction-row">
        <span class="label">翻译方向：</span>
        <div class="direction-col">
          <div class="seg-row">
            <button type="button" class="seg-btn"
              :class="{ active: sourceLang === 'zh' }"
              @click="selectSource('zh')">中文</button>
            <button type="button" class="seg-btn"
              :class="{ active: sourceLang === 'en' }"
              @click="selectSource('en')">英文</button>
          </div>

          <!-- 中文子选项 -->
          <div v-if="sourceLang === 'zh'" class="check-row">
            <label class="check-label">
              <input type="checkbox" v-model="zhChecks.zh2en" :disabled="loading" />
              → 英文
            </label>
            <label class="check-label">
              <input type="checkbox" v-model="zhChecks.zh2ko" :disabled="loading" />
              → 韩文
            </label>
          </div>

          <!-- 英文子选项 -->
          <div v-if="sourceLang === 'en'" class="check-row">
            <label class="check-label">
              <input type="checkbox" v-model="enChecks.en2zh" :disabled="loading" />
              → 中文简体
            </label>
            <label class="check-label">
              <input type="checkbox" v-model="enChecks.en2zhtw" :disabled="loading" />
              → 中文繁体
            </label>
            <label class="check-label">
              <input type="checkbox" v-model="enChecks.en2es" :disabled="loading" />
              → 西班牙语
            </label>
          </div>
        </div>
      </div>

      <hr class="divider" />
      <div class="textarea-wrap">
        <textarea
          v-model="content"
          :placeholder="inputPlaceholder"
          rows="12"
          class="content-area"
          :disabled="loading"
          :maxlength="MAX_CONTENT_CHARS"
        />
        <div class="count-row">
          <span class="char-count">{{ (content || "").length.toLocaleString() }} / {{ MAX_CONTENT_CHARS.toLocaleString() }}</span>
          <button type="button" class="clear-btn" :disabled="!content || loading" @click="content = ''; results = []">清空</button>
        </div>
      </div>
      <div class="action-row">
        <button type="button" class="action-btn"
          :disabled="loading || !content.trim() || !hasChecked"
          @click="translate">
          <span v-if="loading" class="spin">⟳</span>
          <span>{{ loading ? "翻译中…" : "翻译" }}</span>
        </button>
      </div>
      <p v-if="loading" class="loading-hint">请耐心等待 1～2 分钟</p>
    </section>

    <p v-if="error" class="error">{{ error }}</p>

    <!-- 结果区 -->
    <div v-if="results.length > 0" class="results-grid">
      <section v-for="(r, idx) in results" :key="idx" class="card result-card">
        <div class="result-head">
          <span>{{ r.label }}</span>
          <button v-if="r.text" type="button" class="copy-btn" @click="copyText(r.text)">复制</button>
        </div>
        <p v-if="r.error" class="result-error">{{ r.error }}</p>
        <pre v-else class="result-body">{{ r.text }}</pre>
      </section>
    </div>
  </div>
</template>

<style scoped>
.toast {
  position: fixed; top: 12px; left: 50%; transform: translateX(-50%);
  background: rgba(0,0,0,0.75); color: #fff; padding: 8px 16px;
  border-radius: 6px; font-size: 14px; z-index: 1000;
}
.box { padding: 1em; max-width: 900px; margin: 0 auto; }
.card {
  background: #fff; border-radius: 8px; padding: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.hint { color: #555; margin: 0; font-size: 0.95em; line-height: 1.5; }
.divider { border: none; border-top: 1px solid #f0f0f0; margin: 12px 0; }
.direction-row { display: flex; align-items: flex-start; gap: 12px; flex-wrap: wrap; }
.direction-row .label { font-weight: 600; color: #333; padding-top: 8px; }
.direction-col { display: flex; flex-direction: column; gap: 10px; flex: 1; }
.seg-row { display: flex; gap: 8px; flex-wrap: wrap; }
.seg-btn {
  padding: 8px 24px; font-weight: 500; font-size: 15px;
  border: 2px solid #d9d9d9; border-radius: 6px; background: #fafafa; cursor: pointer;
}
.seg-btn:hover { border-color: #722ed1; color: #531dab; }
.seg-btn.active { background: #722ed1; border-color: #722ed1; color: #fff; }
.check-row { display: flex; gap: 16px; flex-wrap: wrap; padding-left: 2px; }
.check-label {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 14px; cursor: pointer; color: #333;
}
.check-label input[type="checkbox"] { width: 16px; height: 16px; cursor: pointer; }
.textarea-wrap { margin-top: 8px; }
.content-area {
  width: 100%; box-sizing: border-box; border-radius: 8px;
  border: 1px solid #d9d9d9; padding: 10px; font-family: inherit;
  font-size: 14px; resize: vertical;
}
.count-row { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; }
.char-count { font-size: 13px; color: #888; }
.clear-btn {
  padding: 6px 16px; font-size: 14px; border: 1px solid #d9d9d9;
  border-radius: 6px; background: #fff; cursor: pointer;
}
.clear-btn:hover:not(:disabled) { color: #ff4d4f; border-color: #ff4d4f; }
.clear-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.action-row { margin-top: 16px; padding-top: 12px; border-top: 1px solid #f0f0f0; display: flex; justify-content: center; }
.action-btn {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 8px 24px; font-size: 16px; border-radius: 6px;
  border: none; background: #1890ff; color: #fff; cursor: pointer;
}
.action-btn:hover:not(:disabled) { background: #40a9ff; }
.action-btn:disabled { opacity: 0.65; cursor: not-allowed; }
.spin { display: inline-block; animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
.loading-hint { margin: 8px 0 0; color: #8c8c8c; font-size: 0.9em; text-align: center; }
.error { margin-top: 12px; color: #cf1322; }
.results-grid { margin-top: 20px; display: flex; flex-wrap: wrap; gap: 16px; }
.results-grid .result-card { flex: 1; min-width: 280px; }
.result-head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 12px; font-weight: 600;
}
.copy-btn {
  padding: 4px 10px; font-size: 13px; border: 1px solid #d9d9d9;
  border-radius: 4px; background: #fff; cursor: pointer;
}
.copy-btn:hover { border-color: #1890ff; color: #1890ff; }
.result-error { color: #cf1322; margin: 0; }
.result-body {
  white-space: pre-wrap; word-break: break-word; margin: 0;
  font-size: 0.95em; line-height: 1.6; max-height: 60vh; overflow-y: auto;
}
</style>

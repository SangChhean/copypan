<script setup>
import { ref, computed } from "vue";
import { message } from "ant-design-vue";
import ToolsHeader from "./ToolsHeader.vue";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";
const MAX_CONTENT_CHARS = 100_000;

const sourceLang = ref(null);

const zhChecks = ref({ zh2en: false, zh2ko: false });
const enChecks = ref({ en2zh: false, en2zhtw: false, en2es: false });

const content = ref("");
const loading = ref(false);
const results = ref([]);
const checking = ref(false);

// 易错字检查
async function checkErrors(resultItem) {
  if (!resultItem.text) return;
  resultItem.checking = true;
  resultItem.hits = [];
  try {
    const res = await fetch(`${apiBase}/api/testb/check_errors`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: resultItem.text }),
    });
    const data = await res.json();
    resultItem.hits = (data.hits || []).map(h => ({
      ...h, accepted: false, manualInput: h.suggestion || ""
    }));
  } catch (e) {
    message.error("易错字检查失败");
  } finally {
    resultItem.checking = false;
  }
}

function getContext(hit, text) {
  if (!text) return { before: "", word: "", after: "" };
  const pos = hit.positions[0];
  const start = Math.max(0, pos - 5);
  const end = Math.min(text.length, pos + hit.word.length + 5);
  return {
    before: text.slice(start, pos),
    word: text.slice(pos, pos + hit.word.length),
    after: text.slice(pos + hit.word.length, end),
  };
}

function acceptManual(hit, resultItem) {
  const val = (hit.manualInput || "").trim();
  if (!val || !resultItem.text) return;
  resultItem.text = resultItem.text.replaceAll(hit.word, val);
  hit.accepted = true;
  message.success(`已替换：${hit.word} → ${val}`);
}

function acceptAll(resultItem) {
  if (!resultItem.text) return;
  let text = resultItem.text;
  let count = 0;
  const toAccept = [...resultItem.hits]
    .filter(h => h.manualInput && !h.accepted)
    .sort((a, b) => b.word.length - a.word.length);
  for (const hit of toAccept) {
    if (text.includes(hit.word)) {
      text = text.replaceAll(hit.word, hit.manualInput);
      hit.accepted = true;
      count++;
    }
  }
  resultItem.text = text;
  message.success(`已接受 ${count} 条建议`);
}

const inputPlaceholder = computed(() => {
  if (sourceLang.value === "en") return "请粘贴英文纲目正文…";
  if (sourceLang.value === "zh") return "请粘贴中文纲目正文…";
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
  if (!text) { message.error("请先粘贴纲目正文"); return; }
  if (text.length > MAX_CONTENT_CHARS) { message.error(`正文过长：最多 ${MAX_CONTENT_CHARS.toLocaleString()} 字，请分段翻译`); return; }
  if (!hasChecked.value) { message.error("请至少勾选一个翻译方向"); return; }

  loading.value = true;
  results.value = [];

  const checks = sourceLang.value === "zh" ? zhChecks.value : enChecks.value;
  const directions = Object.entries(checks).filter(([, v]) => v).map(([k]) => k);

  try {
    const settled = await Promise.allSettled(directions.map(dir => doFetch(dir)));
    const newResults = [];
    settled.forEach((res, i) => {
      if (res.status === "fulfilled" && res.value) {
        newResults.push({
          label: DIRECTION_LABELS[directions[i]],
          text: res.value,
          direction: directions[i],
          hits: [],
          checking: false,
        });
      } else {
        newResults.push({
          label: DIRECTION_LABELS[directions[i]],
          text: null,
          direction: directions[i],
          error: res.reason?.message || "翻译失败",
          hits: [],
          checking: false,
        });
      }
    });
    results.value = newResults;
    message.success("翻译完成！");
    // 繁体结果自动触发易错字检查
    for (const r of results.value) {
      if (r.direction === "en2zhtw" && r.text) {
        checkErrors(r);
      }
    }
  } catch (e) {
    message.error(e.message || "翻译失败，请稍后重试");
  } finally {
    loading.value = false;
  }
}

function copyResult(text) {
  navigator.clipboard.writeText(text).then(() => message.success("已复制"));
}
</script>

<template>
  <ToolsHeader title="纲目翻译测试" />
  <div class="box">
    <a-card>
      <p class="hint">
        粘贴纲目正文后选择方向，点「翻译」即可。<strong>输入上限
        {{ MAX_CONTENT_CHARS.toLocaleString() }} 字</strong>，过长请分段翻译。
      </p>
      <a-divider :style="{ margin: '12px 0' }" />

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

      <a-divider :style="{ margin: '12px 0' }" />
      <div class="textarea-wrap">
        <a-textarea
          v-model:value="content"
          :placeholder="inputPlaceholder"
          :disabled="loading"
          :maxlength="MAX_CONTENT_CHARS"
          show-count
          allow-clear
          class="content-area"
        />
      </div>
      <div class="action-row">
        <button type="button" class="action-btn clear-btn"
          :disabled="loading || !content"
          @click="content = ''; results = []">清空</button>
        <button type="button" class="action-btn"
          :disabled="loading || !content.trim() || !hasChecked"
          @click="translate">
          <span v-if="loading" class="spin">⟳</span>
          <span>{{ loading ? "翻译中…" : "翻译" }}</span>
        </button>
      </div>
      <p v-if="loading" class="loading-hint">请耐心等待 1～2 分钟</p>
    </a-card>

    <div v-if="results.length > 0" class="results-grid">
      <a-card v-for="(r, idx) in results" :key="idx" class="result-card">
        <template #title>
          <span>{{ r.label }}</span>
          <button v-if="r.text" type="button" class="copy-btn" @click="copyResult(r.text)">
            复制
          </button>
        </template>
        <p v-if="r.error" class="result-error">{{ r.error }}</p>
        <template v-else>
          <textarea v-model="r.text" class="result-area" />
          <!-- 易错字区域（仅繁体） -->
          <template v-if="r.direction === 'en2zhtw'">
            <div class="hits-header" v-if="r.hits && r.hits.length > 0">
              <span class="hits-title">发现 {{ r.hits.length }} 处易错字</span>
              <div style="display:flex;gap:8px;align-items:center;">
                <button type="button" class="recheck-btn"
                  :disabled="r.checking" @click="checkErrors(r)">
                  <span v-if="r.checking" class="spin">⟳</span>
                  {{ r.checking ? "检查中…" : "重新检查" }}
                </button>
                <button type="button" class="accept-all-btn"
                  :disabled="r.hits.filter(h => h.manualInput && !h.accepted).length === 0"
                  @click="acceptAll(r)">全部接受</button>
              </div>
            </div>
            <div v-else-if="r.checking" class="loading-hint">正在检查易错字…</div>
            <div v-else-if="r.hits && r.hits.length === 0 && !r.checking && r.text" class="no-hits">未发现易错字 ✓</div>
            <div v-if="r.hits && r.hits.length > 0" class="hits-list">
              <div v-for="(hit, hidx) in r.hits" :key="hidx"
                class="hit-item" :class="{ accepted: hit.accepted }">
                <div class="hit-main">
                  <span class="hit-context-inline" v-if="!hit.accepted">
                    <span class="ctx-before">…{{ getContext(hit, r.text).before }}</span>
                    <span class="ctx-word">{{ getContext(hit, r.text).word }}</span>
                    <span class="ctx-after">{{ getContext(hit, r.text).after }}…</span>
                  </span>
                  <input v-model="hit.manualInput" class="manual-input"
                    :placeholder="'替换为…'" :disabled="hit.accepted" />
                  <button type="button" class="accept-btn"
                    :disabled="hit.accepted || !hit.manualInput.trim()"
                    @click="acceptManual(hit, r)">
                    {{ hit.accepted ? "已接受" : "接受" }}
                  </button>
                </div>
              </div>
            </div>
          </template>
        </template>
      </a-card>
    </div>
  </div>
</template>

<style scoped>
.box {
  padding: 1em;
  max-width: 900px;
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
.direction-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}
.direction-row .label {
  font-weight: 600;
  color: #333;
  font-size: 1em;
  padding-top: 8px;
}
.direction-col {
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex: 1;
}
.seg-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.seg-btn {
  padding: 8px 24px;
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
.check-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  padding-left: 2px;
}
.check-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  cursor: pointer;
  color: #333;
}
.check-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
}
.textarea-wrap { margin-top: 8px; }
.content-area :deep(.ant-input) {
  border-radius: 8px;
  font-family: inherit;
  height: calc(100vh - 420px) !important;
  min-height: 400px !important;
  resize: none !important;
  overflow-y: auto !important;
}
.action-row {
  margin-top: 16px;
  padding: 12px 0;
  border-top: 1px solid #f0f0f0;
  display: flex;
  justify-content: center;
  gap: 12px;
}
.loading-hint {
  margin: 8px 0 0;
  color: #8c8c8c;
  font-size: 0.9em;
  text-align: center;
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
.action-btn:hover:not(:disabled) { background: #40a9ff; }
.action-btn:disabled { opacity: 0.65; cursor: not-allowed; }
.clear-btn {
  background: #fff;
  color: #555;
  border: 1px solid #d9d9d9;
}
.clear-btn:hover:not(:disabled) {
  background: #fff;
  color: #ff4d4f;
  border-color: #ff4d4f;
}
.spin { display: inline-block; animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
.results-grid {
  margin-top: 20px;
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}
.results-grid .result-card { flex: 1; min-width: 280px; }
.results-grid :deep(.ant-card-head) {
  display: flex;
  align-items: center;
}
.copy-btn {
  margin-left: auto;
  padding: 4px 10px;
  font-size: 13px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  color: #555;
}
.copy-btn:hover { color: #1890ff; border-color: #1890ff; }
.result-error { color: #cf1322; margin: 0; }
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
.hits-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 12px 0 8px;
}
.hits-title { font-weight: 600; color: #cf1322; font-size: 0.95em; }
.recheck-btn {
  padding: 4px 10px; font-size: 13px; border: 1px solid #d9d9d9;
  border-radius: 4px; background: #fff; cursor: pointer;
  display: inline-flex; align-items: center; gap: 4px;
}
.recheck-btn:hover:not(:disabled) { border-color: #1890ff; color: #1890ff; }
.accept-all-btn {
  padding: 4px 12px; font-size: 13px; border: 1px solid #52c41a;
  border-radius: 4px; background: #fff; color: #389e0d; cursor: pointer;
}
.accept-all-btn:hover:not(:disabled) { background: #52c41a; color: #fff; }
.accept-all-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.no-hits { margin-top: 10px; color: #52c41a; font-size: 0.9em; text-align: center; }
.hits-list { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
.hit-item {
  display: flex; align-items: center; padding: 6px 10px;
  background: #fff7e6; border: 1px solid #ffd591; border-radius: 6px;
}
.hit-item.accepted { background: #f6ffed; border-color: #b7eb8f; opacity: 0.7; }
.hit-main { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; width: 100%; }
.hit-context-inline { font-size: 13px; color: #555; }
.ctx-before, .ctx-after { color: #888; }
.ctx-word { color: #cf1322; font-weight: 600; background: #fff1f0; border-radius: 3px; padding: 0 2px; }
.manual-input {
  border: 1px solid #d9d9d9; border-radius: 4px; padding: 2px 8px;
  font-size: 13px; width: 100px; outline: none;
}
.manual-input:focus { border-color: #1890ff; }
.accept-btn {
  margin-left: auto; padding: 2px 10px; font-size: 13px;
  border: 1px solid #52c41a; border-radius: 4px; background: #fff; color: #389e0d; cursor: pointer;
}
.accept-btn:hover:not(:disabled) { background: #52c41a; color: #fff; }
.accept-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>

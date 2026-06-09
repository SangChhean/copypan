<script setup>
import { ref, computed, reactive } from "vue";

const apiBase = "";

// 三类纲目
const feastOutlineTypes = [
  { label: "晨兴信息选读的纲目", value: "morning_revival" },
  { label: "听抄稿的纲目", value: "transcript" },
  { label: "复合的纲目", value: "composite" },
];

const selectedTypes = ref([]);

// 输入区
const inputLine1 = ref("");
const inputLine2 = ref("");
const inputLine3 = ref("");
const inputOutline = ref("");
const inputMorningRevival = ref("");
const inputTranscript = ref("");
const inputTranscriptPreface = ref("");
const inputTranscriptAddendum = ref("");
const inputMorningRevivalOutline = ref("");

// 状态
const loading = ref(false);
const results = reactive({
  morning_revival: { content: "", loading: false, error: "" },
  transcript:      { content: "", loading: false, error: "" },
  composite:       { content: "", loading: false, error: "" },
});
const prefaceOutline = ref("");
const addendumOutline = ref("");
const errors = ref([]);

function toggleType(value) {
  const i = selectedTypes.value.indexOf(value);
  if (i > -1) selectedTypes.value.splice(i, 1);
  else selectedTypes.value.push(value);
}

function canGenerate() {
  const o = inputOutline.value.trim();
  const m = inputMorningRevival.value.trim();
  const t = inputTranscript.value.trim();
  const mo = inputMorningRevivalOutline.value.trim();
  if (selectedTypes.value.length === 0) return false;
  if (selectedTypes.value.includes("morning_revival") && !m && !mo) return false;
  if (selectedTypes.value.includes("transcript") && (!o || !t)) return false;
  if (selectedTypes.value.includes("composite")) {
    if (!o || !t) return false;
    if (!mo && !m) return false;
  }
  return true;
}

function resetResults() {
  for (const key of ["morning_revival", "transcript", "composite"]) {
    results[key].content = "";
    results[key].loading = false;
    results[key].error = "";
  }
  prefaceOutline.value = "";
  addendumOutline.value = "";
  errors.value = [];
}

async function postJson(path, body) {
  const res = await fetch(`${apiBase}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  let data = {};
  try { data = JSON.parse(text); } catch {}
  return { ok: res.ok, status: res.status, data };
}

async function generateAll() {
  if (!canGenerate()) return;
  resetResults();
  loading.value = true;

  const o  = inputOutline.value.trim();
  const m  = inputMorningRevival.value.trim();
  const t  = inputTranscript.value.trim();
  const mo = inputMorningRevivalOutline.value.trim();
  const tp = inputTranscriptPreface.value.trim();
  const ta = inputTranscriptAddendum.value.trim();

  try {
    // ── Step 1：并发跑晨兴和听抄稿 ──

    const runMorningRevival = async () => {
      // 若勾了晨兴但填了⑥，直接用⑥内容，不调接口
      if (selectedTypes.value.includes("morning_revival") && mo) {
        results.morning_revival.content = mo;
        return mo;
      }
      // 不需要晨兴接口（未勾晨兴，且复合稿也已有⑥），直接返回
      const needMorningApi =
        (selectedTypes.value.includes("morning_revival") && !mo && m) ||
        (selectedTypes.value.includes("composite") && !mo && m);
      if (!needMorningApi) return mo || "";

      results.morning_revival.loading = true;
      try {
        const { ok, data } = await postJson(
          "/api/testc/feast_outline/morning_revival",
          { content: m }
        );
        const outline = (data.outline || "").trim();
        if (ok && outline) {
          if (selectedTypes.value.includes("morning_revival")) {
            results.morning_revival.content = outline;
          }
          return outline;
        }
        const msg = data.detail || data.error || "生成失败";
        if (selectedTypes.value.includes("morning_revival")) {
          results.morning_revival.error = msg;
        }
        errors.value.push(`晨兴信息选读的纲目：${msg}`);
        return "";
      } finally {
        results.morning_revival.loading = false;
      }
    };

    const runTranscript = async () => {
      const need =
        selectedTypes.value.includes("transcript") ||
        selectedTypes.value.includes("composite");
      if (!need || !o || !t) return "";

      results.transcript.loading = true;
      try {
        const body = { original_outline: o, transcript: t };
        if (tp) body.transcript_preface = tp;
        if (ta) body.transcript_addendum = ta;
        const { ok, data } = await postJson(
          "/api/testc/feast_outline/transcript",
          body
        );
        const outline = (data.outline || "").trim();
        if (ok && outline) {
          if (selectedTypes.value.includes("transcript")) {
            results.transcript.content = outline;
          }
          if (data.preface_outline) prefaceOutline.value = data.preface_outline.trim();
          if (data.addendum_outline) addendumOutline.value = data.addendum_outline.trim();
          return outline;
        }
        const msg = data.detail || data.error || "生成失败";
        if (selectedTypes.value.includes("transcript")) {
          results.transcript.error = msg;
        }
        errors.value.push(`听抄稿的纲目：${msg}`);
        return "";
      } finally {
        results.transcript.loading = false;
      }
    };

    const [morningRevivalOutline, transcriptOutline] = await Promise.all([
      runMorningRevival(),
      runTranscript(),
    ]);

    // ── Step 2：复合稿串行，依赖 Step 1 ──

    if (selectedTypes.value.includes("composite")) {
      const mrForComposite = morningRevivalOutline || mo;
      if (mrForComposite && transcriptOutline) {
        results.composite.loading = true;
        try {
          const { ok, data } = await postJson(
            "/api/testc/feast_outline/composite",
            {
              morning_revival_outline: mrForComposite,
              transcript_outline: transcriptOutline,
            }
          );
          const outline = (data.outline || "").trim();
          if (ok && outline) {
            results.composite.content = outline;
          } else {
            const msg = data.detail || data.error || "生成失败";
            results.composite.error = msg;
            errors.value.push(`复合的纲目：${msg}`);
          }
        } finally {
          results.composite.loading = false;
        }
      } else {
        results.composite.error = "需先成功生成听抄稿纲目与晨兴纲目";
        errors.value.push("复合的纲目：依赖项未就绪，已跳过");
      }
    }
  } finally {
    loading.value = false;
  }
}

function copyText(text) {
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => alert("已复制到剪贴板"));
}

const hasAnyResult = computed(() =>
  Object.values(results).some((r) => r.content) ||
  prefaceOutline.value ||
  addendumOutline.value
);
</script>

<template>
  <div class="page">
    <div class="page-title">节期纲目制作练习</div>

    <!-- 类型多选 -->
    <div class="section">
      <div class="section-label">选择类型（可多选）</div>
      <div class="type-buttons">
        <button
          v-for="t in feastOutlineTypes"
          :key="t.value"
          :class="['type-btn', selectedTypes.includes(t.value) ? 'type-btn--active' : '']"
          @click="toggleType(t.value)"
        >
          {{ t.label }}
        </button>
      </div>
    </div>

    <!-- 前三行 -->
    <div class="section">
      <div class="field">
        <label class="field-label">第一行</label>
        <input
          v-model="inputLine1"
          class="input-text"
          placeholder="特会系列：如：二〇二六年国殇节"
        />
      </div>
      <div class="field">
        <label class="field-label">第二行</label>
        <input
          v-model="inputLine2"
          class="input-text"
          placeholder="极其需要新的复兴"
        />
      </div>
      <div class="field">
        <label class="field-label">第三行</label>
        <input
          v-model="inputLine3"
          class="input-text"
          placeholder="第一篇　与主合作带进新的复兴，以结束这个世代"
        />
      </div>
    </div>

    <!-- 输入区 -->
    <div class="section">
      <div class="field">
        <label class="field-label">① 纲目原文</label>
        <textarea
          v-model="inputOutline"
          class="textarea"
          rows="6"
          placeholder="请粘贴纲目原文（无格式）；用于听抄稿的纲目"
        />
      </div>
      <div class="field">
        <label class="field-label">② 晨兴信息选读</label>
        <textarea
          v-model="inputMorningRevival"
          class="textarea"
          rows="6"
          placeholder="请粘贴晨兴信息选读内容；用于晨兴信息选读的纲目及复合的纲目"
        />
      </div>
      <div class="field">
        <label class="field-label">③ 听抄稿</label>
        <textarea
          v-model="inputTranscript"
          class="textarea"
          rows="6"
          placeholder="请粘贴听抄稿内容；用于听抄稿的纲目及复合的纲目"
        />
      </div>
      <div class="field">
        <label class="field-label">④ 听抄稿序言 <span class="optional">可选</span></label>
        <textarea
          v-model="inputTranscriptPreface"
          class="textarea"
          rows="3"
          placeholder="生成节期纲目时一并交给 Claude 做成序言纲目，并用于听抄稿/复合稿"
        />
      </div>
      <div class="field">
        <label class="field-label">⑤ 听抄稿添言 <span class="optional">可选</span></label>
        <textarea
          v-model="inputTranscriptAddendum"
          class="textarea"
          rows="3"
          placeholder="生成节期纲目时一并交给 Claude 做成添言纲目，并用于听抄稿/复合稿"
        />
      </div>
      <div class="field">
        <label class="field-label">
          ⑥ 已有晨兴纲目
          <span class="optional">可选 · 有此项时复合稿直接使用，无需重新生成</span>
        </label>
        <textarea
          v-model="inputMorningRevivalOutline"
          class="textarea"
          rows="5"
          placeholder="如晨兴信息选读的纲目已提前做好，可直接粘贴于此；复合稿生成时将跳过晨兴纲目的 AI 生成步骤"
        />
      </div>
    </div>

    <!-- 生成按钮 -->
    <button
      class="generate-btn"
      :disabled="!canGenerate() || loading"
      @click="generateAll"
    >
      {{ loading ? "生成中…" : "生成节期纲目" }}
    </button>

    <!-- 错误提示 -->
    <div v-if="errors.length" class="error-box">
      <div v-for="(e, i) in errors" :key="i">{{ e }}</div>
    </div>

    <!-- 结果区 -->
    <div v-if="hasAnyResult" class="results">

      <!-- 晨兴信息选读的纲目 -->
      <div
        v-if="selectedTypes.includes('morning_revival') || results.morning_revival.content"
        class="result-card"
      >
        <div class="result-header">
          <span class="result-title">晨兴信息选读的纲目</span>
          <button
            v-if="results.morning_revival.content"
            class="copy-btn"
            @click="copyText(results.morning_revival.content)"
          >复制</button>
        </div>
        <div v-if="results.morning_revival.loading" class="loading-text">生成中…</div>
        <div v-else-if="results.morning_revival.error" class="error-text">{{ results.morning_revival.error }}</div>
        <pre v-else-if="results.morning_revival.content" class="result-content">{{ results.morning_revival.content }}</pre>
      </div>

      <!-- 听抄稿的纲目 -->
      <div
        v-if="selectedTypes.includes('transcript') || results.transcript.content"
        class="result-card"
      >
        <div class="result-header">
          <span class="result-title">听抄稿的纲目</span>
          <button
            v-if="results.transcript.content"
            class="copy-btn"
            @click="copyText(results.transcript.content)"
          >复制</button>
        </div>
        <div v-if="results.transcript.loading" class="loading-text">生成中…</div>
        <div v-else-if="results.transcript.error" class="error-text">{{ results.transcript.error }}</div>
        <pre v-else-if="results.transcript.content" class="result-content">{{ results.transcript.content }}</pre>
      </div>

      <!-- 序言纲目 -->
      <div v-if="prefaceOutline" class="result-card result-card--sub">
        <div class="result-header">
          <span class="result-title">序言纲目</span>
          <button class="copy-btn" @click="copyText(prefaceOutline)">复制</button>
        </div>
        <pre class="result-content">{{ prefaceOutline }}</pre>
      </div>

      <!-- 添言纲目 -->
      <div v-if="addendumOutline" class="result-card result-card--sub">
        <div class="result-header">
          <span class="result-title">添言纲目</span>
          <button class="copy-btn" @click="copyText(addendumOutline)">复制</button>
        </div>
        <pre class="result-content">{{ addendumOutline }}</pre>
      </div>

      <!-- 复合的纲目 -->
      <div
        v-if="selectedTypes.includes('composite') || results.composite.content"
        class="result-card"
      >
        <div class="result-header">
          <span class="result-title">复合的纲目</span>
          <button
            v-if="results.composite.content"
            class="copy-btn"
            @click="copyText(results.composite.content)"
          >复制</button>
        </div>
        <div v-if="results.composite.loading" class="loading-text">等待听抄稿与晨兴纲目完成后生成…</div>
        <div v-else-if="results.composite.error" class="error-text">{{ results.composite.error }}</div>
        <pre v-else-if="results.composite.content" class="result-content">{{ results.composite.content }}</pre>
      </div>

    </div>
  </div>
</template>

<style scoped>
.page {
  max-width: 860px;
  margin: 0 auto;
  padding: 2em 1.5em 4em;
  background: #f7f5f0;
  min-height: 100vh;
}

.page-title {
  font-size: 1.5em;
  font-weight: 700;
  color: #2c5f8a;
  margin-bottom: 1.5em;
}

.section {
  background: #fff;
  border-radius: 8px;
  padding: 1.2em 1.4em;
  margin-bottom: 1.2em;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

.section-label {
  font-weight: 600;
  color: #2c5f8a;
  margin-bottom: 0.8em;
}

.type-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.type-btn {
  padding: 6px 16px;
  border: 2px solid #2c5f8a;
  border-radius: 6px;
  background: #fff;
  color: #2c5f8a;
  font-size: 0.95em;
  cursor: pointer;
  transition: all 0.15s;
}

.type-btn--active {
  background: #2c5f8a;
  color: #fff;
}

.type-btn:hover {
  opacity: 0.85;
}

.field {
  margin-bottom: 1em;
}

.field:last-child {
  margin-bottom: 0;
}

.field-label {
  display: block;
  font-weight: 600;
  color: #444;
  margin-bottom: 4px;
  font-size: 0.95em;
}

.optional {
  font-weight: normal;
  color: #999;
  font-size: 0.88em;
  margin-left: 6px;
}

.input-text,
.textarea {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #d0ccc4;
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 0.95em;
  font-family: inherit;
  background: #faf9f7;
  color: #333;
  resize: vertical;
  transition: border-color 0.15s;
}

.input-text::placeholder,
.textarea::placeholder {
  color: #bbb;
}

.input-text:focus,
.textarea:focus {
  outline: none;
  border-color: #2c5f8a;
}

.generate-btn {
  width: 100%;
  padding: 12px;
  background: #2c5f8a;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 1.05em;
  font-weight: 600;
  cursor: pointer;
  margin-bottom: 1.2em;
  transition: opacity 0.15s;
}

.generate-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.generate-btn:not(:disabled):hover {
  opacity: 0.88;
}

.error-box {
  background: #fff2f0;
  border: 1px solid #ffccc7;
  border-radius: 6px;
  padding: 10px 14px;
  color: #cf1322;
  font-size: 0.9em;
  margin-bottom: 1.2em;
  line-height: 1.7;
}

.results {
  display: flex;
  flex-direction: column;
  gap: 1.2em;
}

.result-card {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.07);
  overflow: hidden;
}

.result-card--sub {
  border-left: 4px solid #d0ccc4;
}

.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid #f0ece4;
  background: #faf9f7;
}

.result-title {
  font-weight: 600;
  color: #2c5f8a;
  font-size: 0.95em;
}

.copy-btn {
  padding: 3px 12px;
  border: 1px solid #2c5f8a;
  border-radius: 4px;
  background: #fff;
  color: #2c5f8a;
  font-size: 0.85em;
  cursor: pointer;
  transition: all 0.15s;
}

.copy-btn:hover {
  background: #2c5f8a;
  color: #fff;
}

.loading-text {
  padding: 16px 14px;
  color: #888;
  font-size: 0.9em;
}

.error-text {
  padding: 16px 14px;
  color: #cf1322;
  font-size: 0.9em;
}

.result-content {
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: inherit;
  font-size: 0.9em;
  line-height: 1.7;
  margin: 0;
  padding: 14px;
  max-height: 500px;
  overflow-y: auto;
  color: #333;
}
</style>

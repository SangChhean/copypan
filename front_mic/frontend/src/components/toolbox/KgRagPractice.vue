<template>
  <div class="container">
    <button class="btn btn-back" type="button" @click="goBack">← 返回</button>
    <h1 class="title">AI 纲目制作练习</h1>

    <!-- Tab 切换 -->
    <div class="tab-row">
      <button
        type="button"
        class="btn btn-tab"
        :class="{ active: activeTab === '2.0' }"
        @click="activeTab = '2.0'"
      >PanAI 2.0</button>
      <button
        type="button"
        class="btn btn-tab"
        :class="{ active: activeTab === '3.5' }"
        @click="activeTab = '3.5'"
      >PanAI 3.5</button>
    </div>

    <!-- ══════════════════════════════════════
         PanAI 2.0 面板（原有，完全不变）
    ══════════════════════════════════════ -->
    <div v-if="activeTab === '2.0'">
      <label class="label">纲目主题</label>
      <input
        v-model="query"
        class="input"
        type="text"
        placeholder="请输入纲目主题"
        :disabled="loading"
      />
      <label class="label">纲目性质</label>
      <div class="nature-row">
        <button
          v-for="opt in natureOptions"
          :key="opt"
          type="button"
          class="btn btn-nature"
          :class="{ active: outlineNature === opt }"
          :disabled="loading"
          @click="outlineNature = opt"
        >{{ opt }}</button>
      </div>
      <label class="label">负担说明（可选）</label>
      <textarea
        v-model="burdenDescription"
        class="textarea"
        rows="4"
        placeholder="可填写负担说明…"
        :disabled="loading"
      />
      <div class="btn-row">
        <button class="btn btn-primary" type="button" :disabled="loading" @click="generate">
          {{ loading ? "生成中…" : "生成纲目" }}
        </button>
      </div>
      <p v-if="emptyError" class="error-msg">请先输入纲目主题</p>
      <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>
      <div v-if="result" class="result-box">
        <div class="result-header">
          <span>生成结果</span>
          <button class="btn btn-copy" type="button" @click="copyResult">
            {{ copied ? "已复制" : "复制" }}
          </button>
        </div>
        <pre class="result-pre">{{ result }}</pre>
        <FormatDownloadBar
          :text="fullText()"
          direction="zh"
          api-endpoint="/api/practice/kg_rag/format_download"
        />
      </div>
    </div>

    <!-- ══════════════════════════════════════
         PanAI 3.5 面板（新增）
    ══════════════════════════════════════ -->
    <div v-if="activeTab === '3.5'">

      <!-- 阶段一：基本信息 -->
      <label class="label">纲目主题 <span class="required">*</span></label>
      <input
        v-model="query35"
        class="input"
        type="text"
        placeholder="请输入纲目主题"
        :disabled="loading35"
      />

      <label class="label">纲目性质 <span class="required">*</span></label>
      <div class="nature-row">
        <button
          v-for="opt in natureOptions"
          :key="opt"
          type="button"
          class="btn btn-nature"
          :class="{ active: outlineNature35 === opt }"
          :disabled="loading35"
          @click="outlineNature35 = opt"
        >{{ opt }}</button>
      </div>

      <!-- 阶段二：负担说明区 -->
      <div class="burden-card" v-if="!burdenSkipped">
        <div class="burden-card-header">
          <span class="burden-card-title">负担说明的生成</span>
          <button type="button" class="btn-skip" @click="skipBurden" :disabled="loading35">
            跳过负担说明
          </button>
        </div>

        <label class="label-sm">原稿请贴这里</label>
        <textarea
          v-model="draftText"
          class="textarea"
          rows="4"
          placeholder="有原稿直接生成负担说明，无原稿可生成三个负担说明以供选择"
          :disabled="loading35 || showStep3"
        />

        <div class="btn-row">
          <button
            class="btn btn-primary"
            type="button"
            :disabled="loading35 || !query35.trim() || showStep3"
            @click="generateBurden"
          >{{ burdenLoading ? "生成中…" : "生成负担说明" }}</button>
        </div>

        <!-- 无原稿：3条候选 -->
        <div v-if="burdenCandidates.length > 0 && !draftText.trim()" class="candidates-box">
          <label class="label-sm">请选择一条负担说明：</label>
          <div
            v-for="(c, i) in burdenCandidates"
            :key="i"
            class="candidate-item"
            :class="{ selected: selectedCandidate === i }"
            @click="selectCandidate(i)"
          >{{ c }}</div>
        </div>

        <!-- 负担说明编辑框（始终显示，可直接输入或由生成结果填入） -->
        <label class="label-sm">生成的负担说明</label>
        <textarea
          v-model="burdenResult"
          class="textarea"
          rows="3"
          placeholder="在此输入或编辑负担说明，也可留空"
          :disabled="loading35 || showStep3"
        />

        <div class="btn-row" v-if="!showStep3">
          <button
            class="btn btn-primary"
            type="button"
            :disabled="loading35 || !query35.trim()"
            @click="confirmBurden"
          >确认，开始推荐重点</button>
        </div>
      </div>

      <!-- 阶段三：推荐重点 + 生成（点击确认或跳过后显示） -->
      <div v-if="showStep3">
        <div class="step3-card">

          <!-- 概念词可编辑区 -->
          <div v-if="step1Done || revelation35.length || experience35.length || practice35.length" class="concepts-edit-box">
            <div class="concepts-row" v-if="revelation35.length">
              <span class="concept-layer-label">启示</span>
              <span
                v-for="(w, i) in revelation35"
                :key="'rev-'+i"
                class="concept-tag c-revelation"
              >{{ w }}<button type="button" class="tag-remove" @click="revelation35.splice(i,1)">×</button></span>
            </div>
            <div class="concepts-row" v-if="experience35.length">
              <span class="concept-layer-label">经历</span>
              <span
                v-for="(w, i) in experience35"
                :key="'exp-'+i"
                class="concept-tag c-experience"
              >{{ w }}<button type="button" class="tag-remove" @click="experience35.splice(i,1)">×</button></span>
            </div>
            <div class="concepts-row" v-if="practice35.length">
              <span class="concept-layer-label">实行</span>
              <span
                v-for="(w, i) in practice35"
                :key="'pra-'+i"
                class="concept-tag c-practice"
              >{{ w }}<button type="button" class="tag-remove" @click="practice35.splice(i,1)">×</button></span>
            </div>
          </div>

          <label class="label-sm">搜索图谱中重点</label>
          <p class="hint-text">直接输入重点，回车添加，× 删除。</p>
          <input
            v-model="extraNode"
            class="input"
            type="text"
            placeholder="输入概念词后按回车添加"
            :disabled="loading35"
            @keydown.enter.prevent="addExtraNode"
          />
          <div class="concepts-row extra-row" v-if="extraNodes35.length">
            <span
              v-for="(w, i) in extraNodes35"
              :key="'extra-'+i"
              class="concept-tag c-extra"
            >{{ w }}<button type="button" class="tag-remove" @click="extraNodes35.splice(i,1)">×</button></span>
          </div>

          <div class="checkbox-row">
            <label class="checkbox-label">
              <input type="checkbox" v-model="genEnglish" :disabled="loading35" />
              同时生成英文纲目
            </label>
            <label class="checkbox-label">
              <input type="checkbox" v-model="genTraditional" :disabled="loading35" />
              同时生成繁体纲目
            </label>
          </div>

          <div class="btn-row">
            <button
              class="btn btn-secondary"
              type="button"
              :disabled="loading35 || !query35.trim()"
              @click="runStep1"
            >{{ step1Loading ? "推荐中…" : "推荐重点" }}</button>
            <button
              class="btn btn-primary"
              type="button"
              :disabled="loading35 || !query35.trim()"
              @click="generate35"
            >{{ generateLoading35 ? "生成中…" : "生成纲目" }}</button>
          </div>

          <p v-if="errorMsg35" class="error-msg">{{ errorMsg35 }}</p>
        </div>

        <!-- 生成结果 -->
        <div v-if="result35" class="result-box">
          <div class="result-header">
            <span>生成结果（PanAI 3.5）</span>
            <button class="btn btn-copy" type="button" @click="copyResult35">
              {{ copied35 ? "已复制" : "复制" }}
            </button>
          </div>
          <pre class="result-pre">{{ result35 }}</pre>
          <FormatDownloadBar
            :text="fullText35()"
            direction="zh"
            api-endpoint="/api/practice/kg_rag/format_download"
          />
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";
import FormatDownloadBar from "./FormatDownloadBar.vue";

const natureOptions = ["一般性", "真理启示", "生命经历", "应用实行"];

// ── Tab ──────────────────────────────────────────────────────
const activeTab = ref("2.0");

// ── PanAI 2.0 状态（原有，完全不变）────────────────────────────
const query = ref("");
const outlineNature = ref("一般性");
const burdenDescription = ref("");
const result = ref("");
const loading = ref(false);
const emptyError = ref(false);
const errorMsg = ref("");
const copied = ref(false);

function goBack() {
  window.location.hash = "/tools";
}
function fullText() {
  const topic = query.value.trim();
  const body = result.value || "";
  return topic ? `${topic}\n\n${body}` : body;
}
async function generate() {
  emptyError.value = false;
  errorMsg.value = "";
  result.value = "";
  if (!query.value.trim()) { emptyError.value = true; return; }
  loading.value = true;
  try {
    const res = await fetch("/api/practice/kg_rag/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query.value.trim(),
        outline_nature: outlineNature.value,
        burden_description: burdenDescription.value.trim(),
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) errorMsg.value = data.detail || data.error || `请求失败（${res.status}）`;
    else if (data.error) errorMsg.value = data.error;
    else if (data.answer) result.value = data.answer;
    else errorMsg.value = "未返回纲目内容";
  } catch (e) {
    errorMsg.value = e?.message || "网络错误，请稍后重试";
  } finally {
    loading.value = false;
  }
}
async function copyResult() {
  if (!result.value) return;
  try {
    await navigator.clipboard.writeText(result.value);
    copied.value = true;
    setTimeout(() => { copied.value = false; }, 2000);
  } catch (_) {}
}

// ── PanAI 3.5 状态 ────────────────────────────────────────────
const query35 = ref("");
const outlineNature35 = ref("一般性");
const draftText = ref("");
const burdenResult = ref("");
const burdenCandidates = ref([]);
const selectedCandidate = ref(-1);
const burdenSkipped = ref(false);
const showStep3 = ref(false);

const revelation35 = ref([]);
const experience35 = ref([]);
const practice35 = ref([]);
const expandedNodes35 = ref([]);
const rewrittenQueries35 = ref([]);
const extraNode = ref("");
const extraNodes35 = ref([]);

function addExtraNode() {
  const val = extraNode.value.trim();
  if (val && !extraNodes35.value.includes(val)) {
    extraNodes35.value.push(val);
  }
  extraNode.value = "";
}

const step1Loading = ref(false);
const step1Done = ref(false);

const genEnglish = ref(false);
const genTraditional = ref(false);
const burdenLoading = ref(false);
const generateLoading35 = ref(false);
const result35 = ref("");
const errorMsg35 = ref("");
const copied35 = ref(false);

const loading35 = ref(false);

function fullText35() {
  const topic = query35.value.trim();
  const body = result35.value || "";
  return topic ? `${topic}\n\n${body}` : body;
}

function skipBurden() {
  burdenSkipped.value = true;
  showStep3.value = true;
}

function confirmBurden() {
  showStep3.value = true;
}

function selectCandidate(i) {
  selectedCandidate.value = i;
  burdenResult.value = burdenCandidates.value[i];
}

async function generateBurden() {
  if (!query35.value.trim()) return;
  burdenLoading.value = true;
  loading35.value = true;
  burdenCandidates.value = [];
  burdenResult.value = "";
  selectedCandidate.value = -1;
  try {
    const res = await fetch("/api/practice/kg_rag/burden", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query35.value.trim(),
        outline_nature: outlineNature35.value,
        draft_text: draftText.value.trim(),
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      errorMsg35.value = data.detail || `请求失败（${res.status}）`;
    } else if (data.burdens && data.burdens.length > 0) {
      if (draftText.value.trim()) {
        burdenResult.value = data.burdens[0];
      } else {
        burdenCandidates.value = data.burdens;
      }
    }
  } catch (e) {
    errorMsg35.value = e?.message || "网络错误";
  } finally {
    burdenLoading.value = false;
    loading35.value = false;
  }
}

async function runStep1() {
  if (!query35.value.trim()) return;
  step1Loading.value = true;
  loading35.value = true;
  errorMsg35.value = "";
  revelation35.value = [];
  experience35.value = [];
  practice35.value = [];
  step1Done.value = false;
  try {
    const res = await fetch("/api/practice/kg_rag/step1", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query35.value.trim(),
        outline_nature: outlineNature35.value,
        burden_description: burdenResult.value.trim(),
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      errorMsg35.value = data.detail || `请求失败（${res.status}）`;
    } else {
      revelation35.value = data.revelation || [];
      experience35.value = data.experience || [];
      practice35.value = data.practice || [];
      expandedNodes35.value = data.expanded_nodes || [];
      rewrittenQueries35.value = data.rewritten_queries || [];
      step1Done.value = true;
    }
  } catch (e) {
    errorMsg35.value = e?.message || "网络错误";
  } finally {
    step1Loading.value = false;
    loading35.value = false;
  }
}

async function generate35() {
  if (!query35.value.trim()) return;
  generateLoading35.value = true;
  loading35.value = true;
  errorMsg35.value = "";
  result35.value = "";
  const nodes = [...expandedNodes35.value, ...extraNodes35.value];
  try {
    const res = await fetch("/api/practice/kg_rag/query35", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query35.value.trim(),
        outline_nature: outlineNature35.value,
        burden_description: burdenResult.value.trim(),
        expanded_nodes: nodes,
        rewritten_queries: rewrittenQueries35.value,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) errorMsg35.value = data.detail || `请求失败（${res.status}）`;
    else if (data.error) errorMsg35.value = data.error;
    else if (data.answer) result35.value = data.answer;
    else errorMsg35.value = "未返回纲目内容";
  } catch (e) {
    errorMsg35.value = e?.message || "网络错误";
  } finally {
    generateLoading35.value = false;
    loading35.value = false;
  }
}

async function copyResult35() {
  if (!result35.value) return;
  try {
    await navigator.clipboard.writeText(result35.value);
    copied35.value = true;
    setTimeout(() => { copied35.value = false; }, 2000);
  } catch (_) {}
}
</script>

<style scoped>
:global(body) { background-color: #f7f5f0; }

.container {
  max-width: 920px;
  margin: 0 auto;
  padding: 28px 24px;
  background: #f7f5f0;
  color: #2d2d2d;
  font-family: sans-serif;
}
.title {
  font-size: 22px;
  font-weight: 700;
  color: #2d2d2d;
  text-align: center;
  margin-bottom: 24px;
  padding-bottom: 12px;
  border-bottom: 2px solid #dde3e9;
}

/* Tab */
.tab-row {
  display: flex;
  gap: 8px;
  margin-bottom: 28px;
}
.btn-tab {
  padding: 8px 28px;
  font-size: 15px;
  font-weight: 500;
  border: 1.5px solid #dde3e9;
  border-radius: 6px;
  background: #fff;
  color: #555;
  cursor: pointer;
  transition: all 0.2s ease;
}
.btn-tab:hover:not(.active) {
  border-color: #2c5f8a;
  color: #2c5f8a;
}
.btn-tab.active {
  background: #2c5f8a;
  color: #fff;
  border-color: #2c5f8a;
}

/* 通用表单元素 */
.label {
  display: block;
  margin-bottom: 8px;
  font-weight: 600;
  color: #2d2d2d;
  font-size: 15px;
}
.label-sm {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  color: #444;
  font-size: 14px;
}
.required { color: #c0392b; margin-left: 2px; }
.input {
  width: 100%;
  box-sizing: border-box;
  padding: 12px 16px;
  font-size: 15px;
  line-height: 1.6;
  margin-bottom: 20px;
  border: 1.5px solid #dde3e9;
  border-radius: 8px;
  background: #fdfcfb;
  color: #2d2d2d;
  outline: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.input:focus { border-color: #2c5f8a; box-shadow: 0 0 0 3px rgba(44,95,138,0.1); }
.input:disabled { opacity: 0.65; cursor: not-allowed; }
.nature-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; }
.btn-nature {
  padding: 8px 20px;
  font-size: 14px;
  font-weight: 500;
  border: 1.5px solid #dde3e9;
  border-radius: 20px;
  background: #fff;
  color: #555;
  cursor: pointer;
  transition: all 0.2s ease;
}
.btn-nature:hover:not(.active):not(:disabled) { border-color: #2c5f8a; color: #2c5f8a; }
.btn-nature.active { background: #2c5f8a; color: #fff; border-color: #2c5f8a; box-shadow: 0 2px 6px rgba(44,95,138,0.25); }
.btn-nature:disabled { opacity: 0.65; cursor: not-allowed; }
.textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 12px 16px;
  font-size: 15px;
  line-height: 1.8;
  margin-bottom: 16px;
  border: 1.5px solid #dde3e9;
  border-radius: 8px;
  background: #fdfcfb;
  color: #2d2d2d;
  resize: vertical;
  outline: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.textarea:focus { border-color: #2c5f8a; box-shadow: 0 0 0 3px rgba(44,95,138,0.1); }
.textarea:disabled { opacity: 0.65; cursor: not-allowed; }
.btn-row { display: flex; gap: 12px; margin-top: 8px; margin-bottom: 16px; }
.btn { cursor: pointer; transition: all 0.2s ease; }
.btn-primary {
  background: #2c5f8a; color: #fff; font-weight: 500;
  border-radius: 6px; padding: 10px 36px; font-size: 16px; border: none;
}
.btn-primary:hover:not(:disabled) { background: #1e4a6e; }
.btn-primary:disabled { opacity: 0.65; cursor: not-allowed; }
.btn-secondary {
  background: #fff; color: #2c5f8a; font-weight: 500;
  border-radius: 6px; padding: 10px 28px; font-size: 16px;
  border: 1.5px solid #2c5f8a;
}
.btn-secondary:hover:not(:disabled) { background: #e8f0f7; }
.btn-secondary:disabled { opacity: 0.65; cursor: not-allowed; }
.btn-back {
  background: transparent; color: #6b6b6b;
  border: 1.5px solid #dde3e9; border-radius: 6px;
  padding: 6px 14px; font-size: 13px; margin-bottom: 20px; cursor: pointer;
}
.btn-back:hover { border-color: #2c5f8a; color: #2c5f8a; }
.btn-copy {
  border: 1.5px solid #2c5f8a; color: #2c5f8a;
  background: #fff; border-radius: 4px; padding: 5px 14px; font-size: 12px; cursor: pointer;
}
.btn-copy:hover { background: #e8f0f7; }
.btn-skip {
  background: none; border: none; color: #2c5f8a;
  font-size: 13px; cursor: pointer; text-decoration: underline; padding: 0;
}
.btn-skip:hover { color: #1e4a6e; }
.btn-skip:disabled { opacity: 0.5; cursor: not-allowed; }

/* 负担说明卡片 */
.burden-card {
  border: 1.5px dashed #b8c8d8;
  border-radius: 10px;
  padding: 20px;
  margin-bottom: 20px;
  background: #f0f5fa;
}
.burden-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.burden-card-title {
  font-weight: 600;
  color: #2c5f8a;
  font-size: 15px;
}

/* 候选负担说明 */
.candidates-box { margin-bottom: 16px; }
.candidate-item {
  padding: 12px 16px;
  margin-bottom: 8px;
  border: 1.5px solid #dde3e9;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  font-size: 14px;
  line-height: 1.7;
  color: #2d2d2d;
  transition: all 0.2s ease;
}
.candidate-item:hover { border-color: #2c5f8a; background: #eef4fa; }
.candidate-item.selected { border-color: #2c5f8a; background: #ddeaf5; font-weight: 500; }

/* 阶段三卡片 */
.step3-card {
  border: 1.5px solid #dde3e9;
  border-radius: 10px;
  padding: 20px;
  margin-bottom: 20px;
  background: #fff;
}

/* 概念词展示 */
.concepts-box { margin-bottom: 20px; }
.concepts-row { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.concept-layer-label {
  font-size: 12px; font-weight: 600; color: #888;
  min-width: 28px; margin-right: 4px;
}
.concept-tag {
  padding: 3px 10px; border-radius: 12px;
  font-size: 13px; font-weight: 500;
}
.c-revelation { background: #e8eef7; color: #2c5f8a; border: 1px solid #b8cde0; }
.c-experience  { background: #e8f5ee; color: #1e6e44; border: 1px solid #a8d4b8; }
.c-practice    { background: #fef3e2; color: #8a5c1a; border: 1px solid #e0c890; }
.c-extra { background: #f3eef8; color: #6b3fa0; border: 1px solid #d0b8e8; }
.tag-remove {
  background: none; border: none; cursor: pointer;
  margin-left: 4px; padding: 0 2px;
  font-size: 12px; line-height: 1;
  color: inherit; opacity: 0.6;
}
.tag-remove:hover { opacity: 1; }
.hint-text { font-size: 12px; color: #888; margin: -4px 0 8px; }
.extra-row { margin-top: 8px; }

/* checkbox */
.checkbox-row { display: flex; gap: 24px; margin-bottom: 16px; }
.checkbox-label { display: flex; align-items: center; gap: 6px; font-size: 14px; color: #444; cursor: pointer; }
.checkbox-label input { cursor: pointer; }

/* 结果区 */
.result-box {
  margin-top: 24px; padding: 20px;
  border: 1px solid #dde3e9; border-radius: 10px;
  background: #ffffff; box-shadow: 0 2px 12px rgba(44,95,138,0.08);
}
.result-header {
  color: #2c5f8a; font-weight: 600; font-size: 14px;
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;
}
.result-pre {
  white-space: pre-wrap; line-height: 1.8;
  color: #2d2d2d; font-size: 15px; margin: 0; font-family: inherit;
}

/* 错误提示 */
.error-msg { color: #c0392b; margin-top: 8px; font-size: 13px; }
</style>

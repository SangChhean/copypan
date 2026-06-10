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

        <label class="label-sm">参考摘录（可选）</label>
        <textarea
          v-model="referenceExcerpt"
          class="textarea"
          rows="8"
          placeholder="可选：粘贴一段参考摘录，有摘录生成1条负担说明（情境A），无摘录生成3条候选（情境B）"
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
        <div v-if="burdenCandidates.length > 0 && !referenceExcerpt.trim()" class="candidates-box">
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
          rows="6"
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

          <!-- 概念词勾选编辑区 -->
          <div v-if="step1Done || revelation35.length || experience35.length || practice35.length" class="concepts-edit-box">

            <!-- 启示层 -->
            <div class="concepts-row-wrap">
              <span class="concept-layer-label">启示</span>
              <div class="concepts-row">
                <label
                  v-for="(w, i) in revelation35"
                  :key="'rev-'+i"
                  class="concept-tag c-revelation"
                  :class="{ unchecked: !revelationChecked[i] }"
                >
                  <input type="checkbox" v-model="revelationChecked[i]" class="tag-checkbox" />
                  {{ w }}
                </label>
                <div class="tag-input-wrap">
                  <input
                    v-model="newRevelation"
                    class="tag-inline-input"
                    placeholder="+ 添加重点词"
                    @keydown.enter.prevent="addToLayer('revelation')"
                  />
                </div>
              </div>
            </div>

            <!-- 经历层 -->
            <div class="concepts-row-wrap">
              <span class="concept-layer-label">经历</span>
              <div class="concepts-row">
                <label
                  v-for="(w, i) in experience35"
                  :key="'exp-'+i"
                  class="concept-tag c-experience"
                  :class="{ unchecked: !experienceChecked[i] }"
                >
                  <input type="checkbox" v-model="experienceChecked[i]" class="tag-checkbox" />
                  {{ w }}
                </label>
                <div class="tag-input-wrap">
                  <input
                    v-model="newExperience"
                    class="tag-inline-input"
                    placeholder="+ 添加重点词"
                    @keydown.enter.prevent="addToLayer('experience')"
                  />
                </div>
              </div>
            </div>

            <!-- 实行层 -->
            <div class="concepts-row-wrap">
              <span class="concept-layer-label">实行</span>
              <div class="concepts-row">
                <label
                  v-for="(w, i) in practice35"
                  :key="'pra-'+i"
                  class="concept-tag c-practice"
                  :class="{ unchecked: !practiceChecked[i] }"
                >
                  <input type="checkbox" v-model="practiceChecked[i]" class="tag-checkbox" />
                  {{ w }}
                </label>
                <div class="tag-input-wrap">
                  <input
                    v-model="newPractice"
                    class="tag-inline-input"
                    placeholder="+ 添加重点词"
                    @keydown.enter.prevent="addToLayer('practice')"
                  />
                </div>
              </div>
            </div>

          </div>

          <!-- Query Rewrite 改写句（验证用） -->
          <div v-if="rewrittenDisplay.length" class="rewrite-box">
            <div class="rewrite-title">查询改写（验证用）</div>
            <div
              v-for="(s, i) in rewrittenDisplay"
              :key="i"
              class="rewrite-item"
            >
              <span class="rewrite-angle">{{ ['启示', '真理', '经历', '应用'][i] }}</span>
              {{ s }}
            </div>
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
          <div v-if="expandedSummary" class="expanded-summary">{{ expandedSummary }}</div>
          <div v-if="skeletonStatus" class="skeleton-status" :class="hasSkeleton35 ? 'has-skeleton' : 'no-skeleton'">
            {{ skeletonStatus }}
          </div>
          <div v-if="hasSkeleton35 && skeletonPreview35.length" class="skeleton-preview">
            <div v-for="(s, i) in skeletonPreview35" :key="i" class="skeleton-step">
              第{{ i + 1 }}步：{{ s }}
            </div>
          </div>
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
const referenceExcerpt = ref("");
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

const step1Loading = ref(false);
const step1Done = ref(false);

const revelationChecked = ref([]);
const experienceChecked = ref([]);
const practiceChecked = ref([]);
const newRevelation = ref("");
const newExperience = ref("");
const newPractice = ref("");

function addToLayer(layer) {
  if (layer === 'revelation') {
    const val = newRevelation.value.trim();
    if (val && !revelation35.value.includes(val)) {
      revelation35.value.push(val);
      revelationChecked.value.push(true);
    }
    newRevelation.value = "";
  } else if (layer === 'experience') {
    const val = newExperience.value.trim();
    if (val && !experience35.value.includes(val)) {
      experience35.value.push(val);
      experienceChecked.value.push(true);
    }
    newExperience.value = "";
  } else if (layer === 'practice') {
    const val = newPractice.value.trim();
    if (val && !practice35.value.includes(val)) {
      practice35.value.push(val);
      practiceChecked.value.push(true);
    }
    newPractice.value = "";
  }
}

const genEnglish = ref(false);
const genTraditional = ref(false);
const burdenLoading = ref(false);
const generateLoading35 = ref(false);
const result35 = ref("");
const expandedSummary = ref("");
const hasSkeleton35 = ref(false)
const skeletonSteps35 = ref(0)
const skeletonPreview35 = ref([])
const skeletonStatus = ref("")
const rewrittenDisplay = ref([]);
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
        audience: "",
        reference_excerpt: referenceExcerpt.value.trim(),
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      errorMsg35.value = data.detail || `请求失败（${res.status}）`;
    } else if (data.scenario === 'A' && data.result) {
      burdenResult.value = data.result;
      burdenCandidates.value = [];
    } else if (data.scenario === 'B' && data.candidates && data.candidates.length > 0) {
      burdenCandidates.value = data.candidates;
      burdenResult.value = "";
    } else if (data.error) {
      errorMsg35.value = data.error;
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
      revelationChecked.value = data.revelation.map(() => true);
      experienceChecked.value = data.experience.map(() => true);
      practiceChecked.value = data.practice.map(() => true);
      expandedNodes35.value = data.expanded_nodes || [];
      rewrittenQueries35.value = data.rewritten_queries || [];
      rewrittenDisplay.value = data.rewritten_queries || [];
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
  const nodes = [
    ...revelation35.value.filter((_, i) => revelationChecked.value[i] !== false),
    ...experience35.value.filter((_, i) => experienceChecked.value[i] !== false),
    ...practice35.value.filter((_, i) => practiceChecked.value[i] !== false),
  ];
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
        revelation: revelation35.value.filter((_, i) => revelationChecked.value[i] !== false),
        experience: experience35.value.filter((_, i) => experienceChecked.value[i] !== false),
        practice: practice35.value.filter((_, i) => practiceChecked.value[i] !== false),
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) errorMsg35.value = data.detail || `请求失败（${res.status}）`;
    else if (data.error) errorMsg35.value = data.error;
    else if (data.answer) {
      result35.value = data.answer;
      if (data.expanded_results_count !== undefined) {
        const ns = (data.expanded_from_nodes || []).join("、");
        expandedSummary.value = `路3查询：共找到 ${data.expanded_results_count} 个额外段落，来自概念词：${ns || "无"}`;
      }
      hasSkeleton35.value = !!data.has_skeleton;
      skeletonSteps35.value = data.skeleton_steps || 0;
      skeletonPreview35.value = data.skeleton_preview || [];
      skeletonStatus.value = data.has_skeleton
        ? `✅ 有骨架（${data.skeleton_steps} 步）`
        : "⚠️ 降级模式（无骨架）";
    }
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
  padding: 14px 16px;
  font-size: 16px;
  line-height: 1.9;
  margin-bottom: 16px;
  border: 1.5px solid #dde3e9;
  border-radius: 8px;
  background: #fdfcfb;
  color: #2d2d2d;
  resize: vertical;
  outline: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
  overflow-y: auto;
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
.concept-layer-label {
  font-size: 12px; font-weight: 600; color: #888;
  min-width: 28px; margin-right: 4px;
}
.c-revelation { background: #e8eef7; color: #2c5f8a; border: 1px solid #b8cde0; }
.c-experience  { background: #e8f5ee; color: #1e6e44; border: 1px solid #a8d4b8; }
.c-practice    { background: #fef3e2; color: #8a5c1a; border: 1px solid #e0c890; }
.concepts-row-wrap {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 12px;
}
.concepts-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.concept-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  user-select: none;
  transition: opacity 0.2s;
}
.concept-tag.unchecked {
  opacity: 0.35;
}
.tag-checkbox {
  width: 13px;
  height: 13px;
  cursor: pointer;
  accent-color: #2c5f8a;
}
.tag-input-wrap {
  display: inline-flex;
  align-items: center;
}
.tag-inline-input {
  border: 1px dashed #aaa;
  border-radius: 12px;
  padding: 3px 10px;
  font-size: 13px;
  color: #666;
  background: transparent;
  outline: none;
  width: 110px;
  transition: border-color 0.2s, width 0.2s;
}
.tag-inline-input:focus {
  border-color: #2c5f8a;
  width: 150px;
  color: #2d2d2d;
}

.rewrite-box {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #f0f5fa;
  border-radius: 8px;
  border: 1px solid #d0e0ee;
}
.rewrite-title {
  font-size: 12px;
  font-weight: 600;
  color: #2c5f8a;
  margin-bottom: 8px;
}
.rewrite-item {
  font-size: 13px;
  color: #444;
  line-height: 1.8;
}
.rewrite-angle {
  display: inline-block;
  min-width: 28px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  background: #2c5f8a;
  border-radius: 4px;
  padding: 1px 6px;
  margin-right: 6px;
  text-align: center;
}

/* checkbox */
.checkbox-row { display: flex; gap: 24px; margin-bottom: 16px; }
.checkbox-label { display: flex; align-items: center; gap: 6px; font-size: 14px; color: #444; cursor: pointer; }
.checkbox-label input { cursor: pointer; }

.expanded-summary {
  font-size: 13px;
  color: #666;
  background: #f5f5f0;
  border-radius: 6px;
  padding: 8px 14px;
  margin-bottom: 14px;
}
.skeleton-status {
  font-size: 13px;
  font-weight: 600;
  padding: 6px 14px;
  border-radius: 6px;
  margin-bottom: 10px;
}
.skeleton-status.has-skeleton {
  background: #e8f5ee;
  color: #1e6e44;
}
.skeleton-status.no-skeleton {
  background: #fef3e2;
  color: #8a5c1a;
}
.skeleton-preview {
  background: #f0f7f2;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 14px;
}
.skeleton-step {
  font-size: 13px;
  color: #2d4a38;
  line-height: 1.8;
}

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

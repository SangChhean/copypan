<!-- 【PanAI 新测试台】（原名【3.5测试用】）由 Search.vue 的「AI纲目制作面板」复制生成（只有 3.5；接口走 /api/t35test；历史记录用独立的 localStorage 键）。 -->
<script setup>
import { ref, computed, watch, reactive, onMounted, onUnmounted, nextTick } from "vue";
import { useRouter, useRoute } from "vue-router";
import { PushpinOutlined, CopyOutlined, CheckOutlined, DownloadOutlined, LoadingOutlined, ArrowLeftOutlined } from "@ant-design/icons-vue";
import axios from "axios";
import { tip } from "../utils/Dialog";
import { message } from "ant-design-vue";

// 【3.5测试用】本页自己的显示状态（0=什么都不显示；3/4/5/6 含义与主站一致）
// 【4.0】从 3.0 页面复制来的关键词搜索（调用主站 /api/search）及其变量、引文已于 2026-11-11 删除
const showInfo = ref(0);


// AI 问答相关状态
const loadingAI = ref(false);
const aiResult = ref(null);
const showAISources = ref(false); // 是否显示引用来源
const showAIAnswer = ref(false); // 是否显示AI答案
const aiLoadingText = ref("AI 正在分析问题..."); // 加载提示文本
// 暂封英文纲目功能，测试通过后改为 true
const ENGLISH_OUTLINE_FEATURE_ENABLED = true;
const includeEnglishOutline = ref(false); // 是否同时生成英文纲目
const answerEn = ref(null); // 英文纲目
const titleEn = ref(null); // 英文标题
const loadingEnglish = ref(false); // 正在生成英文纲目
const errorEnglish = ref(null); // 英文纲目生成失败信息
const aiAnswerEnCopied = ref(false); // 英文复制状态

const includeTraditionalOutline = ref(false); // 是否同时生成繁体纲目
const answerZhTw = ref(null); // 台湾繁体纲目
const loadingTraditional = ref(false); // 正在生成繁体纲目
const errorTraditional = ref(null); // 繁体纲目生成失败信息
const aiAnswerZhTwCopied = ref(false); // 繁体复制状态

// KG-RAG 返回结构化数据
const aiMeta = reactive({
  revelation: [],
  inner: [],
  experience: [],
  practice: [],
  skeleton: null,
  mainSources: [],
  totalElapsedMs: null,
  totalCostUsd: null,
  cached: false,
  cacheKey: null,
});

// 刷格式并下载（DOCX/PDF）
const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";
const downloadFormatsZh = ref([]);
const downloadFormatsEn = ref([]);
const downloadFormatsZhTw = ref([]);
const downloadingZh = ref(false);
const downloadingEn = ref(false);
const downloadingZhTw = ref(false);

const aiPanelVisible = ref(true);
/** 【4.0】只有一条流程（原 2.0 / 3.0 模式已于 2026-11-11 删除，原名“3.5”改名“4.0”） */
const PIPELINE_MODE = "4.0";
const aiModeDisplayText = computed(() => "PanAI 新测试台");
const KG_RAG_HISTORY_KEY = "t35test_history";
const EVAL_PREFILL_KEY = "t35test_eval_prefill";
const router = useRouter();
const route = useRoute();
const AI_NATURE_OPTIONS = ["综合性", "真理启示", "内在素质", "生命经历", "实行应用"];
const aiForm = reactive({
  outlineTopic: "",
  burdenDescription: "",
  specialNeeds: "",
});
const aiFormValid = computed(() => {
  const outline = aiForm.outlineTopic.trim().length > 0;
  const nature = aiForm.specialNeeds.trim().length > 0;
  return outline && nature;
});

// ---------- AI 生成负担说明 ----------
const referenceExcerpt = ref("");
const burdenPhaseReady = ref(false);
const burdenGenLoading = ref(false);
const burdenGenScenario = ref(null); // 'A' | 'B' | null
const burdenGenCandidates = ref([]);
const burdenSelectedIdx = ref(0);
const burdenGenLineA = ref("");
const burdenGenReasoning = ref(""); // 模型输出的思考过程（新测试台）
const burdenReasoningOpen = ref(false); // 思考过程折叠面板是否展开
/** 要点依据逐行加序号「N、」；按实际换行分行，保留原有行内容（含没有负担的重点时按候选分组的行） */
const burdenGenReasoningNumbered = computed(() => {
  const lines = (burdenGenReasoning.value || "").split("\n").filter((l) => l.trim() !== "");
  return lines.map((l, i) => `${i + 1}、${l}`).join("\n");
});
/** 跳过「跳过负担说明」后隐藏整块面板，直到纲目主题与跳过时不一致 */
const burdenHiddenBySkip = ref(false);
const burdenSkipTopicSnapshot = ref("");

const showBurdenPhasePanel = computed(() => {
  if (!burdenHiddenBySkip.value) return true;
  return aiForm.outlineTopic.trim() !== burdenSkipTopicSnapshot.value;
});

watch(
  () => aiForm.outlineTopic,
  () => {
    if (
      burdenHiddenBySkip.value &&
      aiForm.outlineTopic.trim() !== burdenSkipTopicSnapshot.value
    ) {
      burdenHiddenBySkip.value = false;
    }
  }
);

watch(
  () => [aiForm.outlineTopic, aiForm.specialNeeds, referenceExcerpt.value],
  () => {
    burdenPhaseReady.value = false;
    burdenGenScenario.value = null;
    burdenGenCandidates.value = [];
    burdenGenLineA.value = "";
    burdenGenReasoning.value = "";
  }
);

watch(burdenSelectedIdx, (idx) => {
  if (burdenGenScenario.value !== "B") return;
  const c = burdenGenCandidates.value[idx];
  if (c != null && String(c).trim() !== "") {
    aiForm.burdenDescription = c;
  }
});

function skipBurdenPhase() {
  if (burdenPhaseReady.value) return;
  aiForm.burdenDescription = "";
  burdenPhaseReady.value = true;
  burdenGenScenario.value = null;
  burdenGenCandidates.value = [];
  burdenGenLineA.value = "";
  burdenGenReasoning.value = "";
  burdenSelectedIdx.value = 0;
  burdenSkipTopicSnapshot.value = aiForm.outlineTopic.trim();
  burdenHiddenBySkip.value = true;
}

function confirmBurdenPhase() {
  if (burdenPhaseReady.value) return;
  burdenPhaseReady.value = true;
}

async function onGenerateBurden() {
  if (!aiForm.outlineTopic.trim() || !aiForm.specialNeeds.trim()) {
    tip("请先填写主题和纲目性质");
    return;
  }
  burdenGenLoading.value = true;
  try {
    const res = await axios.post("/api/t35test/generate_burden", {
      query: aiForm.outlineTopic.trim(),
      outline_nature: aiForm.specialNeeds.trim(),
      reference_excerpt: referenceExcerpt.value.trim(),
    });
    const d = res.data || {};
    console.debug("[KG-RAG BURDEN DEBUG] generate_burden response:", d);
    // Prompt 已经把「摘录」统一改成「负担的重点」了，这里留一道保险（万一模型偶尔还是吐出旧词）
    burdenGenReasoning.value = d.reasoning != null ? String(d.reasoning).trim().replaceAll("摘录", "负担的重点") : "";
    if (d.scenario === "A" && d.result != null && String(d.result).trim() !== "") {
      burdenGenScenario.value = "A";
      const line = String(d.result).trim();
      burdenGenLineA.value = line;
      aiForm.burdenDescription = line;
      return;
    }
    if (d.scenario === "B" && d.candidates && d.candidates.length) {
      burdenGenScenario.value = "B";
      burdenGenCandidates.value = d.candidates.slice(0, 4);
      burdenSelectedIdx.value = 0;
      const first = burdenGenCandidates.value[0];
      aiForm.burdenDescription = first != null ? String(first).trim() : "";
      return;
    }
    tip(d.error || "生成失败");
    burdenGenScenario.value = null;
  } catch (e) {
    console.error("[KG-RAG BURDEN DEBUG] generate_burden error:", {
      message: e?.message,
      response: e?.response?.data,
      status: e?.response?.status,
    });
    tip(e.response?.data?.error || e.message || "生成失败");
    burdenGenScenario.value = null;
  } finally {
    burdenGenLoading.value = false;
  }
}

// ---------- 两阶段概念抽取 ----------
const conceptStage = ref("idle"); // idle | candidates_ready
const conceptLoading = ref(false);
const conceptCandidates = ref(null);
const stepThinkingText = ref(""); // Step1 模型的思考文字（英文原文，新测试台，常为空——见说明）
const stepThinkingTextZh = ref(""); // 上面那段的中文翻译（另外调用翻译模型得到，可能为空）
const stepThinkingOpen = ref(false);
const stepDropped = ref([]); // 不在概念列表/最内在词库里，被丢弃的词：[{layer, word}]
const stepDroppedOpen = ref(false);
const stepTruncated = ref([]); // 词合法但这层选多了，按数量上限被截掉的词：[{layer, word}]
const stepTruncatedOpen = ref(false);
const stepSummaryOpen = ref(false); // 小结（即 summary，原 reasoning「推荐理由」）折叠面板是否展开
const selectedRevelation = ref([]);
const selectedInner = ref([]); // 内在素质（词汇待资料库上传）
const selectedExperience = ref([]);
const selectedPractice = ref([]);
const selectedKeyVerses = ref([]); // 关键圣经节（可选，人工取舍；默认不勾选）
/** 概念来源：ai = 勾选候选；manual = 三层 tag 手动输入（互斥） */
const conceptMode = ref("ai"); // 'ai' | 'manual'
const manualRevelation = ref([]);
const manualInner = ref([]);
const manualExperience = ref([]);
const manualPractice = ref([]);
const manualKeyVerses = ref([]); // 关键圣经节（可选）
const manualConceptOptions = reactive({
  revelation: [],
  inner: [],
  experience: [],
  practice: [],
});
const manualConceptLoading = reactive({
  revelation: false,
  inner: false,
  experience: false,
  practice: false,
});
const manualConceptSearchValue = reactive({
  revelation: "",
  inner: "",
  experience: "",
  practice: "",
});
const manualConceptTimers = {
  revelation: null,
  inner: null,
  experience: null,
  practice: null,
};
const conceptSearchKeyword = ref("");
const conceptSearchOptions = ref([]);
const conceptSearchLoading = ref(false);
const conceptSearchOpen = ref(false);
let conceptSearchTimer = null;
const historyDrawerOpen = ref(false);
const historyList = ref([]);
const currentRecordId = ref(null);
const isMobileView = ref(false);

function updateIsMobileView() {
  isMobileView.value = window.innerWidth <= 768;
}

/** 骨架 path_evidence 展示：去掉末尾「（N跳）」（兼容旧缓存 / 旧模型输出） */
function formatPathEvidenceDisplay(pe) {
  if (pe == null || pe === "") return "";
  return String(pe).replace(/（\d+跳）\s*$/u, "").trim();
}

/** 模型思考过程显示用：按空行分段，每段开头加两个全角空格缩进，方便复制粘贴时保留分段和缩进 */
function indentParagraphs(text) {
  if (!text) return "";
  return String(text)
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter((p) => p)
    .map((p) => "　　" + p)
    .join("\n\n");
}

function resetAiConceptState() {
  conceptStage.value = "idle";
  conceptCandidates.value = null;
  stepThinkingText.value = "";
  stepThinkingTextZh.value = "";
  stepDropped.value = [];
  stepTruncated.value = [];
  selectedRevelation.value = [];
  selectedInner.value = [];
  selectedExperience.value = [];
  selectedPractice.value = [];
  selectedKeyVerses.value = [];
}
function resetManualConceptState() {
  manualRevelation.value = [];
  manualInner.value = [];
  manualExperience.value = [];
  manualPractice.value = [];
  manualKeyVerses.value = [];
  manualConceptSearchValue.inner = "";
  manualConceptSearchValue.revelation = "";
  manualConceptSearchValue.experience = "";
  manualConceptSearchValue.practice = "";
  manualConceptOptions.revelation = [];
  manualConceptOptions.inner = [];
  manualConceptOptions.experience = [];
  manualConceptOptions.practice = [];
}
function setConceptMode(mode) {
  if (conceptMode.value === mode) return;
  conceptMode.value = mode;
  if (mode === "manual") {
    resetAiConceptState();
  } else {
    resetManualConceptState();
  }
}

function ensureAiConceptBuckets() {
  if (!conceptCandidates.value) {
    conceptCandidates.value = { revelation: [], inner: [], experience: [], practice: [] };
  }
  if (!Array.isArray(conceptCandidates.value.revelation)) conceptCandidates.value.revelation = [];
  if (!Array.isArray(conceptCandidates.value.inner)) conceptCandidates.value.inner = [];
  if (!Array.isArray(conceptCandidates.value.experience)) conceptCandidates.value.experience = [];
  if (!Array.isArray(conceptCandidates.value.practice)) conceptCandidates.value.practice = [];
  if (!Array.isArray(conceptCandidates.value.key_verses)) conceptCandidates.value.key_verses = [];
  if (conceptStage.value === "idle") {
    conceptStage.value = "candidates_ready";
  }
}

function onSelectConceptSearchOption(value) {
  const word = String(value || "").trim();
  if (!word) return;
  conceptSearchKeyword.value = word;
  conceptSearchOpen.value = false;
  conceptSearchOptions.value = [];
}

async function fetchConceptSearchOptions(keyword) {
  const key = String(keyword || "").trim();
  if (!key) {
    conceptSearchOptions.value = [];
    conceptSearchOpen.value = false;
    return;
  }
  conceptSearchLoading.value = true;
  try {
    const res = await axios.get("/api/t35test/concepts/search_v4", {
      params: { q: key, limit: 20 },
    });
    const rows = Array.isArray(res.data?.results) ? res.data.results : [];
    conceptSearchOptions.value = rows.map((item) => ({ value: String(item) }));
    conceptSearchOpen.value = conceptSearchOptions.value.length > 0;
  } catch (e) {
    conceptSearchOptions.value = [];
    conceptSearchOpen.value = false;
  } finally {
    conceptSearchLoading.value = false;
  }
}

async function fetchManualConceptOptions(layer, keyword) {
  const key = String(keyword || "").trim();
  // 内在素质用「最内在的词汇」，资料库还没上传，先不搜图谱概念（避免给出不对的候选）
  if (layer === "inner") {
    manualConceptOptions.inner = [];
    return;
  }
  if (!key) {
    manualConceptOptions[layer] = [];
    return;
  }
  manualConceptLoading[layer] = true;
  try {
    const res = await axios.get("/api/t35test/concepts/search", {
      params: { q: key, limit: 20 },
    });
    const rows = Array.isArray(res.data?.results) ? res.data.results : [];
    const selectedSet = new Set(
      (layer === "revelation"
        ? manualRevelation.value
        : layer === "inner"
          ? manualInner.value
          : layer === "experience"
            ? manualExperience.value
            : manualPractice.value
      ).map((x) => String(x).trim()).filter(Boolean)
    );
    manualConceptOptions[layer] = rows
      .map((item) => String(item).trim())
      .filter((item) => item && !selectedSet.has(item))
      .map((item) => ({ value: item }));
  } catch (e) {
    manualConceptOptions[layer] = [];
  } finally {
    manualConceptLoading[layer] = false;
  }
}

function onManualConceptSearch(layer, value) {
  const key = String(value || "").trim();
  manualConceptSearchValue[layer] = String(value || "");
  if (manualConceptTimers[layer]) clearTimeout(manualConceptTimers[layer]);
  if (!key) {
    manualConceptOptions[layer] = [];
    return;
  }
  manualConceptTimers[layer] = setTimeout(() => {
    fetchManualConceptOptions(layer, key);
  }, 300);
}

function onManualConceptSelect(layer) {
  manualConceptSearchValue[layer] = "";
  manualConceptOptions[layer] = [];
}

function addManualConceptValue(layer, value) {
  const v = String(value || "").trim();
  if (!v) return;
  const target =
    layer === "revelation"
      ? manualRevelation.value
      : layer === "inner"
        ? manualInner.value
        : layer === "experience"
          ? manualExperience.value
          : manualPractice.value;
  if (!target.includes(v)) target.push(v);
}

function onManualConceptInputKeydown(layer, event) {
  if (event.key !== "Enter") return;
  const inputValue = String(manualConceptSearchValue[layer] || "").trim();
  if (!inputValue) return;
  event.preventDefault();
  addManualConceptValue(layer, inputValue);
  onManualConceptSelect(layer);
}

watch(
  () => conceptMode.value,
  () => {
    conceptSearchKeyword.value = "";
    conceptSearchOptions.value = [];
    conceptSearchOpen.value = false;
  }
);

watch(conceptSearchKeyword, (val) => {
  if (conceptSearchTimer) clearTimeout(conceptSearchTimer);
  const key = String(val || "").trim();
  if (!key) {
    conceptSearchOptions.value = [];
    conceptSearchOpen.value = false;
    return;
  }
  conceptSearchTimer = setTimeout(() => {
    fetchConceptSearchOptions(key);
  }, 300);
});

watch(
  () => [aiForm.outlineTopic, aiForm.specialNeeds, aiForm.burdenDescription],
  () => {
    if (conceptStage.value !== "idle") {
      resetAiConceptState();
    }
    if (
      manualRevelation.value.length ||
      manualInner.value.length ||
      manualExperience.value.length ||
      manualPractice.value.length ||
      manualKeyVerses.value.length
    ) {
      resetManualConceptState();
    }
  }
);

async function extractConcepts() {
  const q = aiForm.outlineTopic.trim();
  if (!q) { tip("请填写纲目主题"); return; }
  if (!burdenPhaseReady.value) {
    tip("请先完成负担说明阶段（点「确认，开始推荐重点」）");
    return;
  }
  conceptLoading.value = true;
  try {
    const res = await axios.post("/api/t35test/extract_concepts", {
      query: q,
      outline_nature: aiForm.specialNeeds.trim(),
      burden_description: aiForm.burdenDescription.trim(),
    });
    const d = res.data || {};
    conceptCandidates.value = d;
    stepThinkingText.value = d.thinking_text != null ? String(d.thinking_text).trim() : "";
    stepThinkingTextZh.value = d.thinking_text_zh != null ? String(d.thinking_text_zh).trim() : "";
    stepDropped.value = Array.isArray(d.dropped) ? d.dropped : [];
    stepTruncated.value = Array.isArray(d.truncated) ? d.truncated : [];
    selectedRevelation.value = [...(d.revelation || [])];
    selectedInner.value = [...(d.inner || [])];
    selectedExperience.value = [...(d.experience || [])];
    selectedPractice.value = [...(d.practice || [])];
    selectedKeyVerses.value = []; // 关键圣经节是可选的，由人工根据纲目需求勾选
    conceptStage.value = "candidates_ready";
  } catch (e) {
    tip(e.response?.data?.error || e.message || "概念抽取失败");
  } finally {
    conceptLoading.value = false;
  }
}

const outlineGenerateDisabled = computed(() => {
  if (conceptMode.value === "manual") return manualRevelation.value.length === 0;
  return selectedRevelation.value.length === 0;
});

function setAiMode(m) {
  // 【3.5测试用】只有 3.5：点击 2.0 / 3.0 没有任何反应
}


function resetConceptState() {
  resetAiConceptState();
  resetManualConceptState();
}

function formatHistoryTime(ts) {
  const d = new Date(ts);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function loadHistory() {
  try {
    const raw = localStorage.getItem(KG_RAG_HISTORY_KEY);
    const arr = JSON.parse(raw || "[]");
    historyList.value = Array.isArray(arr) ? arr : [];
  } catch (e) {
    historyList.value = [];
  }
}

function persistHistory() {
  localStorage.setItem(KG_RAG_HISTORY_KEY, JSON.stringify(historyList.value));
}

const pendingConfirmCount = computed(
  () => historyList.value.filter((x) => x?.status === "待确认").length
);

function syncHistoryAnswerSkeleton(answerText) {
  const query = aiForm.outlineTopic.trim();
  const record = historyList.value.find(
    (r) => r.id === currentRecordId.value || r.query === query
  );
  if (!record) return;

  if (!currentRecordId.value) currentRecordId.value = record.id;
  const idx = historyList.value.findIndex((r) => r.id === record.id);
  if (idx < 0) return;

  historyList.value = historyList.value.map((item, i) =>
    i === idx
      ? {
          ...item,
          answer: answerText ?? aiResult.value?.answer ?? "",
          skeleton: Array.isArray(aiMeta.skeleton) ? [...aiMeta.skeleton] : [],
        }
      : item
  );
  persistHistory();
}

function buildEvalHistoryPayload(evalData) {
  if (!evalData) return null;
  return {
    scored_at: new Date().toLocaleString("zh-CN"),
    total_score: evalData.total_score,
    pansai_layer: evalData.pansai_layer ?? {
      F1: evalData.F1,
      F2: evalData.F2,
      F3: evalData.F3,
      F4: evalData.F4,
    },
    theology_layer: evalData.theology_layer ?? {
      T1: evalData.T1,
      T2: evalData.T2,
      T3: evalData.T3,
      T4: evalData.T4,
    },
    synthesis: evalData.synthesis ?? null,
  };
}

function writeEvalToHistory() {
  if (!evalResult.value) return;

  let targetId = currentRecordId.value
    ?? historyList.value.find((r) => r.query === aiForm.outlineTopic.trim())?.id
    ?? null;

  if (!targetId) {
    const cand = conceptCandidates.value || {};
    const record = {
      id: Date.now(),
      createdAt: formatHistoryTime(Date.now()),
      status: "已生成",
      query: aiForm.outlineTopic.trim(),
      outline_nature: aiForm.specialNeeds.trim(),
      burden_description: aiForm.burdenDescription.trim(),
      revelation: getConceptListForEval("revelation"),
      inner: getConceptListForEval("inner"),
      experience: getConceptListForEval("experience"),
      practice: getConceptListForEval("practice"),
      answer: aiResult.value?.answer ?? "",
      skeleton: Array.isArray(aiMeta.skeleton) ? [...aiMeta.skeleton] : [],
      eval: null,
    };
    currentRecordId.value = record.id;
    historyList.value = [record, ...historyList.value];
    targetId = record.id;
  }

  const idx = historyList.value.findIndex((r) => r.id === targetId);
  if (idx < 0) return;

  currentRecordId.value = targetId;
  const prev = historyList.value[idx];
  const next = {
    ...prev,
    status: "已生成",
    answer: aiResult.value?.answer ?? prev.answer ?? "",
    skeleton: Array.isArray(aiMeta.skeleton) ? [...aiMeta.skeleton] : prev.skeleton ?? [],
    eval: buildEvalHistoryPayload(evalResult.value),
  };
  historyList.value = historyList.value.map((item, i) => (i === idx ? next : item));
  persistHistory();
}

function saveCurrentToHistory() {
  const cand = conceptCandidates.value || {};
  // 保存 AI 推荐的完整四层，而非仅勾选项（载入后可在手工重点里看到全部）
  const record = {
    id: Date.now(),
    createdAt: formatHistoryTime(Date.now()),
    status: "待确认",
    query: aiForm.outlineTopic.trim(),
    outline_nature: aiForm.specialNeeds.trim(),
    burden_description: aiForm.burdenDescription.trim(),
    revelation: Array.isArray(cand.revelation) ? [...cand.revelation] : [],
    inner: Array.isArray(cand.inner) ? [...cand.inner] : [],
    experience: Array.isArray(cand.experience) ? [...cand.experience] : [],
    practice: Array.isArray(cand.practice) ? [...cand.practice] : [],
    key_verses: Array.isArray(cand.key_verses) ? [...cand.key_verses] : [],
    summary: cand.summary ?? cand.reasoning ?? "", // 小结（旧记录里叫 reasoning）
    thinking_text: stepThinkingText.value || "",
    thinking_text_zh: stepThinkingTextZh.value || "",
    dropped: Array.isArray(stepDropped.value) ? [...stepDropped.value] : [],
    truncated: Array.isArray(stepTruncated.value) ? [...stepTruncated.value] : [],
    answer: aiResult.value?.answer ?? "",
    skeleton: aiMeta.skeleton ?? [],
    eval: evalResult.value ? buildEvalHistoryPayload(evalResult.value) : null,
  };
  currentRecordId.value = record.id;
  historyList.value = [record, ...historyList.value];
  persistHistory();
  message.success("已保存全部推荐重点到历史记录");
}

// ---------- 纲目品质评估 ----------
const evalLoading = ref(false);
const evalResult = ref(null);
const skeletonSnapshot = ref([]);
const outlineEditing = ref(false);
const outlineEditVisible = ref(false);
const outlineEditReadonly = ref(false);
const editableAnswer = ref("");
const scriptureReplacementItems = ref([]);

const F_EVAL_META = [
  { key: "F1", title: "F1 重点覆盖度" },
  { key: "F2", title: "F2 负担吻合度" },
  { key: "F3", title: "F3 骨架吻合度" },
  { key: "F4", title: "F4 逻辑连贯性" },
];

const T1_L_KEYS = ["L1", "L2", "L3", "L4"];

const T1_L_META = [
  { key: "L1", label: "L1 字句层" },
  { key: "L2", label: "L2 语境层" },
  { key: "L3", label: "L3 经纶层" },
  { key: "L4", label: "L4 异象层" },
];
const T2_S_META = [
  { key: "S1", label: "①神圣启示" },
  { key: "S2", label: "②结晶意义" },
  { key: "S3", label: "③内里经历" },
  { key: "S4", label: "④团体建造" },
  { key: "S5", label: "⑤实行应用" },
  { key: "S6", label: "⑥终极目标" },
];
const T3_FRAMEWORK_META = {
  R系: [
    { key: "R1", label: "R1 启示核心" },
    { key: "R2", label: "R2 展开纵深" },
    { key: "R3", label: "R3 经纶骨架" },
    { key: "R4", label: "R4 异象落点" },
  ],
  E系: [
    { key: "E1", label: "E1 生命核心" },
    { key: "E2", label: "E2 经历进展" },
    { key: "E3", label: "E3 主观路径" },
    { key: "E4", label: "E4 建造目标" },
  ],
  P系: [
    { key: "P1", label: "P1 生命根基" },
    { key: "P2", label: "P2 路径层次" },
    { key: "P3", label: "P3 落地实行" },
    { key: "P4", label: "P4 团体建造" },
  ],
};

const SUGGESTED_CONCEPT_LABELS = {
  revelation: "启示层",
  inner: "内在素质层",
  experience: "经历层",
  practice: "实行层",
};

function getConceptListForEval(layer) {
  if (aiMeta[layer]?.length) return [...aiMeta[layer]];
  if (conceptMode.value === "manual") {
    if (layer === "revelation") return [...manualRevelation.value];
    if (layer === "inner") return [...manualInner.value];
    if (layer === "experience") return [...manualExperience.value];
    return [...manualPractice.value];
  }
  if (layer === "revelation") return [...selectedRevelation.value];
  if (layer === "inner") return [...selectedInner.value];
  if (layer === "experience") return [...selectedExperience.value];
  return [...selectedPractice.value];
}

function buildEvalPayload(overrides = {}) {
  const nature = aiForm.specialNeeds.trim();
  const natureMap = { 应用实行: "实行应用", 综合性: "一般性" }; // 应用实行 是旧历史记录里的旧名
  return {
    answer: editableAnswer.value || aiResult.value?.answer || "",
    query: aiForm.outlineTopic.trim(),
    outline_nature: natureMap[nature] || nature || "一般性",
    burden_description: aiForm.burdenDescription.trim(),
    revelation: getConceptListForEval("revelation"),
    inner: getConceptListForEval("inner"),
    experience: getConceptListForEval("experience"),
    practice: getConceptListForEval("practice"),
    skeleton: skeletonSnapshot.value.length
      ? [...skeletonSnapshot.value]
      : Array.isArray(aiMeta.skeleton)
        ? [...aiMeta.skeleton]
        : [],
    ...overrides,
  };
}

const evalPansaiLayer = computed(() => evalResult.value?.pansai_layer ?? {});
const evalTheologyLayer = computed(() => evalResult.value?.theology_layer ?? {});
const evalT1 = computed(() => evalTheologyLayer.value?.T1 ?? {});
const evalT2 = computed(() => evalTheologyLayer.value?.T2 ?? {});
const evalT3 = computed(() => evalTheologyLayer.value?.T3 ?? {});
const evalT4 = computed(() => evalTheologyLayer.value?.T4 ?? {});
const evalSynthesis = computed(() => evalResult.value?.synthesis ?? {});

const evalT3Meta = computed(() => {
  const ft = evalT3.value?.framework_type ?? "E系";
  return T3_FRAMEWORK_META[ft] ?? T3_FRAMEWORK_META.E系;
});

const frameworkTypeLabel = computed(() => {
  const map = {
    R系: "真理启示",
    E系: "生命经历",
    P系: "实行应用",
  };
  return map[evalT3.value?.framework_type] ?? evalT3.value?.framework_type;
});

const evalT1Score10 = computed(() => {
  const total = evalT1.value?.total ?? 0;
  return Math.round((total / 40) * 10 * 10) / 10;
});

const evalT2Score10 = computed(() => {
  const ws = evalT2.value?.weighted_score ?? 0;
  return Math.round((ws / 100) * 10 * 10) / 10;
});

const evalT3Score10 = computed(() => {
  const total = evalT3.value?.total ?? 0;
  return Math.round((total / 40) * 10 * 10) / 10;
});

const evalT4Score10 = computed(() => evalT4.value?.score ?? 0);

const evalImprovementEntries = computed(() => {
  const notes = evalResult.value?.improvement_note ?? evalResult.value?.improvement_notes;
  if (notes && typeof notes === "object") {
    return Object.entries(notes)
      .filter(([, v]) => v != null && String(v).trim())
      .map(([dim, note]) => ({ dim, note: String(note) }));
  }
  const dims = ["F1", "F2", "F3", "F4", "T1", "T2", "T3", "T4"];
  return dims
    .map((dim) => {
      let block = evalResult.value?.[dim];
      if (!block && dim.startsWith("F")) block = evalPansaiLayer.value?.[dim];
      if (!block && dim.startsWith("T")) block = evalTheologyLayer.value?.[dim];
      return { dim, note: block?.improvement_note };
    })
    .filter((x) => x.note != null && String(x.note).trim());
});

function formatSubScore(score) {
  if (score == null || score === "" || Number.isNaN(Number(score))) return "—/10";
  const n = Number(score);
  const rounded = Math.round(n * 10) / 10;
  const display = Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
  return `${display}/10`;
}

function evalGapText(gap) {
  if (gap == null) return null;
  const s = String(gap).trim();
  if (!s || s.toLowerCase() === "null" || s === "无") return null;
  return s;
}

function extractVerseRef(text) {
  const s = String(text || "").trim();
  if (!s) return "";
  const m = s.match(/[\u4e00-\u9fff]{1,8}[\d一二三四五六七八九十百千两〇零]+[\d:：\-—]*\d*/);
  if (m) return m[0];
  return s.split(/[「『《"\s(（]/)[0] || s;
}

function normalizeScriptureSuggestionItem(item) {
  if (Array.isArray(item?.suggestions) && item.suggestions.length > 0) {
    return item;
  }
  const suggestions = [];
  if (item?.skeleton_recommendation) {
    suggestions.push({
      source: "骨架推荐",
      verse: extractVerseRef(item.skeleton_recommendation),
    });
  }
  if (item?.ai_suggestion) {
    suggestions.push({
      source: "AI推荐",
      verse: extractVerseRef(item.ai_suggestion),
    });
  }
  return { ...item, suggestions };
}

function applyScriptureReplacements(suggestions, answer) {
  if (!suggestions || suggestions.length === 0) {
    return { answer, replaced: 0 };
  }

  let result = answer;
  let replaced = 0;

  for (const raw of suggestions) {
    const s = normalizeScriptureSuggestionItem(raw);
    if (!s.current_verse || !s.suggestions || s.suggestions.length === 0) continue;

    const replacement =
      s.suggestions.find((x) => x.source === "骨架推荐") ?? s.suggestions[0];
    if (!replacement?.verse) continue;

    const escaped = s.current_verse.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const regex = new RegExp(escaped, "g");
    const next = result.replace(regex, replacement.verse);
    if (next !== result) {
      replaced += 1;
      result = next;
    }
  }

  return { answer: result, replaced };
}

function replaceSingleVerseInAnswer(currentVerse, replacementVerse, answer, originalText = "") {
  if (!currentVerse || !replacementVerse) return answer;
  const lines = answer.split("\n");
  let replaced = false;
  const newLines = lines.map((line) => {
    if (replaced) return line;
    const hasVerse = line.includes(currentVerse);
    if (!hasVerse) return line;
    // 若有 originalText，要求该行也包含 originalText 的前15字（避免截断影响）
    if (originalText) {
      const anchor = originalText.trim().slice(0, 15);
      if (anchor && !line.includes(anchor)) return line;
    }
    // 只替换第一个匹配的行，且只替换行内第一个 currentVerse
    replaced = true;
    return line.replace(currentVerse, replacementVerse);
  });
  if (!replaced) return answer; // 匹配失败，原样返回
  return newLines.join("\n");
}

function formatScriptureReplacementItems(suggestions) {
  return (suggestions || []).map((raw) => ({
    location: raw.location ?? "",
    original_text: raw.original_text ?? "",
    current_verse: raw.current_verse ?? "",
    ai_suggestion: raw.ai_suggestion ?? "",
    reason: raw.reason ?? "",
    decided: false,
    accepted: false,
  }));
}

function acceptScriptureReplacement(index) {
  const item = scriptureReplacementItems.value[index];
  if (!item || item.decided) return;
  const replacement =
    extractVerseRef(item.ai_suggestion) || String(item.ai_suggestion || "").trim();
  if (!replacement) return;
  const base = editableAnswer.value || aiResult.value?.answer || "";
  const next = replaceSingleVerseInAnswer(
    item.current_verse,
    replacement,
    base,
    item.original_text
  );
  if (next === base) {
    tip("找不到对应经文，请手动修改纲目");
    return;
  }
  editableAnswer.value = next;
  if (aiResult.value) {
    aiResult.value = { ...aiResult.value, answer: next };
  }
  item.decided = true;
  item.accepted = true;
  syncHistoryAnswerSkeleton(next);
}

function rejectScriptureReplacement(index) {
  const item = scriptureReplacementItems.value[index];
  if (!item || item.decided) return;
  item.decided = true;
  item.accepted = false;
}

function clearOutdatedGaps(evalData) {
  const t1 = evalData?.theology_layer?.T1 ?? evalData?.T1;
  if (!t1) return;
  const obsoleteKeywords = ["建议替换", "建议改用", "宜换用", "可换用", "建议用"];
  const layers = ["L1", "L2", "L3", "L4"];
  for (const layer of layers) {
    if (t1[layer]?.gap) {
      const hasObsolete = obsoleteKeywords.some((kw) => t1[layer].gap.includes(kw));
      if (hasObsolete) t1[layer].gap = null;
    }
  }
}

function formatScore10(value, divisor = 1) {
  if (value == null || value === "" || Number.isNaN(Number(value))) return "—/10";
  const n = Number(value) / divisor;
  const rounded = Math.round(n * 10) / 10;
  const display = Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
  return `${display}/10`;
}

function evalFScore10(key) {
  const block = evalPansaiLayer.value?.[key] ?? evalResult.value?.[key];
  if (!block || block.error || block.score == null) return "—/10";
  return formatScore10(block.score, 0.5);
}

function evalDimScore(key) {
  return evalFScore10(key);
}

function evalHasBlock(key) {
  const block = key.startsWith("T")
    ? evalTheologyLayer.value?.[key]
    : evalPansaiLayer.value?.[key] ?? evalResult.value?.[key];
  return block && !block.error;
}

// 【4.0】runOutlineEval（调用 /api/t35test/eval/outline）已删除

function toggleOutlineEdit() {
  if (outlineEditing.value) {
    outlineEditing.value = false;
    outlineEditReadonly.value = true;
    if (aiResult.value) {
      aiResult.value = { ...aiResult.value, answer: editableAnswer.value };
    }
    return;
  }
  outlineEditVisible.value = true;
  outlineEditing.value = true;
  outlineEditReadonly.value = false;
  editableAnswer.value = editableAnswer.value || aiResult.value?.answer || "";
  nextTick(() => {
    document.getElementById("outline-edit-textarea")?.scrollIntoView({ behavior: "smooth", block: "center" });
  });
}

function buildCurrentEvalRecord() {
  return {
    query: aiForm.outlineTopic.trim(),
    outline_nature: aiForm.specialNeeds.trim(),
    burden_description: aiForm.burdenDescription.trim(),
    revelation: getConceptListForEval("revelation"),
    inner: getConceptListForEval("inner"),
    experience: getConceptListForEval("experience"),
    practice: getConceptListForEval("practice"),
  };
}

function getF1SuggestedConcepts() {
  return (
    evalResult.value?.pansai_layer?.F1?.suggested_concepts
    ?? evalResult.value?.F1?.suggested_concepts
    ?? null
  );
}

function pickConceptLayer(suggested, layer, fallback) {
  const fromSuggested = suggested?.[layer];
  if (Array.isArray(fromSuggested) && fromSuggested.length > 0) {
    return [...fromSuggested];
  }
  return Array.isArray(fallback) ? [...fallback] : [];
}

async function applyEvalPrefill() {
  const raw = sessionStorage.getItem(EVAL_PREFILL_KEY);
  if (!raw) return false;
  sessionStorage.removeItem(EVAL_PREFILL_KEY);

  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    return false;
  }

  aiResult.value = null;
  evalResult.value = null;
  scriptureReplacementItems.value = [];
  skeletonSnapshot.value = [];
  outlineEditing.value = false;
  outlineEditVisible.value = false;
  outlineEditReadonly.value = false;
  editableAnswer.value = "";
  showInfo.value = 1;

  referenceExcerpt.value = "";
  burdenGenScenario.value = null;
  burdenGenCandidates.value = [];
  burdenGenLineA.value = "";
  burdenGenReasoning.value = "";
  burdenSelectedIdx.value = 0;
  burdenHiddenBySkip.value = false;
  burdenSkipTopicSnapshot.value = "";

  aiForm.outlineTopic = data.query || "";
  aiForm.specialNeeds = data.outline_nature === "应用实行" ? "实行应用" : (data.outline_nature || "");
  aiForm.burdenDescription = data.burden_description || "";
  burdenPhaseReady.value = true;

  resetConceptState();
  conceptMode.value = "manual";
  manualRevelation.value = [...(data.revelation || [])];
  manualInner.value = [...(data.inner || [])];
  manualExperience.value = [...(data.experience || [])];
  manualPractice.value = [...(data.practice || [])];
  manualKeyVerses.value = [...(data.key_verses || [])];

  aiPanelVisible.value = true;

  await nextTick();
  document.querySelector(".ai-meta-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
  return true;
}

function onRegenerateWithConcepts() {
  const currentRecord = buildCurrentEvalRecord();
  const suggested = getF1SuggestedConcepts();
  const prefillData = {
    query: currentRecord.query,
    outline_nature: currentRecord.outline_nature,
    burden_description: currentRecord.burden_description,
    revelation: pickConceptLayer(suggested, "revelation", currentRecord.revelation),
    inner: pickConceptLayer(suggested, "inner", currentRecord.inner),
    experience: pickConceptLayer(suggested, "experience", currentRecord.experience),
    practice: pickConceptLayer(suggested, "practice", currentRecord.practice),
  };
  sessionStorage.setItem(EVAL_PREFILL_KEY, JSON.stringify(prefillData));
  router.push({ path: "/panai35-test", query: { prefill: "true" } });
}

function setHistoryStatus(id, status) {
  historyList.value = historyList.value.map((item) =>
    item.id === id ? { ...item, status } : item
  );
  persistHistory();
}

function deleteHistoryRecord(id) {
  historyList.value = historyList.value.filter((item) => item.id !== id);
  persistHistory();
}

async function loadHistoryRecord(item) {
  aiForm.outlineTopic = "";
  aiForm.specialNeeds = "";
  aiForm.burdenDescription = "";
  referenceExcerpt.value = "";
  burdenPhaseReady.value = false;
  burdenGenScenario.value = null;
  burdenGenCandidates.value = [];
  burdenGenLineA.value = "";
  burdenGenReasoning.value = "";
  burdenSelectedIdx.value = 0;
  burdenHiddenBySkip.value = false;
  burdenSkipTopicSnapshot.value = "";
  resetConceptState();
  conceptMode.value = "manual";
  aiForm.outlineTopic = item.query || "";
  aiForm.specialNeeds = item.outline_nature === "应用实行" ? "实行应用" : (item.outline_nature || "");
  aiForm.burdenDescription = item.burden_description || "";
  currentRecordId.value = item.id;
  historyDrawerOpen.value = false;
  await nextTick();
  burdenPhaseReady.value = true;
  manualRevelation.value = [...(item.revelation || [])];
  manualInner.value = [...(item.inner || [])];
  manualExperience.value = [...(item.experience || [])];
  manualPractice.value = [...(item.practice || [])];
  manualKeyVerses.value = [...(item.key_verses || [])];
  console.log("载入后状态", {
    outlineTopic: aiForm.outlineTopic,
    specialNeeds: aiForm.specialNeeds,
    burdenPhaseReady: burdenPhaseReady.value,
    conceptMode: conceptMode.value,
    manualRevelation: manualRevelation.value,
    aiFormValid: aiFormValid.value,
    outlineGenerateDisabled: outlineGenerateDisabled.value
  });
}

onMounted(() => {
  updateIsMobileView();
  window.addEventListener("resize", updateIsMobileView);
  loadHistory();
  if (sessionStorage.getItem(EVAL_PREFILL_KEY)) {
    applyEvalPrefill();
    if (route.query.prefill) {
      router.replace({ path: "/panai35-test", query: {} });
    }
  }
});

watch(
  () => route.query.prefill,
  (val) => {
    if (val === "true" || val === true) {
      applyEvalPrefill();
      router.replace({ path: "/panai35-test", query: {} });
    }
  }
);

onUnmounted(() => {
  window.removeEventListener("resize", updateIsMobileView);
});

// AI 回答复制（包含标题）
const aiAnswerCopied = ref(false);
const copyAiAnswer = async () => {
  const text = aiResult.value?.answer;
  if (!text) return;
  // 使用生成时保存的标题，而不是当前输入框的值
  const title = aiResult.value?.outlineTopic || aiForm.outlineTopic.trim();
  const fullText = title ? `${title}\n\n${text}` : text;
  try {
    await navigator.clipboard.writeText(fullText);
    aiAnswerCopied.value = true;
    tip("已复制到剪贴板");
    setTimeout(() => {
      aiAnswerCopied.value = false;
    }, 2000);
  } catch (e) {
    tip("复制失败");
  }
};

// 英文纲目复制（包含标题）
const copyAiAnswerEn = async () => {
  const text = answerEn.value;
  if (!text) return;
  // 优先使用英文标题，否则使用生成时保存的中文标题
  const title = titleEn.value || aiResult.value?.outlineTopic || aiForm.outlineTopic.trim();
  const fullText = title ? `${title}\n\n${text}` : text;
  try {
    await navigator.clipboard.writeText(fullText);
    aiAnswerEnCopied.value = true;
    tip("英文纲目已复制到剪贴板");
    setTimeout(() => {
      aiAnswerEnCopied.value = false;
    }, 2000);
  } catch (e) {
    tip("复制失败");
  }
};

// 请求翻译中文纲目为英文（用户勾选「同时生成英文纲目」后调用）
const fetchTranslate = async (chineseOutline) => {
  if (!chineseOutline || !chineseOutline.trim()) return;
  loadingEnglish.value = true;
  errorEnglish.value = null;
  answerEn.value = null;
  titleEn.value = null;
  try {
    const res = await axios.post(
      "/api/t35test/translate_outline",
      { 
        chinese_outline: chineseOutline,
        outline_topic: aiForm.outlineTopic.trim() || null
      },
      { timeout: 120000 }
    );
    const data = res.data;
    if (data.answer_en) {
      answerEn.value = data.answer_en;
      titleEn.value = (data.title_en && data.title_en.trim()) ? data.title_en.trim() : null;
      if (!titleEn.value) {
        console.warn("英文标题翻译未返回，将使用中文标题");
      }
      if (aiMeta.cacheKey) {
        axios.post("/api/t35test/cache_translation", {
          cache_key: aiMeta.cacheKey,
          field: "answer_en",
          value: data.answer_en,
        }).catch(() => {});
      }
    } else {
      errorEnglish.value = data.error || "英文纲目生成失败";
    }
  } catch (err) {
    errorEnglish.value = err.response?.data?.detail || err.message || "翻译请求失败，请稍后重试";
  } finally {
    loadingEnglish.value = false;
  }
};

// 请求简体纲目转台湾繁体（用户勾选「同时生成繁体纲目」后调用）
const fetchTraditionalOutline = async (simplifiedOutline) => {
  if (!simplifiedOutline || !simplifiedOutline.trim()) return;
  loadingTraditional.value = true;
  errorTraditional.value = null;
  answerZhTw.value = null;
  try {
    const res = await axios.post(
      "/api/t35test/outline_to_traditional",
      { content: simplifiedOutline },
      { timeout: 60000 }
    );
    const data = res.data;
    if (data.answer_zh_tw) {
      answerZhTw.value = data.answer_zh_tw;
      if (aiMeta.cacheKey) {
        axios.post("/api/t35test/cache_translation", {
          cache_key: aiMeta.cacheKey,
          field: "answer_zh_tw",
          value: data.answer_zh_tw,
        }).catch(() => {});
      }
    } else {
      errorTraditional.value = data.error || "繁体纲目生成失败";
    }
  } catch (err) {
    errorTraditional.value = err.response?.data?.detail || err.message || "简转繁请求失败，请稍后重试";
  } finally {
    loadingTraditional.value = false;
  }
};

// 繁体纲目复制（包含标题）
const copyAiAnswerZhTw = async () => {
  const text = answerZhTw.value;
  if (!text) return;
  const title = aiResult.value?.outlineTopic || aiForm.outlineTopic.trim();
  const fullText = title ? `${title}\n\n${text}` : text;
  try {
    await navigator.clipboard.writeText(fullText);
    aiAnswerZhTwCopied.value = true;
    tip("繁体纲目已复制到剪贴板");
    setTimeout(() => {
      aiAnswerZhTwCopied.value = false;
    }, 2000);
  } catch (e) {
    tip("复制失败");
  }
};

// 刷格式并下载（中文纲目）
const downloadFormattedZh = async () => {
  const text = aiResult.value?.answer;
  if (!text || downloadFormatsZh.value.length === 0) {
    if (!text) tip("请先完成纲目生成");
    else tip("请至少选择一种下载格式");
    return;
  }
  const title = aiResult.value?.outlineTopic || aiForm.outlineTopic.trim();
  const fullText = title ? `${title}\n\n${text}` : text;
  const token = localStorage.getItem("token");
  if (!token) {
    window.location.hash = "/login";
    return;
  }
  downloadingZh.value = true;
  try {
    const orderedZh = ["docx", "pdf"].filter((f) => downloadFormatsZh.value.includes(f));
    for (const format of orderedZh) {
      const res = await fetch(`${apiBase}/api/t35test/format_outline_only`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          direction: "en2zh",
          translated_text: fullText,
          output_format: format,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        tip((data.detail || data.error) || "格式化失败");
        continue;
      }
      doDownload(data, format, false);
    }
    if (downloadFormatsZh.value.length > 0) tip("下载完成");
  } catch (e) {
    tip(e?.message || "下载失败");
  } finally {
    downloadingZh.value = false;
  }
};

// 刷格式并下载（英文纲目）
const downloadFormattedEn = async () => {
  const text = answerEn.value;
  if (!text || downloadFormatsEn.value.length === 0) {
    if (!text) tip("请先完成英文纲目生成");
    else tip("请至少选择一种下载格式");
    return;
  }
  const title = titleEn.value || aiResult.value?.outlineTopic || aiForm.outlineTopic.trim();
  const fullText = title ? `${title}\n\n${text}` : text;
  const token = localStorage.getItem("token");
  if (!token) {
    window.location.hash = "/login";
    return;
  }
  downloadingEn.value = true;
  try {
    const orderedEn = ["docx", "pdf"].filter((f) => downloadFormatsEn.value.includes(f));
    for (const format of orderedEn) {
      const res = await fetch(`${apiBase}/api/t35test/format_outline_only`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ direction: "zh2en", translated_text: fullText, output_format: format }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        tip((data.detail || data.error) || "格式化失败");
        continue;
      }
      doDownload(data, format, true);
    }
    if (downloadFormatsEn.value.length > 0) tip("下载完成");
  } catch (e) {
    tip(e?.message || "下载失败");
  } finally {
    downloadingEn.value = false;
  }
};

// 刷格式并下载（繁体纲目）
const downloadFormattedZhTw = async () => {
  const text = answerZhTw.value;
  if (!text || downloadFormatsZhTw.value.length === 0) {
    if (!text) tip("请先完成繁体纲目生成");
    else tip("请至少选择一种下载格式");
    return;
  }
  const title = aiResult.value?.outlineTopic || aiForm.outlineTopic.trim();
  const fullText = title ? `${title}\n\n${text}` : text;
  const token = localStorage.getItem("token");
  if (!token) {
    window.location.hash = "/login";
    return;
  }
  downloadingZhTw.value = true;
  try {
    const orderedZhTw = ["docx", "pdf"].filter((f) => downloadFormatsZhTw.value.includes(f));
    for (const format of orderedZhTw) {
      const res = await fetch(`${apiBase}/api/t35test/format_outline_only`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ direction: "zh_cn2tw", translated_text: fullText, output_format: format }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        tip((data.detail || data.error) || "格式化失败");
        continue;
      }
      doDownload(data, format, false);
    }
    if (downloadFormatsZhTw.value.length > 0) tip("下载完成");
  } catch (e) {
    tip(e?.message || "下载失败");
  } finally {
    downloadingZhTw.value = false;
  }
};

// 通用：根据接口返回触发 DOCX/PDF 下载（移动端与桌面端均使用下载）
function doDownload(data, format, isEn) {
  const defaultName = isEn ? "outline_en" : "outline_zh";
  if (format === "docx" && data.docx_base64) {
    const bin = Uint8Array.from(atob(data.docx_base64), (c) => c.charCodeAt(0));
    const blob = new Blob([bin], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = data.filename || `${defaultName}.docx`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } else if (format === "pdf") {
    if (data.pdf_base64) {
      const bin = Uint8Array.from(atob(data.pdf_base64), (c) => c.charCodeAt(0));
      const blob = new Blob([bin], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = data.filename || `${defaultName}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } else if (data.docx_base64) {
      const bin = Uint8Array.from(atob(data.docx_base64), (c) => c.charCodeAt(0));
      const blob = new Blob([bin], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = (data.filename || defaultName).replace(".pdf", ".docx");
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      tip("PDF 转换失败，已下载 DOCX");
    }
  }
}

async function downloadEvalDocx() {
  const text = editableAnswer.value;
  if (!text?.trim()) {
    tip("请先完成纲目评估");
    return;
  }
  const title = aiResult.value?.outlineTopic || aiForm.outlineTopic.trim();
  const fullText = title ? `${title}\n\n${text}` : text;
  const token = localStorage.getItem("token");
  if (!token) {
    window.location.hash = "/login";
    return;
  }
  try {
    const res = await fetch(`${apiBase}/api/t35test/format_outline_only`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ direction: "en2zh", translated_text: fullText, output_format: "docx" }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      tip((data.detail || data.error) || "格式化失败");
      return;
    }
    doDownload(data, "docx", false);
    tip("下载完成");
  } catch (e) {
    tip(e?.message || "下载失败");
  }
}

// 仅将 AI 回答中的大点（壹、贰、叁/参…拾、拾壹、拾贰…贰拾、贰壹、贰贰…）整行加粗；「参考与参读资料：」及之后不加粗
const aiAnswerFormatted = computed(() => {
  const raw = aiResult.value?.answer;
  if (!raw) return "";
  const escaped = raw.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const withBr = escaped.replace(/\r\n/g, "\n").replace(/\n/g, "<br>");
  // 「参考与参读资料：」及之后不加粗
  const refIdx = withBr.search(/参考与参读资料[：:]/i);
  const toBold = refIdx >= 0 ? withBr.slice(0, refIdx) : withBr;
  const afterRef = refIdx >= 0 ? withBr.slice(refIdx) : "";
  // 只匹配大点：壹、贰、叁/参、肆…拾、拾壹、拾贰…贰拾、贰壹、贰贰… 整行（纲目后可为顿号、逗号、全角空格、半角空格、制表符等）
  const big = /(^|<br>)([\s#*]*)((?:壹[、，\u3000\t ]|贰[、，\u3000\t ]|(?:叁|参)[、，\u3000\t ]|肆[、，\u3000\t ]|伍[、，\u3000\t ]|陆[、，\u3000\t ]|柒[、，\u3000\t ]|捌[、，\u3000\t ]|玖[、，\u3000\t ]|拾[、，\u3000\t ]|拾[壹贰叁参肆伍陆柒捌玖][、，\u3000\t ]|贰[拾壹贰叁参肆伍陆柒捌玖][、，\u3000\t ])[^<]*?)(?=<br>|$)/g;
  const s = toBold.replace(big, "$1$2<strong>$3</strong>");
  const content = s + afterRef;
  // 添加标题（如果有）- 使用生成时保存的标题，而不是当前输入框的值
  const title = aiResult.value?.outlineTopic || aiForm.outlineTopic.trim();
  if (title) {
    const titleEscaped = title.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return `<div style="text-align: center; font-weight: bold; margin-bottom: 16px;">${titleEscaped}</div>${content}`;
  }
  return content;
});

// 繁体纲目格式化（换行转 br，大点壹貳參…加粗，「參考與參讀資料：」及之后不加粗）
const aiAnswerZhTwFormatted = computed(() => {
  const raw = answerZhTw.value;
  if (!raw) return "";
  const escaped = raw.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const withBr = escaped.replace(/\r\n/g, "\n").replace(/\n/g, "<br>");
  const refIdx = withBr.search(/參考與參讀資料[：:]/i);
  const toBold = refIdx >= 0 ? withBr.slice(0, refIdx) : withBr;
  const afterRef = refIdx >= 0 ? withBr.slice(refIdx) : "";
  // 繁体大点：壹、貳、參、肆、伍、陸、柒、捌、玖、拾、拾壹…貳拾、貳壹…
  const big = /(^|<br>)([\s#*]*)((?:壹[、，\u3000\t ]|貳[、，\u3000\t ]|參[、，\u3000\t ]|肆[、，\u3000\t ]|伍[、，\u3000\t ]|陸[、，\u3000\t ]|柒[、，\u3000\t ]|捌[、，\u3000\t ]|玖[、，\u3000\t ]|拾[、，\u3000\t ]|拾[壹貳參肆伍陸柒捌玖][、，\u3000\t ]|貳[拾壹貳參肆伍陸柒捌玖][、，\u3000\t ])[^<]*?)(?=<br>|$)/g;
  const s = toBold.replace(big, "$1$2<strong>$3</strong>");
  const content = s + afterRef;
  const title = aiResult.value?.outlineTopic || aiForm.outlineTopic.trim();
  if (title) {
    const titleEscaped = title.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return `<div style="text-align: center; font-weight: bold; margin-bottom: 16px;">${titleEscaped}</div>${content}`;
  }
  return content;
});

// 英文纲目格式化（换行转 br，只有英文大点加粗，其他星号去掉）
const aiAnswerEnFormatted = computed(() => {
  const raw = answerEn.value;
  if (!raw) return "";
  const escaped = raw.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const withBr = escaped.replace(/\r\n/g, "\n").replace(/\n/g, "<br>");
  // 英文大点罗马数字：I–X(1–10)、XI–XX(11–20)，支持加粗
  const romanMajor = "(?:XX|X(?:I{0,3}|IV|VI{0,3}|IX)?|I{1,3}|IV|VI{0,3}|IX|X)";
  // 先处理带星号的英文大点（**I.**、**XI.** 等）加粗
  const withBoldStars = withBr.replace(new RegExp(`\\*\\*(${romanMajor}[\\.:]\\s*[^<]*?)\\*\\*`, "g"), "<strong>$1</strong>");
  // 将剩余的 **文本** 去掉星号，只保留文本（不加粗）
  const withoutBold = withBoldStars.replace(/\*\*([^*]+?)\*\*/g, "$1");
  // 将 Markdown 的 *文本*（斜体）去掉星号，只保留文本
  const withoutItalic = withoutBold.replace(/\*([^*]+?)\*/g, "$1");
  // 直接匹配英文大点（I–X、XI–XX）加粗（不依赖星号）
  const bigEn = new RegExp(`(^|<br>)([\\s#*]*)(${romanMajor}[\\.:]\\s*[^<]*?)(?=<br>|$)`, "g");
  const content = withoutItalic.replace(bigEn, "$1$2<strong>$3</strong>");
  // 添加标题（如果有）- 优先使用英文标题，否则使用生成时保存的中文标题
  const title = titleEn.value || aiResult.value?.outlineTopic || aiForm.outlineTopic.trim();
  if (title) {
    const titleEscaped = title.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return `<div style="text-align: center; font-weight: bold; margin-bottom: 16px;">${titleEscaped}</div>${content}`;
  }
  return content;
});

// ─── 引用来源：索引类型判断与格式化 ───

function getSourceType(chunkId) {
  if (!chunkId) return "unknown";
  if (chunkId.startsWith("firewall:") || chunkId.startsWith("防火墙")) return "firewall";
  // 【4.0】新编号
  if (chunkId.startsWith("gm12490_")) return "gm12490";
  if (chunkId.startsWith("gmfeasts_")) return "gmfeasts";
  if (chunkId.startsWith("gmbible_")) return "gmbible";
  if (chunkId.startsWith("gmhymns_")) return "gmhymns";
  if (chunkId.startsWith("pano_")) return "pano_catalog";
  if (chunkId.startsWith("mutual:")) return "mutual"; // 【4.0】彼此互相
  if (chunkId.startsWith("3a:")) return "dict_3a"; // 【4.0】真理辞典 3a
  if (chunkId.startsWith("life_")) return "life";
  if (chunkId.startsWith("cwwl_")) return "cwwl";
  if (chunkId.startsWith("cwwn_")) return "cwwn";
  if (chunkId.startsWith("others_")) return "others";
  if (chunkId.startsWith("bib_")) return "bib";
  if (chunkId.startsWith("map_note_")) return "map_note";
  if (chunkId.startsWith("map_7feasts_")) return "map_7feasts";
  if (chunkId.startsWith("map_pano")) return "map_pano";
  if (chunkId.startsWith("map_dictionary")) return "map_dictionary";
  return "unknown";
}

const SOURCE_TYPE_LABELS = {
  firewall:       { label: "防火墙",         color: "#f50" },
  life:           { label: "生命读经",       color: "#2db7f5" },
  cwwl:           { label: "李常受文集",     color: "#87d068" },
  cwwn:           { label: "倪柝声文集",     color: "#9254de" },
  others:         { label: "其他",           color: "#13c2c2" },
  bib:            { label: "圣经",           color: "#fa8c16" },
  map_note:       { label: "注解纲目",       color: "#597ef7" },
  map_7feasts:    { label: "节期纲目",       color: "#f759ab" },
  map_pano:       { label: "清明上河图",     color: "#36cfc9" },
  map_dictionary: { label: "主恢复真理词典", color: "#ff85c0" },
  gm12490:        { label: "倪李文集纲目",   color: "#73d13d" },
  gmfeasts:       { label: "节期纲目",       color: "#f759ab" },
  gmbible:        { label: "圣经",           color: "#fa8c16" },
  gmhymns:        { label: "诗歌",           color: "#ffc53d" },
  pano_catalog:   { label: "清明上河图目录", color: "#36cfc9" },
  mutual:         { label: "彼此互相",       color: "#08979c" }, // 【4.0】
  dict_3a:        { label: "3a",             color: "#cf1322" }, // 【4.0】真理辞典 3a
  unknown:        { label: "其他",           color: "#d9d9d9" },
};

function getSourceLabel(chunkId) {
  return SOURCE_TYPE_LABELS[getSourceType(chunkId)] || SOURCE_TYPE_LABELS.unknown;
}

function formatSourceTitle(src) {
  const type = getSourceType(src.chunk_id);

  if (type === "firewall") {
    // 【4.0】后端带「（整篇）」或「（一句说明）」+ 篇题
    return src.display_title || src.chunk_id.replace(/^firewall:/, "");
  }

  // 【4.0】后端按库算好的出处（原文/注解取 source_zh，纲目取 text 开头出处，圣经取书名节号，诗歌取首名，目录取 path_text+篇题）
  if (src.display_title) return src.display_title;

  if (type === "bib") {
    const sz = src.source_zh || src.chunk_id;
    return sz.replace(/^[（(]/, "").replace(/[）)]$/, "");
  }

  const parts = [];
  if (src.book_title) parts.push(src.book_title);
  if (src.message_title) parts.push(src.message_title);
  return parts.join("，") || src.chunk_id;
}

const buildKgRagParams = () => ({
  outline_nature: aiForm.specialNeeds.trim(),
  burden_description: aiForm.burdenDescription.trim(),
  depth: "general",
});

/** 统一解析 KG-RAG 响应（缓存命中 / 未命中） */
function parseKgRagResponse(data) {
  const isCached = !!data.cached;
  const result = {
    answer: data.answer || null,
    outlineTopic: aiForm.outlineTopic.trim(),
    cached: isCached,
    cacheKey: data.cache_key || null,
    revelation: [],
    inner: [],
    experience: [],
    practice: [],
    skeleton: null,
    mainSources: [],
    totalElapsedMs: null,
    totalCostUsd: null,
    answerEn: null,
    answerZhTw: null,
  };
  if (isCached) {
    result.revelation = data.revelation || [];
    result.inner = data.inner || [];
    result.experience = data.experience || [];
    result.practice = data.practice || [];
    result.skeleton = data.skeleton || null;
    result.mainSources = data.main_sources || [];
    result.totalElapsedMs = data.total_elapsed_ms ?? null;
    result.totalCostUsd = data.total_cost_usd ?? null;
    result.answerEn = data.answer_en || null;
    result.answerZhTw = data.answer_zh_tw || null;
  } else {
    const s1 = data.steps?.step1 || {};
    const s2 = data.steps?.step2 || {};
    const s3 = data.steps?.step3 || {};
    const usage = data.llm_usage || {};
    result.revelation = s1.revelation || [];
    result.inner = s1.inner || [];
    result.experience = s1.experience || [];
    result.practice = s1.practice || [];
    result.skeleton = s2.skeleton || null;
    // 【4.0】清明上河图目录的 20 条也算进引用来源
    const allResults = [...(s3.main_results || []), ...(s3.expanded_results || []), ...(s3.catalog_results || []), ...(s3.mutual_results || []), ...(s3.dict_results || [])]; // 【4.0】dict_results = 真理辞典 3a
    result.mainSources = allResults.map(r => ({
      chunk_id: r.chunk_id || "",
      book_title: r.book_title || "",
      source_zh: r.source_zh || "",
      message_title: r.message_title || "",
      display_title: r.display_title || "",
      text_preview: (() => {
        const t = r.text || "";
        return t.length > 200 ? t.slice(0, 200) + "…" : t;
      })(),
    }));
    result.totalElapsedMs = usage.total_elapsed_ms ?? null;
    result.totalCostUsd = (usage.totals || {}).cost_usd ?? null;
  }
  console.log("parsed answer:", result?.answer, "raw data keys:", Object.keys(data));
  return result;
}

// AI 纲目生成（单次调用 KG-RAG）
const onAISearch = async () => {
  const question = aiForm.outlineTopic.trim();

  if (!question || !aiFormValid.value) {
    tip("请至少填写纲目主题并选择纲目性质");
    return;
  }
  if (!burdenPhaseReady.value) {
    tip("请先完成负担说明阶段（点「确认，开始推荐重点」）");
    return;
  }

  loadingAI.value = true;
  showInfo.value = 6;
  aiResult.value = null;
  evalResult.value = null;
  scriptureReplacementItems.value = [];
  skeletonSnapshot.value = [];
  outlineEditing.value = false;
  outlineEditVisible.value = false;
  outlineEditReadonly.value = false;
  editableAnswer.value = "";
  answerEn.value = null;
  errorEnglish.value = null;
  answerZhTw.value = null;
  errorTraditional.value = null;
  showAISources.value = false;
  showAIAnswer.value = false;
  aiLoadingText.value = "✨ AI 纲目生成中…";
  Object.assign(aiMeta, { revelation: [], inner: [], experience: [], practice: [], skeleton: null, mainSources: [], totalElapsedMs: null, totalCostUsd: null, cached: false, cacheKey: null });

  try {
    const qParams = buildKgRagParams();
    if (
      conceptMode.value === "manual" &&
      manualRevelation.value.length > 0
    ) {
      qParams.preset_revelation = [...manualRevelation.value];
      qParams.preset_inner = [...manualInner.value];
      qParams.preset_experience = [...manualExperience.value];
      qParams.preset_practice = [...manualPractice.value];
      qParams.preset_key_verses = [...manualKeyVerses.value]; // 可选；目前只记录，还没放进生成纲目的 Prompt
    } else if (
      conceptMode.value === "ai" &&
      conceptStage.value === "candidates_ready" &&
      conceptCandidates.value &&
      selectedRevelation.value.length > 0
    ) {
      qParams.preset_revelation = [...selectedRevelation.value];
      qParams.preset_inner = [...selectedInner.value];
      qParams.preset_experience = [...selectedExperience.value];
      qParams.preset_practice = [...selectedPractice.value];
      qParams.preset_key_verses = [...selectedKeyVerses.value]; // 可选；目前只记录，还没放进生成纲目的 Prompt
    }
    const res = await axios.post(
      "/api/t35test/query",
      { query: question, params: qParams, mode: PIPELINE_MODE },
      { timeout: 300000 }
    );
    const data = res.data;
    if (!data.answer) {
      tip(data.error || "纲目生成失败，请稍后重试");
      showInfo.value = 3;
      return;
    }

    const parsed = parseKgRagResponse(data);
    aiResult.value = { answer: parsed.answer, outlineTopic: parsed.outlineTopic };
    Object.assign(aiMeta, {
      revelation: parsed.revelation,
      inner: parsed.inner,
      experience: parsed.experience,
      practice: parsed.practice,
      skeleton: parsed.skeleton,
      mainSources: parsed.mainSources,
      totalElapsedMs: parsed.totalElapsedMs,
      totalCostUsd: parsed.totalCostUsd,
      cached: parsed.cached,
      cacheKey: parsed.cacheKey,
    });

    showInfo.value = 5;
    showAISources.value = true;
    showAIAnswer.value = true;

    if (parsed.cached) {
      aiLoadingText.value = "已找到缓存结果";
    }

    // 缓存命中且已有翻译时直接展示
    if (parsed.cached && parsed.answerEn) {
      answerEn.value = parsed.answerEn;
    } else if (includeEnglishOutline.value) {
      fetchTranslate(parsed.answer);
    }
    if (parsed.cached && parsed.answerZhTw) {
      answerZhTw.value = parsed.answerZhTw;
    } else if (includeTraditionalOutline.value) {
      fetchTraditionalOutline(parsed.answer);
    }

    setTimeout(() => {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }, 100);
  } catch (err) {
    console.error("AI纲目生成失败:", err);
    const isTimeout = err.code === "ECONNABORTED" || err.message?.includes("timeout");
    const msg = isTimeout
      ? "请求超时，AI 生成时间较长，请稍后重试"
      : (err.response?.data?.detail || err.response?.data?.error || "AI纲目生成失败，请稍后重试");
    tip(msg);
    showInfo.value = 3;
  } finally {
    loadingAI.value = false;
    resetConceptState();
  }
};

// 【PanAI 新测试台】返回工具箱
function goBackToTools() {
  try {
    router.push("/tools");
  } catch (e) {
    window.location.hash = "/tools";
  }
}

</script>

<template>
  <div class="t35-header">
    <div class="t35-header-left" @click="goBackToTools" title="返回工具箱">
      <ArrowLeftOutlined class="t35-header-back" />
      <span class="t35-header-backtext">返回</span>
    </div>
    <div class="t35-header-title">PanAI 新测试台</div>
    <div class="t35-header-right"></div>
  </div>
  <div class="search-box t35-box">
    <div class="search-bar">
      <transition name="ai-meta-panel">
        <div v-if="aiPanelVisible" class="ai-meta-panel">
          <div class="ai-meta-grid">
            <label class="ai-meta-field full">
              <span>纲目主题*（必填）</span>
              <a-textarea
                v-model:value="aiForm.outlineTopic"
                :disabled="loadingAI"
                placeholder="纲目的题目"
                :auto-size="{ minRows: 1, maxRows: 4 }"
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
            <div v-if="showBurdenPhasePanel" class="ai-meta-field full ai-burden-phase">
              <div class="ai-burden-phase-head">
                <span class="ai-burden-phase-title">负担说明的生成</span>
                <a
                  href="#"
                  class="ai-burden-skip"
                  :class="{ 'ai-burden-skip--locked': burdenPhaseReady }"
                  @click.prevent="skipBurdenPhase"
                >跳过负担说明</a>
              </div>
              <label class="ai-meta-field full ai-burden-phase-inner">
                <span>负担的重点请贴这里（80字以内）</span>
                <textarea
                  class="ai-burden-textarea"
                  rows="3"
                  v-model="referenceExcerpt"
                  :disabled="loadingAI || burdenGenLoading || burdenPhaseReady"
                  placeholder="有提供负担的重点直接生成负担说明，没有提供负担的重点可生成四个负担说明以供选择"
                ></textarea>
              </label>
              <div class="ai-burden-btn-wrap">
                <a-button
                  block
                  :loading="burdenGenLoading"
                  :disabled="loadingAI || burdenGenLoading || !aiFormValid || burdenPhaseReady"
                  @click="onGenerateBurden"
                >生成负担说明</a-button>
              </div>
              <div v-if="burdenGenReasoning" class="ai-burden-reasoning">
                <div
                  class="ai-burden-reasoning-head"
                  @click="burdenReasoningOpen = !burdenReasoningOpen"
                >
                  <span>{{ burdenReasoningOpen ? "▼" : "▶" }} 查看要点依据</span>
                </div>
                <div v-if="burdenReasoningOpen" class="ai-burden-reasoning-body">{{ burdenGenReasoningNumbered }}</div>
              </div>
              <div v-if="burdenGenScenario === 'A' && burdenGenLineA" class="ai-burden-gen-out">
                <div class="ai-burden-gen-label">有负担的重点</div>
                <div class="ai-burden-gen-text">{{ burdenGenLineA }}</div>
              </div>
              <div v-if="burdenGenScenario === 'B' && burdenGenCandidates.length" class="ai-burden-gen-out">
                <div class="ai-burden-gen-label">没有负担的重点</div>
                <a-radio-group
                  v-model:value="burdenSelectedIdx"
                  class="ai-burden-radio-group"
                  :disabled="burdenPhaseReady"
                >
                  <div
                    v-for="(c, i) in burdenGenCandidates"
                    :key="i"
                    class="ai-burden-radio-line"
                  >
                    <a-radio :value="i">{{ ['真理启示', '内在素质', '生命经历', '实行应用'][i] }}</a-radio>
                    <span class="ai-burden-cand-body">{{ c }}</span>
                  </div>
                </a-radio-group>
              </div>
              <label class="ai-meta-field full ai-burden-phase-inner">
                <span>生成的负担说明</span>
                <a-textarea
                  class="ai-burden-textarea"
                  v-model:value="aiForm.burdenDescription"
                  :disabled="loadingAI || burdenPhaseReady"
                  placeholder="在此输入或编辑负担说明，也可留空"
                  :auto-size="{ minRows: 2, maxRows: 8 }"
                />
              </label>
              <div class="ai-burden-btn-wrap">
                <a-button block :disabled="loadingAI || burdenPhaseReady" @click="confirmBurdenPhase">确认，开始推荐重点</a-button>
              </div>
            </div>
          </div>
            <div class="ai-panel-actions">
            <div class="ai-panel-hint" v-if="!aiFormValid">请至少填写纲目主题并选择纲目性质后再开始制作</div>
            <div class="ai-panel-hint" v-else-if="!burdenPhaseReady">请先完成负担说明步骤（跳过负担说明，或生成/填写负担说明后，点「确认，开始推荐重点」）</div>
            <div v-else class="concept-mode-toggle">
              <a-button
                :type="conceptMode === 'ai' ? 'primary' : 'default'"
                @click="setConceptMode('ai')"
              >推荐重点</a-button>
              <a-button
                :type="conceptMode === 'manual' ? 'primary' : 'default'"
                @click="setConceptMode('manual')"
              >输入重点</a-button>
            </div>
            <div class="ai-concept-panel ai-concept-search-panel">
              <div class="ai-concept-search">
                <span class="ai-concept-label">搜索图谱中重点</span>
                  <a-auto-complete
                    v-model:value="conceptSearchKeyword"
                    :options="conceptSearchOptions"
                    :open="conceptSearchOpen"
                    :not-found-content="conceptSearchLoading ? '搜索中…' : '暂无匹配'"
                    placeholder=""
                    allow-clear
                    @select="onSelectConceptSearchOption"
                  />
              </div>
            </div>
            <!-- AI：勾选候选（不可自由输入） -->
            <div
              v-if="conceptMode === 'ai' && conceptStage === 'candidates_ready' && conceptCandidates"
              class="ai-concept-panel"
            >
              <div v-if="stepThinkingText" class="ai-burden-reasoning">
                <div
                  class="ai-burden-reasoning-head"
                  @click="stepThinkingOpen = !stepThinkingOpen"
                >
                  <span>{{ stepThinkingOpen ? "▼" : "▶" }} 查看模型思考过程</span>
                </div>
                <div v-if="stepThinkingOpen" class="ai-burden-reasoning-body">
                  <div class="ai-concept-label" style="margin-bottom: 4px;">英文原文</div>
                  <div>{{ indentParagraphs(stepThinkingText) }}</div>
                  <template v-if="stepThinkingTextZh">
                    <div class="ai-concept-label" style="margin: 10px 0 4px;">中文翻译</div>
                    <div>{{ indentParagraphs(stepThinkingTextZh) }}</div>
                  </template>
                </div>
              </div>
              <div class="ai-concept-section ai-concept-checkwrap">
                <span class="ai-concept-label">关键圣经节<span class="ai-concept-optional">（可选）</span></span>
                <a-checkbox-group
                  v-if="(conceptCandidates.key_verses || []).length"
                  v-model:value="selectedKeyVerses"
                  :options="conceptCandidates.key_verses"
                  class="ai-concept-checks"
                />
                <span v-else class="ai-concept-empty">（本题没有推荐关键圣经节）</span>
              </div>
              <div v-if="(conceptCandidates.revelation || []).length" class="ai-concept-section ai-concept-checkwrap">
                <span class="ai-concept-label">真理启示</span>
                <a-checkbox-group
                  v-model:value="selectedRevelation"
                  :options="conceptCandidates.revelation"
                  class="ai-concept-checks"
                />
              </div>
              <div v-else class="ai-concept-empty">（启示层无候选）</div>
              <div class="ai-concept-section ai-concept-checkwrap">
                <span class="ai-concept-label">内在素质</span>
                <a-checkbox-group
                  v-if="(conceptCandidates.inner || []).length"
                  v-model:value="selectedInner"
                  :options="conceptCandidates.inner"
                  class="ai-concept-checks"
                />
                <span v-else class="ai-concept-empty">（内在素质层无候选）</span>
              </div>
              <div v-if="(conceptCandidates.experience || []).length" class="ai-concept-section ai-concept-checkwrap">
                <span class="ai-concept-label">生命经历</span>
                <a-checkbox-group
                  v-model:value="selectedExperience"
                  :options="conceptCandidates.experience"
                  class="ai-concept-checks"
                />
              </div>
              <div v-if="(conceptCandidates.practice || []).length" class="ai-concept-section ai-concept-checkwrap">
                <span class="ai-concept-label">实行应用</span>
                <a-checkbox-group
                  v-model:value="selectedPractice"
                  :options="conceptCandidates.practice"
                  class="ai-concept-checks"
                />
              </div>
              <div v-if="conceptCandidates.summary || conceptCandidates.reasoning" class="ai-burden-reasoning">
                <div
                  class="ai-burden-reasoning-head"
                  @click="stepSummaryOpen = !stepSummaryOpen"
                >
                  <span>{{ stepSummaryOpen ? "▼" : "▶" }} 查看小结</span>
                </div>
                <div v-if="stepSummaryOpen" class="ai-burden-reasoning-body">{{ conceptCandidates.summary || conceptCandidates.reasoning }}</div>
              </div>
              <div class="ai-burden-reasoning">
                <div
                  class="ai-burden-reasoning-head"
                  @click="stepDroppedOpen = !stepDroppedOpen"
                >
                  <span>{{ stepDroppedOpen ? "▼" : "▶" }} 查看dropped（舍弃的词{{ stepDropped.length ? "，共" + stepDropped.length + "个" : "" }}）</span>
                </div>
                <div v-if="stepDroppedOpen" class="ai-burden-reasoning-body">
                  <div v-if="!stepDropped.length">本次无舍弃的词</div>
                  <div v-for="(item, idx) in stepDropped" :key="'dropped-' + idx">{{ item.layer }}：{{ item.word }}</div>
                </div>
              </div>
              <div class="ai-burden-reasoning">
                <div
                  class="ai-burden-reasoning-head"
                  @click="stepTruncatedOpen = !stepTruncatedOpen"
                >
                  <span>{{ stepTruncatedOpen ? "▼" : "▶" }} 查看被截断的词{{ stepTruncated.length ? "（共" + stepTruncated.length + "个）" : "" }}</span>
                </div>
                <div v-if="stepTruncatedOpen" class="ai-burden-reasoning-body">
                  <div v-if="!stepTruncated.length">本次无被截断的词</div>
                  <div v-for="(item, idx) in stepTruncated" :key="'truncated-' + idx">{{ item.layer }}：{{ item.word }}</div>
                </div>
              </div>
              <div class="ai-history-save-row">
                <a-button size="small" @click="saveCurrentToHistory">保存记录</a-button>
              </div>
            </div>
            <!-- 人工：四层 tag -->
            <div v-if="conceptMode === 'manual'" class="ai-concept-panel ai-concept-manual">
              <div class="ai-concept-hint">直接输入重点，回车添加，× 删除。</div>
              <div class="ai-concept-section">
                <span class="ai-concept-label">关键圣经节<span class="ai-concept-optional">（可选）</span></span>
                <a-select
                  v-model:value="manualKeyVerses"
                  mode="tags"
                  class="ai-concept-tags"
                  :open="false"
                  placeholder="如：弗四16，回车添加"
                  allow-clear
                />
              </div>
              <div class="ai-concept-section">
                <span class="ai-concept-label">真理启示</span>
                <a-select
                  v-model:value="manualRevelation"
                  v-model:searchValue="manualConceptSearchValue.revelation"
                  mode="multiple"
                  class="ai-concept-tags ai-concept-tags--revelation"
                  :options="manualConceptOptions.revelation"
                  :loading="manualConceptLoading.revelation"
                  :filter-option="false"
                  placeholder=""
                  @search="(v) => onManualConceptSearch('revelation', v)"
                  @select="() => onManualConceptSelect('revelation')"
                  @inputKeyDown="(e) => onManualConceptInputKeydown('revelation', e)"
                  allow-clear
                />
              </div>
              <div class="ai-concept-section">
                <span class="ai-concept-label">内在素质</span>
                <a-select
                  v-model:value="manualInner"
                  v-model:searchValue="manualConceptSearchValue.inner"
                  mode="multiple"
                  class="ai-concept-tags ai-concept-tags--inner"
                  :options="manualConceptOptions.inner"
                  :filter-option="false"
                  placeholder="词汇待资料库上传，目前可直接输入、回车添加"
                  @search="(v) => onManualConceptSearch('inner', v)"
                  @select="() => onManualConceptSelect('inner')"
                  @inputKeyDown="(e) => onManualConceptInputKeydown('inner', e)"
                  allow-clear
                />
              </div>
              <div class="ai-concept-section">
                <span class="ai-concept-label">生命经历</span>
                <a-select
                  v-model:value="manualExperience"
                  v-model:searchValue="manualConceptSearchValue.experience"
                  mode="multiple"
                  class="ai-concept-tags ai-concept-tags--experience"
                  :options="manualConceptOptions.experience"
                  :loading="manualConceptLoading.experience"
                  :filter-option="false"
                  placeholder=""
                  @search="(v) => onManualConceptSearch('experience', v)"
                  @select="() => onManualConceptSelect('experience')"
                  @inputKeyDown="(e) => onManualConceptInputKeydown('experience', e)"
                  allow-clear
                />
              </div>
              <div class="ai-concept-section">
                <span class="ai-concept-label">实行应用</span>
                <a-select
                  v-model:value="manualPractice"
                  v-model:searchValue="manualConceptSearchValue.practice"
                  mode="multiple"
                  class="ai-concept-tags ai-concept-tags--practice"
                  :options="manualConceptOptions.practice"
                  :loading="manualConceptLoading.practice"
                  :filter-option="false"
                  placeholder=""
                  @search="(v) => onManualConceptSearch('practice', v)"
                  @select="() => onManualConceptSelect('practice')"
                  @inputKeyDown="(e) => onManualConceptInputKeydown('practice', e)"
                  allow-clear
                />
              </div>
            </div>
            <div class="ai-panel-cta">
              <a-checkbox v-model:checked="includeEnglishOutline" :disabled="!ENGLISH_OUTLINE_FEATURE_ENABLED || loadingAI" style="margin-right: 12px;">同时生成英文纲目</a-checkbox>
              <a-checkbox v-model:checked="includeTraditionalOutline" :disabled="loadingAI" style="margin-right: 12px;">同时生成繁体纲目</a-checkbox>
              <a-button
                v-if="conceptMode === 'ai' && conceptStage === 'idle'"
                :loading="conceptLoading"
                :disabled="conceptLoading || !aiFormValid || !burdenPhaseReady"
                @click="extractConcepts"
              >
                {{ conceptLoading ? "推荐中…" : "推荐重点" }}
              </a-button>
              <a-button
                v-else-if="
                  conceptMode === 'manual' ||
                  (conceptMode === 'ai' && conceptStage === 'candidates_ready')
                "
                type="primary"
                :loading="loadingAI"
                :disabled="
                  loadingAI ||
                  !burdenPhaseReady ||
                  outlineGenerateDisabled
                "
                @click="onAISearch"
              >
                {{ loadingAI ? "生成中…" : "生成纲目" }}
              </a-button>
            </div>
          </div>
        </div>
      </transition>
    </div>
  </div>
  <a-divider style="margin: 30px 0 10px 0"></a-divider>
  <!-- AI 正在思考的加载动画 -->
  <div class="ai-loading-container" v-if="showInfo == 6">
    <div class="ai-loading">
      <div class="ai-loading-card">
        <div class="loading-content">
          <a-spin size="large">
            <template #indicator>
              <div class="custom-spinner">
                <div class="spinner-dot"></div>
                <div class="spinner-dot"></div>
                <div class="spinner-dot"></div>
              </div>
            </template>
          </a-spin>
          <div class="loading-text">{{ aiLoadingText }}</div>
        </div>
      </div>
    </div>
  </div>

  <!-- AI 问答结果显示 -->
  <div class="ai-result" v-if="showInfo == 5 && aiResult">
    <a-alert type="success" show-icon>
      <template #message>
        <span style="font-size: 16px">✨ <strong style="background: linear-gradient(135deg, #667eea, #764ba2); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">{{ aiModeDisplayText }}</strong> 纲目生成完成</span>
      </template>
    </a-alert>
    <a-divider style="margin: 10px 0"></a-divider>

    <!-- 信息栏：耗时 / 费用 / 缓存 / 概念 / 骨架 -->
    <div class="kg-info-bar">
      <div class="kg-info-stats">
        <span v-if="aiMeta.totalElapsedMs != null">⏱ 耗时 <strong>{{ (aiMeta.totalElapsedMs / 1000).toFixed(1) }}s</strong></span>
        <span v-if="aiMeta.totalCostUsd != null" class="kg-info-sep">💰 <strong>${{ Number(aiMeta.totalCostUsd).toFixed(2) }}</strong></span>
        <a-tag v-if="aiMeta.cached" color="green" style="margin-left: 8px;">缓存结果</a-tag>
      </div>
      <div class="kg-info-row">📌 真理启示：{{ aiMeta.revelation.length ? aiMeta.revelation.join("、") : "无" }}</div>
      <div class="kg-info-row">📌 内在素质：{{ (aiMeta.inner || []).length ? aiMeta.inner.join("、") : "无" }}</div>
      <div class="kg-info-row">📌 生命经历：{{ aiMeta.experience.length ? aiMeta.experience.join("、") : "无" }}</div>
      <div class="kg-info-row">📌 实行应用：{{ aiMeta.practice.length ? aiMeta.practice.join("、") : "无" }}</div>
      <div v-if="aiMeta.skeleton && aiMeta.skeleton.length" class="kg-info-row">
        <div>🦴 骨架：</div>
        <div v-for="(item, i) in aiMeta.skeleton" :key="i" class="kg-skeleton-item">
          {{ typeof item === 'object' ? item.step : item }}
          <span v-if="item && typeof item === 'object' && item.path_evidence" class="kg-skeleton-evidence">↳ {{ formatPathEvidenceDisplay(item.path_evidence) }}</span>
          <span v-if="item && typeof item === 'object' && item.scripture_anchor" class="kg-skeleton-evidence">📖 {{ item.scripture_anchor }}</span>
        </div>
      </div>
    </div>

    <div class="kg-outline-divider">─── 纲目正文 ───</div>

    <!-- 中文纲目 -->
    <transition name="slide-down">
      <div v-if="showAIAnswer" class="ai-answer-card">
        <div class="ai-answer-header">
          <span style="font-weight: bold; color: #667eea;">📝 中文纲目</span>
          <a-button type="text" size="small" @click="copyAiAnswer" class="ai-copy-btn">
            <CheckOutlined v-if="aiAnswerCopied" style="color: #52c41a;" />
            <CopyOutlined v-else />
            {{ aiAnswerCopied ? "已复制" : "复制" }}
          </a-button>
        </div>
        <div class="ai-answer-content" v-html="aiAnswerFormatted"></div>
        <div v-if="aiResult?.answer" class="ai-download-row">
          <span class="ai-download-label">下载格式：</span>
          <a-checkbox-group v-model:value="downloadFormatsZh">
            <a-checkbox value="docx">DOCX</a-checkbox>
            <a-checkbox value="pdf">PDF</a-checkbox>
          </a-checkbox-group>
          <a-button type="primary" size="small" :loading="downloadingZh" :disabled="downloadingZh || downloadFormatsZh.length === 0" @click="downloadFormattedZh">
            <LoadingOutlined v-if="downloadingZh" spin />
            <DownloadOutlined v-else />
            {{ downloadingZh ? "格式化并下载中…" : "刷格式并下载" }}
          </a-button>
        </div>
        <!-- 【4.0】纲目评估已删除（2026-11-11 用户要求） -->
      </div>
    </transition>

    <!-- 英文纲目 -->
    <div v-if="showAIAnswer && includeEnglishOutline" class="ai-answer-card ai-answer-card-en">
      <div class="ai-answer-header">
        <span style="font-weight: bold; color: #667eea;">📝 英文纲目</span>
        <a-button v-if="answerEn" type="text" size="small" @click="copyAiAnswerEn" class="ai-copy-btn">
          <CheckOutlined v-if="aiAnswerEnCopied" style="color: #52c41a;" />
          <CopyOutlined v-else />
          {{ aiAnswerEnCopied ? "已复制" : "复制" }}
        </a-button>
      </div>
      <div v-if="loadingEnglish" class="ai-answer-content ai-answer-loading-en">
        <a-spin size="small" /> 正在生成英文纲目…
      </div>
      <div v-else-if="errorEnglish" class="ai-answer-content ai-answer-error-en">
        {{ errorEnglish }}
      </div>
      <div v-else-if="answerEn" class="ai-answer-content" v-html="aiAnswerEnFormatted"></div>
      <div v-if="answerEn" class="ai-download-row">
        <span class="ai-download-label">下载格式：</span>
        <a-checkbox-group v-model:value="downloadFormatsEn">
          <a-checkbox value="docx">DOCX</a-checkbox>
          <a-checkbox value="pdf">PDF</a-checkbox>
        </a-checkbox-group>
        <a-button type="primary" size="small" :loading="downloadingEn" :disabled="downloadingEn || downloadFormatsEn.length === 0" @click="downloadFormattedEn">
          <LoadingOutlined v-if="downloadingEn" spin />
          <DownloadOutlined v-else />
          {{ downloadingEn ? "格式化并下载中…" : "刷格式并下载" }}
        </a-button>
      </div>
    </div>

    <!-- 繁体纲目 -->
    <div v-if="showAIAnswer && includeTraditionalOutline" class="ai-answer-card ai-answer-card-zh-tw">
      <div class="ai-answer-header">
        <span style="font-weight: bold; color: #2d5016;">📝 繁体纲目</span>
        <a-button v-if="answerZhTw" type="text" size="small" @click="copyAiAnswerZhTw" class="ai-copy-btn">
          <CheckOutlined v-if="aiAnswerZhTwCopied" style="color: #52c41a;" />
          <CopyOutlined v-else />
          {{ aiAnswerZhTwCopied ? "已复制" : "复制" }}
        </a-button>
      </div>
      <div v-if="loadingTraditional" class="ai-answer-content ai-answer-loading-zh-tw">
        <a-spin size="small" /> 正在生成繁体纲目…
      </div>
      <div v-else-if="errorTraditional" class="ai-answer-content ai-answer-error-zh-tw">
        {{ errorTraditional }}
      </div>
      <div v-else-if="answerZhTw" class="ai-answer-content" v-html="aiAnswerZhTwFormatted"></div>
      <div v-if="answerZhTw" class="ai-download-row">
        <span class="ai-download-label">下载格式：</span>
        <a-checkbox-group v-model:value="downloadFormatsZhTw">
          <a-checkbox value="docx">DOCX</a-checkbox>
          <a-checkbox value="pdf">PDF</a-checkbox>
        </a-checkbox-group>
        <a-button type="primary" size="small" :loading="downloadingZhTw" :disabled="downloadingZhTw || downloadFormatsZhTw.length === 0" @click="downloadFormattedZhTw">
          <LoadingOutlined v-if="downloadingZhTw" spin />
          <DownloadOutlined v-else />
          {{ downloadingZhTw ? "格式化并下载中…" : "刷格式并下载" }}
        </a-button>
      </div>
    </div>

    <!-- 引用来源（可折叠） -->
    <div v-if="aiMeta.mainSources.length > 0" class="ai-sources">
      <div class="ai-sources-header" @click="showAISources = !showAISources" style="cursor: pointer;">
        <span style="font-weight: bold; color: #764ba2;">📚 引用来源 ({{ aiMeta.mainSources.length }} 条) {{ showAISources ? '▼' : '▶' }}</span>
      </div>
      <template v-if="showAISources">
        <a-divider style="margin: 8px 0"></a-divider>
        <div v-for="(src, idx) in aiMeta.mainSources" :key="idx" class="source-item">
          <div class="source-title">
            <span style="font-weight: bold; color: #1677ff;">{{ idx + 1 }}. </span>
            <a-tag :color="getSourceLabel(src.chunk_id).color" size="small" style="margin-right: 6px;">{{ getSourceLabel(src.chunk_id).label }}</a-tag>
            <span>{{ formatSourceTitle(src) }}</span>
          </div>
          <div v-if="src.text_preview && getSourceType(src.chunk_id) !== 'firewall'"
               class="source-content"
               style="color: #666; margin-left: 28px; margin-top: 4px; font-size: 13px; line-height: 1.5;">
            {{ src.text_preview }}
          </div>
        </div>
      </template>
    </div>
    
    <div style="margin-bottom: 360px"></div>
  </div>
  <div v-if="showInfo == 3">
    <a-result status="404" title="没有搜到任何内容，请换个关键字试试" />
  </div>
  <div v-if="showInfo == 4" class="spin">
    <a-spin tip="加载中……" size="large" />
  </div>
  <div v-if="aiPanelVisible" class="history-entry-fixed">
    <a-badge :count="pendingConfirmCount" :offset="[-2, 2]">
      <a-button type="primary" @click="historyDrawerOpen = !historyDrawerOpen">暂时保存</a-button>
    </a-badge>
  </div>
  <a-drawer
    v-model:open="historyDrawerOpen"
    title="历史记录"
    placement="right"
    :width="isMobileView ? '100vw' : 460"
    :bodyStyle="isMobileView ? { paddingBottom: 'calc(24px + env(safe-area-inset-bottom))' } : {}"
  >
    <div v-if="historyList.length === 0" class="history-empty">暂无历史记录</div>
    <a-collapse v-else>
      <a-collapse-panel v-for="item in historyList" :key="item.id">
        <template #header>
          <div class="history-item-header">
            <div class="history-item-title">{{ item.query || "（无主题）" }}</div>
            <a-tag :color="item.status === '待确认' ? 'orange' : item.status === '待生成' ? 'blue' : 'green'">
              {{ item.status }}
            </a-tag>
            <span class="history-item-time">{{ item.createdAt }}</span>
          </div>
        </template>
        <div class="history-item-body">
          <div>纲目性质：{{ item.outline_nature || "—" }}</div>
          <div>负担说明：{{ item.burden_description || "—" }}</div>
          <div>真理启示：{{ (item.revelation || []).join("、") || "—" }}</div>
          <div>内在素质：{{ (item.inner || []).join("、") || "—" }}</div>
          <div>生命经历：{{ (item.experience || []).join("、") || "—" }}</div>
          <div>实行应用：{{ (item.practice || []).join("、") || "—" }}</div>
          <div class="history-actions">
            <a-button size="small" @click.stop="loadHistoryRecord(item)">载入</a-button>
            <a-button size="small" @click="setHistoryStatus(item.id, '待生成')">待生成</a-button>
            <a-button size="small" @click="setHistoryStatus(item.id, '已生成')">已生成</a-button>
            <a-button danger size="small" @click="deleteHistoryRecord(item.id)">删除</a-button>
          </div>
        </div>
      </a-collapse-panel>
    </a-collapse>
  </a-drawer>
</template>

<style scoped>
.spin {
  text-align: center;
}
.up,
.down {
  margin: 5px 0;
}
.space {
  margin-bottom: 3px !important;
}
.tag,
.text_tag,
.tag_footer {
  cursor: pointer;
  font-size: 16px;
}
.tag_footer {
  background-color: #fff0f6;
  color: #8316ff;
  padding: 0 5px;
  border-radius: 5px;
}
.res-title {
  color: #1677ff;
  font-size: 17px;
}
.tag:hover {
  background-color: #8316ff;
  color: #fff;
}
.tag_footer:hover {
  background-color: rgb(245, 66, 96);
  color: #fff;
}
.res {
  border: 1px solid #ccc;
  border-radius: 10px;
  margin-bottom: 10px;
  padding: 5px;
  background-color: white;
}
.textindex {
  color: #fff;
  margin-bottom: 5em;
  text-align: justify;
}
.info {
  display: flex;
  justify-content: center;
  align-items: center;
  flex-direction: column;
  margin-top: 20px;
}
.cat {
  width: 80%;
  max-width: 960px;
  background-color: #8316ff;
  border-radius: 10px;
  overflow: hidden;
  padding: 20px;
  margin-bottom: 10px;
  color: #fff;
  font-size: 14px;
}
.paoma {
  width: 80%;
  max-width: 960px;
  background-color: #1677ff;
  border-radius: 10px;
  overflow: hidden;
  padding: 20px;
}
.title {
  color: #1677ff;
  font-weight: bold;
  font-size: 1.2em;
}
.search-box {
  margin-top: 80px;
  display: flex;
  justify-content: center;
}
.search-bar {
  width: 80%;
  max-width: 1000px;
}
.search-result {
  margin: 0 2em;
}
.model {
  margin-top: 5px;
  align-items: center;
}

.ai-mode-switcher {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  align-items: center;
}
.ai-mode-btn {
  padding: 5px 18px;
  border-radius: 8px;
  border: 1.5px solid #b39ddb;
  background: #fff;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  font-style: italic;
  color: #7c3aed;
  letter-spacing: 0.3px;
  transition: all 0.2s;
}
.ai-mode-btn.active {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  border-color: transparent;
}
.ai-mode-btn:hover:not(.active):not(:disabled) {
  background: #f3f0ff;
  border-color: #7c3aed;
}
.ai-mode-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.ai-meta-panel {
  position: relative;
  margin-top: 12px;
  padding: 16px;
  border: 1px solid #e6f4ff;
  background: #fafdff;
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(22, 119, 255, 0.08);
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
  font-size: 14px;
  color: #333;
}

.ai-meta-field > span {
  font-weight: 600;
  color: #222;
}

.ai-meta-field.full {
  grid-column: 1 / -1;
}

.ai-burden-phase {
  border: 1px dashed #d3adf7;
  border-radius: 10px;
  padding: 12px;
  background: #faf5ff;
}

.ai-burden-phase-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.ai-burden-phase-title {
  font-weight: 700;
  color: #391085;
}

.ai-burden-skip {
  font-size: 13px;
  color: #722ed1;
}
.ai-burden-skip--locked {
  pointer-events: none;
  color: #bfbfbf;
  cursor: not-allowed;
}

.ai-burden-phase-inner {
  margin-top: 6px;
}

.ai-burden-btn-wrap {
  margin-top: 10px;
  max-width: 420px;
  margin-left: auto;
  margin-right: auto;
  width: 100%;
}
.ai-burden-btn-wrap :deep(.ant-btn) {
  min-height: 40px;
}

.ai-burden-gen-out {
  margin-top: 10px;
  padding: 10px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #efdbff;
}

.ai-burden-reasoning {
  margin-top: 10px;
  padding: 8px 10px;
  background: #fafafa;
  border-radius: 8px;
  border: 1px dashed #d9d9d9;
}

.ai-burden-reasoning-head {
  font-size: 12px;
  font-weight: 600;
  color: #888;
  cursor: pointer;
  user-select: none;
}

.ai-burden-reasoning-body {
  margin-top: 8px;
  font-size: 12.5px;
  line-height: 1.6;
  color: #555;
  white-space: pre-wrap;
}

.ai-burden-gen-label {
  font-size: 12px;
  font-weight: 600;
  color: #722ed1;
  margin-bottom: 6px;
}

.ai-burden-gen-text {
  font-size: 14px;
  line-height: 1.5;
  color: #333;
}

.ai-burden-radio-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ai-burden-radio-line {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.ai-burden-cand-body {
  flex: 1;
  font-size: 13px;
  line-height: 1.5;
  color: #333;
}

.ai-meta-field input,
.ai-meta-field textarea {
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 14px;
  font-family: inherit;
  resize: none;
  transition: border-color 0.2s;
}

.ai-meta-field .ai-burden-textarea {
  resize: vertical;
  min-height: 72px;
}

.ai-meta-field .ai-skeleton-textarea {
  resize: vertical;
}

.ai-meta-field input:focus,
.ai-meta-field textarea:focus {
  outline: none;
  border-color: #1677ff;
  box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.1);
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
  font-size: 14px;
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

.ai-panel-actions {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.ai-panel-actions > .ai-concept-panel {
  width: 100%;
  max-width: 100%;
  min-width: 0;
}
.concept-mode-toggle {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.ai-concept-panel {
  background: #f6f8fc;
  border: 1px solid #dbe4f0;
  border-radius: 8px;
  padding: 14px 16px;
  width: 100%;
  max-width: 100%;
  min-width: 0;
}
.ai-concept-search-panel {
  padding-bottom: 10px;
}
.ai-concept-search {
  margin-bottom: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  max-width: 100%;
  min-width: 0;
}
.ai-concept-search :deep(.ant-select),
.ai-concept-search :deep(.ant-select-selector),
.ai-concept-search :deep(.ant-input-affix-wrapper),
.ai-concept-search :deep(.ant-input) {
  width: 100% !important;
  max-width: 100% !important;
}
.ai-concept-search :deep(.ant-select),
.ai-concept-search :deep(.ant-select .ant-select-selector) {
  min-width: 0;
}
.ai-concept-hint {
  font-size: 12px;
  color: #888;
  margin-bottom: 10px;
}
.ai-concept-section {
  margin-bottom: 10px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
  width: 100%;
  max-width: 100%;
  min-width: 0;
}
.ai-concept-tags {
  width: 100% !important;
  max-width: 100% !important;
  min-width: 0;
}
.ai-concept-tags :deep(.ant-select) {
  width: 100% !important;
  max-width: 100% !important;
  min-width: 0;
}
.ai-concept-tags :deep(.ant-select-selector) {
  width: 100% !important;
  max-width: 100% !important;
  min-height: 38px;
}
.ai-concept-tags :deep(.ant-select-selection-search-input) {
  color: #222 !important;
  -webkit-text-fill-color: #222 !important;
}
.ai-concept-tags :deep(.ant-select-selection-placeholder) {
  color: #999 !important;
}
/* 人工输入概念：三层 tag 分色 */
.ai-concept-manual .ai-concept-tags--revelation :deep(.ant-select-selection-item) {
  background: #ede7f6 !important;
  border: 1px solid #d1c4e9;
  border-radius: 4px;
}
.ai-concept-manual .ai-concept-tags--inner :deep(.ant-select-selection-item) {
  background: #e6fffb !important;
  border: 1px solid #87e8de;
  border-radius: 4px;
}
.ai-concept-manual .ai-concept-tags--experience :deep(.ant-select-selection-item) {
  background: #e8f5e9 !important;
  border: 1px solid #c8e6c9;
  border-radius: 4px;
}
.ai-concept-manual .ai-concept-tags--practice :deep(.ant-select-selection-item) {
  background: #fff9e6 !important;
  border: 1px solid #ffe58f;
  border-radius: 4px;
}
.ai-concept-manual .ai-concept-tags :deep(.ant-select-selection-item-remove) {
  color: rgba(0, 0, 0, 0.45);
}
.ai-concept-manual .ai-concept-tags :deep(.ant-select-selection-item-remove:hover) {
  color: rgba(0, 0, 0, 0.75);
}
.ai-concept-label {
  font-weight: 600;
  font-size: 13px;
  color: #444;
  white-space: nowrap;
}
.ai-concept-checks {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-start;
  align-items: flex-start;
  width: 100%;
  text-align: left;
  gap: 4px 10px;
}
.ai-concept-empty {
  color: #aaa;
  font-size: 12px;
}
.ai-concept-optional {
  font-weight: 400;
  color: #999;
  font-size: 12px;
}
.ai-history-save-row {
  margin-top: 10px;
}
.ai-concept-warn {
  color: #fa541c;
  font-size: 12px;
  margin-top: 4px;
}

.ai-panel-hint {
  font-size: 13px;
  color: #fa8c16;
}

.ai-panel-cta {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}

.ai-panel-cta :deep(.ant-btn) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 38px;
  min-width: 200px;
  padding: 0 32px;
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

.text_tag {
  margin-left: 5px;
  padding: 3px 12px;
}

.text_tag:hover {
  background-color: #1677ff;
  color: #fff;
}
.footer_fix {
  bottom: 0;
  position: fixed;
  width: 100%;
  background-color: #fff;
  border-top: 1px solid #e7e7e7;
  padding: 10px 0;
  text-align: center;
  color: #777;
}

/* AI 问答样式 */
.ai-result {
  margin: 0 2em;
}
.history-entry-fixed {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 1001;
}
.history-empty {
  color: #999;
}
.history-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}
.history-item-title {
  font-weight: 600;
  flex: 1;
  min-width: 0;
}
.history-item-time {
  color: #999;
  font-size: 12px;
}
.history-eval-score {
  color: #999;
  font-size: 12px;
  white-space: nowrap;
}
.history-item-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
}
.history-actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* AI 加载动画容器 */
.ai-loading-container {
  margin: 0 2em;
}

.ai-loading {
  margin: 40px 0;
  display: flex;
  justify-content: center;
}

.ai-result-loading {
  margin-top: 20px;
}

.ai-loading-card {
  background: linear-gradient(135deg, #667eea10 0%, #764ba210 100%);
  border: 2px solid #667eea;
  border-radius: 16px;
  padding: 60px 80px;
  text-align: center;
  box-shadow: 0 8px 24px rgba(102, 126, 234, 0.2);
  animation: pulse-border 2s ease-in-out infinite;
}

@keyframes pulse-border {
  0%, 100% {
    box-shadow: 0 8px 24px rgba(102, 126, 234, 0.2);
  }
  50% {
    box-shadow: 0 8px 32px rgba(102, 126, 234, 0.4);
  }
}

.loading-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.custom-spinner {
  display: flex;
  gap: 12px;
  align-items: center;
}

.spinner-dot {
  width: 16px;
  height: 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 50%;
  animation: bounce 1.4s ease-in-out infinite;
}

.spinner-dot:nth-child(1) {
  animation-delay: 0s;
}

.spinner-dot:nth-child(2) {
  animation-delay: 0.2s;
}

.spinner-dot:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes bounce {
  0%, 80%, 100% {
    transform: scale(0.8);
    opacity: 0.5;
  }
  40% {
    transform: scale(1.2);
    opacity: 1;
  }
}

.loading-text {
  font-size: 20px;
  font-weight: 600;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: text-glow 2s ease-in-out infinite;
}

@keyframes text-glow {
  0%, 100% {
    opacity: 0.8;
  }
  50% {
    opacity: 1;
  }
}

.loading-tips {
  font-size: 14px;
  color: #666;
  margin-top: -5px;
}

/* 渐进显示过渡效果 */
.fade-slide-enter-active {
  animation: fadeSlideIn 0.6s ease-out;
}

@keyframes fadeSlideIn {
  0% {
    opacity: 0;
    transform: translateY(20px);
  }
  100% {
    opacity: 1;
    transform: translateY(0);
  }
}

/* AI答案从上方滑入效果 */
.slide-down-enter-active {
  animation: slideDownIn 0.8s cubic-bezier(0.34, 1.56, 0.64, 1);
}

@keyframes slideDownIn {
  0% {
    opacity: 0;
    transform: translateY(-30px) scale(0.95);
  }
  60% {
    opacity: 0.8;
    transform: translateY(5px) scale(1.02);
  }
  100% {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

/* 淡入淡出效果 */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

/* AI正在整理答案提示 */
.ai-preparing {
  background: linear-gradient(135deg, #ffeaa710 0%, #ffdd5710 100%);
  border: 2px dashed #f59e0b;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
  text-align: center;
}

.preparing-content {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  font-size: 16px;
  font-weight: 500;
  color: #d97706;
}

.preparing-spinner {
  display: flex;
  gap: 6px;
}

.preparing-spinner .dot {
  width: 8px;
  height: 8px;
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
  border-radius: 50%;
  animation: preparingBounce 1.2s ease-in-out infinite;
}

.preparing-spinner .dot:nth-child(1) {
  animation-delay: 0s;
}

.preparing-spinner .dot:nth-child(2) {
  animation-delay: 0.15s;
}

.preparing-spinner .dot:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes preparingBounce {
  0%, 80%, 100% {
    transform: scale(0.8);
    opacity: 0.5;
  }
  40% {
    transform: scale(1.3);
    opacity: 1;
  }
}

.ai-answer-card {
  background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%);
  border: 2px solid #667eea;
  border-radius: 12px;
  padding: 28px 20px;
  margin-bottom: 20px;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
}

.ai-answer-header {
  font-size: 18px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 12px;
  margin-bottom: 12px;
  border-bottom: 1px solid rgba(102, 126, 234, 0.3);
}

.ai-copy-btn {
  color: #667eea;
  font-size: 14px;
  background-color: rgba(102, 126, 234, 0.2);
  border-radius: 6px;
  padding: 5px 14px;
  border: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.ai-copy-btn:hover {
  color: #764ba2;
  background-color: rgba(118, 75, 162, 0.25);
}

.ai-answer-content {
  line-height: 1.8;
  font-size: 16px;
  color: #333;
  white-space: pre-wrap;
}
.ai-answer-content strong {
  font-weight: 700;
  color: #1a1a2e;
}
.ai-answer-loading-en,
.ai-answer-error-en,
.ai-answer-loading-zh-tw,
.ai-answer-error-zh-tw {
  color: #666;
  padding: 12px 0;
}
.ai-answer-error-en,
.ai-answer-error-zh-tw {
  color: #c41e3a;
}

.ai-download-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid rgba(102, 126, 234, 0.3);
}
.ai-download-row .ai-download-label {
  font-weight: 600;
  color: #333;
  font-size: 14px;
}
.ai-download-row .ant-checkbox-group {
  display: inline-flex;
  gap: 8px;
}

.outline-edit-wrap {
  margin-top: 12px;
}
.report-outline-edit {
  margin-top: 10px;
}
.outline-edit-textarea {
  font-family: inherit;
  line-height: 24px;
}
.eval-improvement-banner {
  background: #fffbe6;
  border: 1px solid #ffe58f;
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 12px;
}
.eval-improvement-title {
  font-weight: 700;
  color: #ad6800;
  margin-bottom: 8px;
}
.eval-improvement-item {
  font-size: 14px;
  line-height: 1.7;
  color: #614700;
  margin-top: 4px;
}
.eval-improvement-note {
  margin-top: 6px;
  font-size: 13px;
  color: #ad6800;
  background: #fffbe6;
  padding: 6px 8px;
  border-radius: 4px;
}

.eval-section {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid rgba(102, 126, 234, 0.25);
}
.eval-action-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.eval-stats {
  color: #666;
  font-size: 13px;
}
.eval-report {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.eval-section-block {
  background: #fafbff;
  border: 1px solid #e8ecf7;
  border-radius: 10px;
  padding: 14px 16px;
}
.eval-section-title {
  font-size: 15px;
  font-weight: 700;
  color: #4c5fd7;
  margin-bottom: 12px;
}
.eval-total-score-card {
  background: linear-gradient(135deg, #667eea12 0%, #764ba212 100%);
  border: 2px solid #667eea;
  border-radius: 12px;
  padding: 16px 20px;
  margin-bottom: 16px;
  text-align: center;
}
.eval-total-score-label {
  font-size: 14px;
  color: #666;
  margin-bottom: 6px;
}
.eval-total-score-value {
  font-size: 32px;
  font-weight: 800;
  color: #4c5fd7;
  line-height: 1.2;
}
.eval-total-score-unit {
  font-size: 18px;
  font-weight: 600;
  color: #888;
}
.eval-scripture-auto-banner {
  font-size: 13px;
  color: #237804;
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 14px;
  line-height: 1.6;
}
.eval-total-score {
  font-size: 20px;
  font-weight: 700;
  color: #333;
  margin-bottom: 14px;
}
.eval-dim-card {
  background: #fff;
  border: 1px solid #eef1f8;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 10px;
}
.eval-dim-card:last-child {
  margin-bottom: 0;
}
.eval-dim-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.eval-dim-score {
  color: #667eea;
  font-weight: 600;
  white-space: nowrap;
}
.eval-comment,
.eval-prescription,
.eval-strength,
.eval-hint,
.eval-golden-summary,
.eval-scripture-reason {
  font-size: 14px;
  line-height: 1.7;
  color: #444;
  margin-top: 6px;
}
.eval-prescription {
  color: #c05621;
  font-weight: 500;
}
.eval-sub-dim-block {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed #eef1f8;
}
.eval-sub-dim-block:first-of-type {
  border-top: none;
  padding-top: 0;
}
.eval-sub-dim-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
}
.eval-sub-dim-label {
  font-size: 13px;
  font-weight: 600;
  color: #333;
}
.eval-sub-dim-score {
  font-size: 13px;
  color: #667eea;
  font-weight: 600;
  white-space: nowrap;
}
.eval-sub-dim-comment {
  font-size: 13px;
  line-height: 1.7;
  color: #555;
  margin-top: 4px;
}
.eval-sub-dim-gap {
  font-size: 13px;
  line-height: 1.6;
  color: #c05621;
  margin-top: 4px;
  padding-left: 2px;
}
.eval-extra-metrics {
  font-size: 13px;
  color: #666;
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid #eef1f8;
}
.eval-summary-line {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid #eef1f8;
  font-weight: 500;
}
.eval-strength {
  color: #237804;
}
.eval-error {
  color: #c41e3a;
  font-size: 13px;
}
.eval-suggested-concepts {
  margin-top: 8px;
  padding: 8px 10px;
  background: #f6ffed;
  border-radius: 6px;
  font-size: 13px;
}
.eval-suggested-title {
  font-weight: 600;
  margin-bottom: 4px;
}
.eval-suggested-row {
  margin-top: 4px;
}
.eval-suggested-label {
  color: #666;
}
.eval-meta-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.eval-q-dots,
.eval-d-rubric {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin: 8px 0;
}
.eval-dot-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.eval-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid #667eea;
  background: transparent;
}
.eval-dot.small {
  width: 10px;
  height: 10px;
}
.eval-dot.filled {
  background: #667eea;
}
.eval-dot-label,
.eval-d-label {
  font-size: 11px;
  color: #888;
}
.eval-d-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.eval-list-block {
  margin-top: 8px;
  font-size: 14px;
}
.eval-list-title {
  font-weight: 600;
  margin-bottom: 4px;
}
.eval-list-block ul {
  margin: 0;
  padding-left: 18px;
}
.t4-comment {
  font-size: 13px;
  line-height: 1.7;
  color: #666;
  margin: 8px 0 0;
}
.t4-supply {
  margin-top: 12px;
  padding: 12px 14px;
  font-size: 15px;
  line-height: 1.85;
  color: #3d2c1e;
  background: linear-gradient(135deg, #fff9f0 0%, #fff4e6 100%);
  border-left: 4px solid #d48806;
  border-radius: 0 8px 8px 0;
}
.scripture-original {
  margin: 8px 0 10px;
  padding: 8px 10px 8px 12px;
  background: #f5f5f0;
  border-left: 2px solid #d9d9d9;
  border-radius: 0 6px 6px 0;
}
.scripture-original .original-label {
  display: block;
  font-size: 11px;
  color: #999;
  margin-bottom: 4px;
}
.scripture-original .original-content {
  margin: 0;
  font-size: 12px;
  line-height: 1.7;
  color: #555;
}
.eval-bottom-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 4px;
}
.btn-download-docx {
  padding: 4px 15px;
  font-size: 14px;
  line-height: 1.5715;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  background: #fff;
  color: rgba(0, 0, 0, 0.88);
  cursor: pointer;
}
.btn-download-docx:hover:not(:disabled) {
  color: #4096ff;
  border-color: #4096ff;
}
.btn-download-docx:disabled {
  color: rgba(0, 0, 0, 0.25);
  border-color: #d9d9d9;
  background: rgba(0, 0, 0, 0.04);
  cursor: not-allowed;
}

.ai-sources {
  background-color: white;
  border: 1px solid #e0e0e0;
  border-radius: 10px;
  padding: 15px;
  margin-bottom: 20px;
}

.ai-sources-header {
  font-size: 17px;
  margin-bottom: 5px;
}

.source-item {
  border-left: 3px solid #764ba2;
  padding: 10px 15px;
  margin-bottom: 15px;
  background-color: #fafafa;
  border-radius: 5px;
}

.source-title {
  font-size: 16px;
  margin-bottom: 8px;
  color: #1677ff;
}

.source-content {
  margin: 8px 0;
  line-height: 1.6;
  color: #555;
  font-size: 14px;
}
.source-meta {
  margin-top: 8px;
}

.claude-payload-section {
  margin-top: 20px;
  margin-bottom: 20px;
}

.claude-payload-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.claude-payload-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.claude-payload-label {
  font-weight: 600;
  color: #555;
  font-size: 13px;
}

.claude-payload-pre {
  margin: 0;
  padding: 12px;
  background: #f5f5f5;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 400px;
  overflow-y: auto;
}

/* KG-RAG 信息栏 */
.kg-info-bar {
  background: linear-gradient(135deg, #f0f5ff 0%, #e6f7ff 100%);
  border: 1px solid #91caff;
  border-radius: 12px;
  padding: 16px 20px;
  margin-bottom: 16px;
}
.kg-info-stats {
  font-size: 15px;
  color: #333;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.kg-info-stats strong {
  color: #1a1a2e;
}
.kg-info-sep {
  margin-left: 16px;
}
.kg-info-row {
  font-size: 14px;
  color: #444;
  margin-top: 6px;
  line-height: 1.6;
}
.kg-skeleton-item {
  padding-left: 20px;
  font-size: 15px;
  color: #555;
  line-height: 1.7;
}
.kg-skeleton-evidence {
  display: block;
  font-size: 13px;
  color: #6090c0;
  padding-left: 8px;
  line-height: 1.4;
}
.kg-outline-divider {
  text-align: center;
  color: #999;
  font-size: 13px;
  margin: 12px 0 16px;
  letter-spacing: 2px;
}

/* ========== 移动端：768px ========== */
@media (max-width: 768px) {
  .search-box {
    margin-top: 56px;
    padding: 0 12px;
  }
  .search-bar {
    width: 100%;
    max-width: 100%;
  }
  .search-bar .search {
    width: 100%;
    max-width: 100%;
  }
  .search-bar :deep(.ant-input-search),
  .search-bar :deep(.ant-input-group) {
    max-width: 100%;
  }
  .search-result,
  .ai-result,
  .ai-loading-container {
    margin: 0 1em;
  }
  .model {
    margin-top: 8px;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }
  .model .ant-radio-group {
    flex-wrap: wrap;
  }
  .model .ant-btn {
    min-height: 40px;
  }
  .cat,
  .paoma {
    width: 95%;
    padding: 14px;
    font-size: 13px;
  }
  .ai-meta-panel {
    padding: 12px;
  }
  .ai-meta-grid {
    grid-template-columns: 1fr;
  }
  .ai-panel-actions {
    flex-direction: column;
    align-items: stretch;
  }
  .ai-concept-search :deep(.ant-select-selector),
  .ai-concept-tags :deep(.ant-select-selector) {
    min-height: 42px;
  }
  :deep(.ant-drawer-content-wrapper) {
    max-width: 100vw !important;
  }
  :deep(.ant-drawer-header) {
    padding-top: calc(16px + env(safe-area-inset-top));
  }
  .ai-panel-cta {
    margin-left: 0;
    flex-direction: column;
    align-items: stretch;
  }
  .ai-panel-cta :deep(.ant-btn) {
    width: 100%;
    min-height: 44px;
  }
  .ai-loading-card {
    padding: 40px 24px;
  }
  .loading-text {
    font-size: 18px;
  }
  .ai-answer-card {
    padding: 20px 14px;
  }
  .ai-answer-content {
    font-size: 15px;
  }
  .source-item {
    padding: 8px 12px;
  }
  .res {
    padding: 8px;
  }
}

/* ========== 移动端：480px ========== */
@media (max-width: 480px) {
  .search-box {
    margin-top: 52px;
    padding: 0 8px;
  }
  .search-bar :deep(.ant-input-group-addon) {
    min-width: 0;
  }
  .search-bar :deep(.ant-select) {
    max-width: 56px;
  }
  .search-result,
  .ai-result,
  .ai-loading-container {
    margin: 0 0.5em;
  }
  .cat,
  .paoma {
    width: 100%;
    padding: 12px;
    font-size: 12px;
  }
  .ai-meta-panel {
    padding: 10px;
  }
  .ai-nature-btn {
    padding: 10px 14px;
    min-height: 44px;
  }
  .ai-loading-card {
    padding: 32px 16px;
  }
  .loading-text {
    font-size: 16px;
  }
  .loading-tips {
    font-size: 13px;
  }
  .ai-answer-header {
    font-size: 16px;
    flex-wrap: wrap;
    gap: 8px;
  }
  .ai-answer-content {
    font-size: 14px;
  }
  .ai-sources-header,
  .source-title {
    font-size: 15px;
  }
  .source-content {
    font-size: 13px;
  }
  .tag,
  .text_tag,
  .tag_footer {
    font-size: 14px;
  }
  .res-title {
    font-size: 15px;
  }
}

.t35-header {
  position: sticky;
  top: 0;
  z-index: 100;
  padding: 10px 20px;
  display: flex;
  align-items: center;
  font-size: large;
  font-weight: bold;
  color: #55bbff;
  background-color: #001529;
}
.t35-header-left {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px 6px 4px;
  margin: -6px 0 -6px -4px;
  user-select: none;
}
.t35-header-left:hover .t35-header-back {
  color: #1677ff;
  transform: scale(1.1);
  transition: 0.2s;
}
.t35-header-backtext {
  font-size: 14px;
}
.t35-header-title {
  flex: 1;
  text-align: center;
}
.t35-header-right {
  width: 64px;
}
.t35-box {
  margin-top: 24px;
}
</style>

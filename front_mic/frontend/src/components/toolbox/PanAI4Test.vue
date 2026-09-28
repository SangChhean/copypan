<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { ArrowLeftOutlined } from "@ant-design/icons-vue";
import axios from "axios";
import { Modal, message } from "ant-design-vue";
import PanAI4Prompts from "./PanAI4Prompts.vue";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";
const api = `${apiBase}/api/panai4`;
const CREATOR_KEY = "panai4_creator";
const NEED_NAME = "请先填写你的名字";
const TEST_DELETED = "所用测试版已删除，请重新选择版本";
const DELETED_CHOICE = "__deleted__";
const PROMPT_STEPS = [
  { step: "burden", name: "Prompt1", label: "负担说明" },
  { step: "skeleton", name: "Prompt2", label: "新生成的龙骨" },
  { step: "orig_skeleton", name: "Prompt3", label: "原纲目的龙骨" },
  { step: "diagnosis", name: "Prompt4", label: "对比诊断" },
];
const STEP_ORDER = { burden: 0, skeleton: 1, orig_skeleton: 5, diagnosis: 6 };

function getAuthHeaders() {
  const token = localStorage.getItem("token") || null;
  if (!token) {
    window.location.hash = "/login";
    return null;
  }
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
}

function blankRow() {
  return { title: "", outline: "", expanded: false };
}

const MAIN_CELLS = [
  { id: "topic", label: "主题" },
  { id: "burden", label: "负担说明" },
  { id: "skeleton", label: "新生成的龙骨" },
  { id: "retrieval", label: "检索", designed: true },
  { id: "generation", label: "生成", designed: true },
  { id: "evaluation", label: "评估", designed: true },
];
const ANALYSIS_CELLS = [
  { id: "orig_skeleton", label: "原纲目的龙骨" },
  { id: "diagnosis", label: "对比诊断" },
];
const RERUN_STEPS = [
  { id: "burden", label: "负担说明" },
  { id: "skeleton", label: "新生成的龙骨" },
  { id: "orig_skeleton", label: "原纲目的龙骨" },
  { id: "diagnosis", label: "对比诊断" },
];
const DESIGNED = new Set(["retrieval", "generation", "evaluation"]);
const OPEN_BY_DEFAULT = new Set(["burden", "skeleton"]);
const BURDEN_TABS = [
  { mark: "【职事界定】", label: "职事界定" },
  { mark: "【真理脉络】", label: "真理脉络" },
  { mark: "【负担说明】", label: "负担说明" },
];
const STATUS_TEXT = {
  pending: "等待",
  running: "进行中",
  done: "完成",
  failed: "失败",
  skipped: "跳过",
  interrupted: "中断",
  queued: "排队中",
  cancelled: "已取消",
};
const ACTIVE = new Set(["queued", "running"]);

const rows = ref([blankRow()]);
const note = ref("");
const sets = ref([]);
const selectedSetId = ref("");
const loadedSetId = ref(null);
const savedSnapshot = ref("");
const meta = ref({ estimate_usd_two_steps: 0.18, estimate_usd_four_steps: 0.3 });
const history = ref([]);
const currentRun = ref(null);
const focusPosition = ref(null);
const mainScope = ref("skeleton");
const analysisScope = ref("diagnosis");
const prices = ref({ burden: 0.15, skeleton: 0.03, orig_skeleton: 0.045, diagnosis: 0.08 });
const cacheHits = ref([]);
const rerunOpen = ref(false);
const rerunStart = ref("skeleton");
const rerunMain = ref("skeleton");
const rerunAnalysis = ref("diagnosis");
const rerunPosition = ref(null);
const rerunChoice = reactive({ burden: "", skeleton: "", orig_skeleton: "", diagnosis: "" });
const tab = ref("run");
const creator = ref(localStorage.getItem(CREATOR_KEY) || "");
const creatorName = computed(() => creator.value.trim());
const creatorNames = ref([]);
const prompts = ref([]);
const promptChoice = reactive({ burden: "", skeleton: "", orig_skeleton: "", diagnosis: "" });
const versionsOpen = ref(false);
const onlyMine = ref(true);
const focusTest = ref(null);
let hitTimer = null;
const nameOpen = ref(false);
const nameText = ref("");
const openMenu = ref(null);
const cardOpen = reactive({});
const manualOpen = reactive({});
const stepOpen = reactive({});
const extraOpen = reactive({});
const burdenTab = reactive({});
const autoKey = ref("");
let timer = null;
let seenRunId = null;

function rowSnapshot() {
  return JSON.stringify(rows.value.map((row) => ({ title: row.title, outline: row.outline })));
}
savedSnapshot.value = rowSnapshot();
const dirty = computed(() => rowSnapshot() !== savedSnapshot.value);
const currentActive = computed(() => ACTIVE.has(currentRun.value?.status));

function testsFor(step) {
  return prompts.value.find((row) => row.step === step)?.tests || [];
}

function currentVersionOf(step) {
  return prompts.value.find((row) => row.step === step)?.current_version || "";
}

function findTest(id) {
  return prompts.value.flatMap((row) => row.tests).find((row) => row.id === Number(id)) || null;
}

function choicePayload(choice) {
  const out = {};
  PROMPT_STEPS.forEach(({ step }) => {
    const value = choice[step];
    if (value && value !== DELETED_CHOICE) out[step] = Number(value);
  });
  return out;
}

function choiceSummary(choice) {
  const parts = [];
  let deleted = false;
  PROMPT_STEPS.forEach(({ step, name }) => {
    const value = choice[step];
    if (!value) return;
    if (value === DELETED_CHOICE) {
      deleted = true;
      parts.push(`${name} 所选测试版已删除`);
      return;
    }
    const test = findTest(value);
    if (test) parts.push(`${name} 使用测试版 ${test.version_name}（${test.created_by}）`);
  });
  return { parts, deleted, all: parts.length === PROMPT_STEPS.length };
}

const footSummary = computed(() => choiceSummary(promptChoice));
const choiceDeleted = computed(() => footSummary.value.deleted);
const estimate = computed(() => {
  const price = prices.value;
  return rows.value.reduce((sum, row, index) => {
    let cost = 0;
    if (mainScope.value === "burden" || mainScope.value === "skeleton") cost += Number(price.burden) || 0;
    if (mainScope.value === "skeleton") cost += Number(price.skeleton) || 0;
    const hasOutline = !!(row.outline || "").trim();
    if (hasOutline && (analysisScope.value === "orig_skeleton" || analysisScope.value === "diagnosis")) {
      if (!cacheHits.value[index]) cost += Number(price.orig_skeleton) || 0;
    }
    if (hasOutline && mainScope.value === "skeleton" && analysisScope.value === "diagnosis") {
      cost += Number(price.diagnosis) || 0;
    }
    return sum + cost;
  }, 0);
});
const scopeBlocked = computed(() => mainScope.value === "none" && analysisScope.value === "none");

function money(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "0.000";
  return num.toFixed(3);
}

function durationText(ms) {
  if (ms == null) return "—";
  const total = Number(ms) / 1000;
  if (total < 60) return `${total.toFixed(1)} 秒`;
  const sec = Math.round(total);
  return `${Math.floor(sec / 60)} 分 ${sec % 60} 秒`;
}

function formatTime(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function itemCost(item) {
  return (item.steps || []).reduce((sum, step) => sum + (Number(step.cost_usd) || 0), 0);
}

function itemDuration(item) {
  return (item.steps || []).reduce((sum, step) => sum + (Number(step.duration_ms) || 0), 0);
}

function statusText(status) {
  return STATUS_TEXT[status] || status || "";
}

function chipClass(status) {
  if (status === "done") return "chip chip-ok";
  if (status === "running") return "chip chip-run";
  if (status === "failed" || status === "interrupted") return "chip chip-err";
  return "chip chip-wait";
}

function itemChipText(item) {
  if (item.status === "running") {
    const step = (item.steps || []).find((row) => row.status === "running");
    return step ? `进行中 · ${step.label}` : "进行中";
  }
  if (item.status === "failed") return item.error ? `失败 · ${item.error}` : "失败";
  return statusText(item.status);
}

function splitBurden(text) {
  if (!text || BURDEN_TABS.some((tab) => !text.includes(tab.mark))) return null;
  const ordered = BURDEN_TABS.map((tab) => ({ ...tab, index: text.indexOf(tab.mark) })).sort((a, b) => a.index - b.index);
  const parts = {};
  ordered.forEach((part, index) => {
    const start = part.index + part.mark.length;
    const end = index + 1 < ordered.length ? ordered[index + 1].index : text.length;
    parts[part.mark] = text.slice(start, end).trim();
  });
  return parts;
}

function stepReason(step) {
  if (step.status === "failed") return step.error || "失败";
  if (step.status === "skipped") return step.output_text || "跳过";
  if (step.status === "cancelled") return "已取消";
  if (step.status === "interrupted") return "中断";
  return "";
}

function stepClosed(step) {
  return ["failed", "skipped", "cancelled", "interrupted"].includes(step.status);
}

function ckey(runId, position) {
  return `${runId}:${position}`;
}

function firstItem(run) {
  return run?.items?.find((item) => item.position === 1) || run?.items?.[0] || null;
}

function initRunView(run) {
  autoKey.value = "";
  const runningPos = run.status === "running" ? run.current?.position : null;
  const first = firstItem(run);
  focusPosition.value = runningPos || first?.position || null;
  (run.items || []).forEach((item) => {
    const key = ckey(run.run_id, item.position);
    cardOpen[key] = false;
    manualOpen[key] = false;
  });
  if (runningPos) openAuto(run, runningPos);
  else if (first) cardOpen[ckey(run.run_id, first.position)] = true;
}

function openAuto(run, position) {
  const key = ckey(run.run_id, position);
  const prev = autoKey.value;
  if (prev && prev !== key && !manualOpen[prev]) cardOpen[prev] = false;
  cardOpen[key] = true;
  autoKey.value = key;
}

const flowItem = computed(() => {
  const run = currentRun.value;
  if (!run?.items?.length) return null;
  return run.items.find((item) => item.position === focusPosition.value) || firstItem(run);
});

function cellOf(stepId) {
  if (stepId === "topic") {
    return currentRun.value && currentRun.value.status !== "queued"
      ? { text: "完成", kind: "done" }
      : { text: "等待", kind: "pending" };
  }
  const step = flowItem.value?.steps?.find((row) => row.step === stepId);
  if (!step) return { text: "等待", kind: "pending" };
  if (step.output_text === "未选择") return { text: "未选择", kind: "unselected" };
  if (step.step === "orig_skeleton" && step.status === "done" && !step.model) {
    const from = step.cache_from_run_id;
    return { text: from ? `沿用缓存（来自运行 #${from}）` : "沿用缓存", kind: "done" };
  }
  let text = statusText(step.status);
  if (step.status === "done" && step.reused_from) text = "完成（沿用）";
  else if (step.status === "done" && step.duration_ms) text = `完成 · ${durationText(step.duration_ms)}`;
  else if (step.status === "skipped") text = step.output_text || "跳过";
  const kind = step.status === "skipped" ? "pending" : step.status === "cancelled" ? "unselected" : step.status;
  return { text, kind };
}

watch(
  () => currentRun.value?.run_id,
  (id) => {
    if (id && id !== seenRunId) {
      seenRunId = id;
      initRunView(currentRun.value);
    }
  }
);

watch(
  () => (currentRun.value?.status === "running" ? currentRun.value?.current?.position : null),
  (position, prev) => {
    const run = currentRun.value;
    if (!run || !position || position === prev) return;
    openAuto(run, position);
    focusPosition.value = position;
  }
);

watch(
  () => currentRun.value?.status,
  (status, prev) => {
    if (prev !== "running" || !status || status === "running") return;
    const first = firstItem(currentRun.value);
    if (first) focusPosition.value = first.position;
  }
);

function onViewChange(event) {
  focusPosition.value = Number(event.target.value);
}

function toggleCard(item) {
  const key = ckey(currentRun.value.run_id, item.position);
  cardOpen[key] = !cardOpen[key];
  if (cardOpen[key]) manualOpen[key] = true;
  focusPosition.value = item.position;
}

function isCardOpen(item) {
  return !!cardOpen[ckey(currentRun.value?.run_id, item.position)];
}

function expandAll(open) {
  const run = currentRun.value;
  if (!run) return;
  run.items.forEach((item) => {
    const key = ckey(run.run_id, item.position);
    cardOpen[key] = open;
    manualOpen[key] = open;
  });
}

function numberSkeleton(text) {
  const lines = String(text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  const marker = /^(?:[-*•]\s+|•|\d+[.、．)]\s*|\d+\s+)/;
  const listed = lines.some((line) => line.trim() && marker.test(line));
  if (listed) {
    let n = 0;
    return lines.map((line) => {
      if (!line.trim() || /^#{1,6}\s?/.test(line)) return line;
      n += 1;
      return `${n}. ${line.replace(marker, "")}`;
    }).join("\n");
  }
  const paragraphs = [];
  let current = [];
  lines.forEach((line) => {
    if (!line.trim()) {
      if (current.length) paragraphs.push(current);
      current = [];
    } else current.push(line);
  });
  if (current.length) paragraphs.push(current);
  const out = [];
  paragraphs.forEach((para, index) => {
    if (out.length) out.push("");
    out.push(`${index + 1}. ${para[0]}`);
    para.slice(1).forEach((line) => out.push(line));
  });
  return out.join("\n");
}

function displayOutput(step) {
  const text = step.output_text || "";
  if (step.step === "skeleton" || step.step === "orig_skeleton") return numberSkeleton(text);
  return text;
}

function stepKey(item, step) {
  return `${currentRun.value?.run_id}:${item.position}:${step.step}`;
}

function isStepOpen(item, step) {
  const key = stepKey(item, step);
  if (Object.prototype.hasOwnProperty.call(stepOpen, key)) return stepOpen[key];
  return OPEN_BY_DEFAULT.has(step.step);
}

function toggleStep(item, step) {
  const key = stepKey(item, step);
  stepOpen[key] = !isStepOpen(item, step);
}

function displayBlocks(item) {
  const blocks = [];
  let designed = [];
  const flush = () => {
    if (!designed.length) return;
    blocks.push({ kind: "skip", names: designed.map((step) => step.label).join(" · ") });
    designed = [];
  };
  (item.steps || []).forEach((step) => {
    if (DESIGNED.has(step.step)) designed.push(step);
    else if (step.output_text === "未选择") {
      flush();
      blocks.push({ kind: "unselected", label: step.label });
    } else {
      flush();
      blocks.push({ kind: "step", step });
    }
  });
  flush();
  return blocks;
}

function toggleExtra(item, step, kind) {
  const key = `${stepKey(item, step)}:${kind}`;
  const opening = !extraOpen[key];
  extraOpen[key] = opening;
  const field = kind === "think" ? "thinking_text" : "prompt_text";
  if (opening && !step[field]) ensureDetail();
}

function extraShown(item, step, kind) {
  return !!extraOpen[`${stepKey(item, step)}:${kind}`];
}

function burdenKey(item) {
  return `${currentRun.value?.run_id}:${item.position}`;
}

function currentBurdenTab(item) {
  return burdenTab[burdenKey(item)] || "【负担说明】";
}

function stepChipText(step) {
  if (step.step === "orig_skeleton" && step.status === "done" && !step.model) {
    return step.cache_from_run_id ? `沿用缓存（来自运行 #${step.cache_from_run_id}）` : "沿用缓存";
  }
  if (step.status === "done" && step.reused_from) return "完成 · 沿用";
  return statusText(step.status);
}

function histSource(run) {
  const text = run.note || "";
  let source = "";
  if (text.startsWith("重跑自 #")) {
    const cut = text.indexOf("。");
    source = cut >= 0 ? text.slice(0, cut) : text;
  } else if (run.parent_run_id) {
    source = `重跑自 #${run.parent_run_id}`;
  }
  if (source && !run.parent_run_id) source = source.replace(/^(重跑自 #\d+)/, "$1（已删除）");
  return source;
}

function histNote(run) {
  const text = run.note || "";
  if (text.startsWith("重跑自 #")) {
    const cut = text.indexOf("。");
    return cut >= 0 ? text.slice(cut + 1) : "";
  }
  return text;
}

function outlineCount(row) {
  return (row.outline || "").length.toLocaleString("zh-CN");
}

async function loadMeta() {
  const headers = getAuthHeaders();
  if (!headers) return;
  const res = await axios.get(`${api}/meta`, { headers });
  meta.value = res.data;
  prices.value = {
    burden: res.data.estimate_usd_burden,
    skeleton: res.data.estimate_usd_skeleton,
    orig_skeleton: res.data.estimate_usd_orig_skeleton,
    diagnosis: res.data.estimate_usd_diagnosis,
  };
}

async function refreshHits() {
  const headers = getAuthHeaders();
  if (!headers) return;
  try {
    const res = await axios.post(
      `${api}/estimate`,
      {
        prompt_tests: choicePayload(promptChoice),
        main_scope: mainScope.value === "none" && analysisScope.value === "none" ? "skeleton" : mainScope.value,
        analysis_scope:
          mainScope.value !== "skeleton" && analysisScope.value === "diagnosis"
            ? "orig_skeleton"
            : analysisScope.value === "none"
              ? "orig_skeleton"
              : analysisScope.value,
        items: rows.value.map((row) => ({ original_outline: row.outline || "" })),
      },
      { headers }
    );
    cacheHits.value = res.data.orig_cache_hits || [];
  } catch {
    cacheHits.value = [];
  }
}

function scheduleHits() {
  if (hitTimer) clearTimeout(hitTimer);
  hitTimer = setTimeout(refreshHits, 400);
}

watch([rows, mainScope, analysisScope, () => promptChoice.orig_skeleton], scheduleHits, { deep: true });
watch(mainScope, (value) => {
  if (value !== "skeleton" && analysisScope.value === "diagnosis") analysisScope.value = "orig_skeleton";
});

async function loadSets() {
  const headers = getAuthHeaders();
  if (!headers) return;
  const res = await axios.get(`${api}/topic_sets`, { headers });
  sets.value = res.data.sets || [];
}

async function loadHistory() {
  const headers = getAuthHeaders();
  if (!headers) return;
  if (onlyMine.value && !creatorName.value) {
    history.value = [];
    return;
  }
  const params = { limit: 50 };
  if (onlyMine.value) params.created_by = creatorName.value;
  const res = await axios.get(`${api}/runs`, { headers, params });
  history.value = res.data.runs || [];
}

async function loadCreators() {
  const headers = getAuthHeaders();
  if (!headers) return;
  try {
    const res = await axios.get(`${api}/creators`, { headers });
    creatorNames.value = res.data.names || [];
  } catch {
    creatorNames.value = [];
  }
}

function markDeletedChoices(choice) {
  PROMPT_STEPS.forEach(({ step }) => {
    const value = choice[step];
    if (value && value !== DELETED_CHOICE && !findTest(value)) choice[step] = DELETED_CHOICE;
  });
}

async function loadPrompts() {
  const headers = getAuthHeaders();
  if (!headers) return;
  const res = await axios.get(`${api}/prompts`, { headers });
  prompts.value = res.data.prompts || [];
  markDeletedChoices(promptChoice);
  markDeletedChoices(rerunChoice);
}

function onPromptsChanged() {
  loadPrompts();
  loadCreators();
}

function saveCreator() {
  const name = creator.value.trim();
  creator.value = name;
  if (name) localStorage.setItem(CREATOR_KEY, name);
  else localStorage.removeItem(CREATOR_KEY);
  loadHistory();
}

watch(onlyMine, () => loadHistory());

function gotoTest(id) {
  focusTest.value = { id, at: Date.now() };
  tab.value = "prompts";
}

function isTestChoice(choice, step) {
  return !!choice[step];
}

function mergeKept(progress) {
  const prev = currentRun.value;
  if (!prev || prev.run_id !== progress.run_id) {
    currentRun.value = progress;
    return;
  }
  const previousSteps = {};
  prev.items.forEach((item) => {
    item.steps.forEach((step) => {
      previousSteps[step.id] = step;
    });
  });
  progress.items.forEach((item) => {
    item.steps.forEach((step) => {
      const old = previousSteps[step.id];
      if (!old) return;
      if ("thinking_text" in old) step.thinking_text = old.thinking_text;
      if ("prompt_text" in old) step.prompt_text = old.prompt_text;
    });
  });
  currentRun.value = progress;
}

async function ensureDetail() {
  const run = currentRun.value;
  const headers = getAuthHeaders();
  if (!run || !headers) return;
  const res = await axios.get(`${api}/runs/${run.run_id}`, { headers });
  currentRun.value = res.data;
}

async function refreshProgress(id) {
  const headers = getAuthHeaders();
  if (!headers) return;
  const res = await axios.get(`${api}/runs/${id}/progress`, { headers });
  mergeKept(res.data);
  if (!ACTIVE.has(res.data.status)) {
    const full = await axios.get(`${api}/runs/${id}`, { headers });
    currentRun.value = full.data;
    await loadHistory();
  }
}

async function tick() {
  if (currentActive.value) await refreshProgress(currentRun.value.run_id);
  await loadHistory();
  if (!currentActive.value && !history.value.some((run) => ACTIVE.has(run.status))) stopTimer();
}

function ensureTimer() {
  if (timer) return;
  timer = setInterval(tick, 3000);
}

function stopTimer() {
  if (timer) clearInterval(timer);
  timer = null;
}

async function openRun(id) {
  const headers = getAuthHeaders();
  if (!headers) return;
  openMenu.value = null;
  const res = await axios.get(`${api}/runs/${id}`, { headers });
  currentRun.value = res.data;
  if (ACTIVE.has(res.data.status)) ensureTimer();
}

function addRow(index) {
  rows.value.splice(index + 1, 0, blankRow());
}

function removeRow(index) {
  if (rows.value.length <= 1) return;
  rows.value.splice(index, 1);
}

function topicItems() {
  return rows.value.map((row) => ({
    title: row.title,
    original_outline: row.outline.trim() ? row.outline : null,
  }));
}

function confirmDiscard() {
  if (!dirty.value) return Promise.resolve(true);
  return new Promise((resolve) => {
    Modal.confirm({
      title: "载入题组",
      content: "页面上的篇目有未保存的改动，载入会覆盖这些内容。",
      okText: "继续载入",
      cancelText: "取消",
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    });
  });
}

async function loadSelected() {
  if (!selectedSetId.value) {
    message.warning("请先选择题组");
    return;
  }
  if (!(await confirmDiscard())) return;
  const headers = getAuthHeaders();
  if (!headers) return;
  const res = await axios.get(`${api}/topic_sets/${selectedSetId.value}`, { headers });
  const items = res.data.items || [];
  rows.value = items.length
    ? items.map((item) => ({ title: item.title || "", outline: item.original_outline || "", expanded: false }))
    : [blankRow()];
  loadedSetId.value = res.data.id;
  savedSnapshot.value = rowSnapshot();
}

function askDeleteSet() {
  if (!loadedSetId.value) return;
  const name = loadedName.value || "这个题组";
  Modal.confirm({
    title: `删除题组「${name}」？删除后无法恢复。`,
    okText: "删除",
    okType: "danger",
    cancelText: "取消",
    onOk: () => removeSet(),
  });
}

async function removeSet() {
  const headers = getAuthHeaders();
  if (!headers || !loadedSetId.value) return;
  try {
    await axios.delete(`${api}/topic_sets/${loadedSetId.value}`, { headers });
    loadedSetId.value = null;
    selectedSetId.value = "";
    savedSnapshot.value = rowSnapshot();
    await loadSets();
    message.success("已删除题组");
  } catch (error) {
    const detail = error.response?.data?.detail;
    message.error(typeof detail === "string" ? detail : "删除失败");
  }
}

function askSaveAs() {
  nameText.value = "";
  nameOpen.value = true;
}

async function confirmSaveAs() {
  const name = nameText.value.trim();
  if (!name) {
    message.warning("请填写题组名称");
    return Promise.reject(new Error("empty"));
  }
  const headers = getAuthHeaders();
  if (!headers) return Promise.reject(new Error("auth"));
  try {
    const res = await axios.post(`${api}/topic_sets`, { name, items: topicItems() }, { headers });
    nameOpen.value = false;
    loadedSetId.value = res.data.id;
    selectedSetId.value = res.data.id;
    savedSnapshot.value = rowSnapshot();
    await loadSets();
    message.success("已另存为题组");
  } catch (error) {
    const detail = error.response?.data?.detail;
    if (error.response?.status === 409) message.warning(typeof detail === "string" ? detail : "名称已存在，请改名");
    else message.error(typeof detail === "string" ? detail : "保存失败");
    return Promise.reject(error);
  }
}

async function saveCurrent() {
  if (!loadedSetId.value) {
    askSaveAs();
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;
  try {
    await axios.put(`${api}/topic_sets/${loadedSetId.value}`, { items: topicItems() }, { headers });
    savedSnapshot.value = rowSnapshot();
    await loadSets();
    message.success("已保存");
  } catch (error) {
    const detail = error.response?.data?.detail;
    message.error(typeof detail === "string" ? detail : "保存失败");
  }
}

async function startRun() {
  if (scopeBlocked.value) return;
  if (!creatorName.value) {
    message.warning(NEED_NAME);
    return;
  }
  if (choiceDeleted.value) {
    versionsOpen.value = true;
    message.warning(TEST_DELETED);
    return;
  }
  const empty = rows.value.findIndex((row) => !row.title.trim());
  if (empty >= 0) {
    message.warning(`第 ${empty + 1} 行篇题为空`);
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;
  try {
    const res = await axios.post(
      `${api}/runs`,
      {
        note: note.value,
        created_by: creatorName.value,
        prompt_tests: choicePayload(promptChoice),
        topic_set_id: loadedSetId.value || null,
        main_scope: mainScope.value,
        analysis_scope: analysisScope.value,
        items: rows.value.map((row) => ({
          title: row.title.trim(),
          original_outline: (row.outline || "").trim() ? row.outline : null,
        })),
      },
      { headers }
    );
    if (res.data.status === "queued") message.info(`已排队，前面还有 ${res.data.queue_ahead} 个`);
    await loadHistory();
    await loadCreators();
    await openRun(res.data.run_id);
    ensureTimer();
  } catch (error) {
    const detail = error.response?.data?.detail;
    if (detail === TEST_DELETED) {
      await loadPrompts();
      versionsOpen.value = true;
    }
    message.error(typeof detail === "string" ? detail : "提交失败");
  }
}

async function postRerun(url, startStep, main, analysis, tests) {
  openMenu.value = null;
  const headers = getAuthHeaders();
  if (!headers) return;
  try {
    const res = await axios.post(
      url,
      {
        start_step: startStep,
        main_scope: main,
        analysis_scope: analysis,
        created_by: creatorName.value,
        prompt_tests: tests,
      },
      { headers }
    );
    if (res.data.status === "queued") message.info(`已排队，前面还有 ${res.data.queue_ahead} 个`);
    await loadHistory();
    await openRun(res.data.run_id);
    ensureTimer();
  } catch (error) {
    const detail = error.response?.data?.detail;
    message.error(typeof detail === "string" ? detail : "重跑失败");
    if (detail === TEST_DELETED) {
      await loadPrompts();
      rerunOpen.value = true;
    }
  }
}

function rerunNeeds(step) {
  if (STEP_ORDER[step] < STEP_ORDER[rerunStart.value]) return false;
  if (step === "burden") return rerunMain.value === "burden" || rerunMain.value === "skeleton";
  if (step === "skeleton") return rerunMain.value === "skeleton";
  if (step === "orig_skeleton") return rerunAnalysis.value === "orig_skeleton" || rerunAnalysis.value === "diagnosis";
  return rerunAnalysis.value === "diagnosis";
}

const rerunBlocked = computed(() => PROMPT_STEPS.some(({ step }) => rerunChoice[step] === DELETED_CHOICE && rerunNeeds(step)));

function presetRerunChoice(run) {
  const selection = run.prompt_selection || {};
  PROMPT_STEPS.forEach(({ step }) => {
    const entry = selection[step];
    if (entry?.kind !== "test" || !entry.id) rerunChoice[step] = "";
    else rerunChoice[step] = entry.deleted || !findTest(entry.id) ? DELETED_CHOICE : entry.id;
  });
}

function askCancel(run) {
  const id = run.run_id ?? run.id;
  const who = run.created_by || "—";
  Modal.confirm({
    title: `取消运行 #${id}？`,
    content: `建立人：${who}。已完成的步骤会保留，其余标为“已取消”。`,
    okText: "取消运行",
    okType: "danger",
    cancelText: "不取消",
    onOk: () => cancelRun(id),
  });
}

async function cancelRun(id) {
  const headers = getAuthHeaders();
  if (!headers) return;
  try {
    await axios.post(`${api}/runs/${id}/cancel`, {}, { headers });
    message.success(`已取消运行 #${id}`);
    if (currentRun.value?.run_id === id) await openRun(id);
    await loadHistory();
  } catch (error) {
    const detail = error.response?.data?.detail;
    message.error(typeof detail === "string" ? detail : "取消失败");
  }
}

function openRerun(startStep, position) {
  const run = currentRun.value;
  if (!run) return;
  openMenu.value = null;
  rerunStart.value = startStep;
  rerunPosition.value = position;
  let main = run.main_scope || "skeleton";
  let analysis = run.analysis_scope || "diagnosis";
  if (startStep === "burden" && main === "none") main = "burden";
  if (startStep === "skeleton") main = "skeleton";
  if (startStep === "orig_skeleton" && analysis === "none") analysis = "orig_skeleton";
  if (startStep === "diagnosis") {
    main = "skeleton";
    analysis = "diagnosis";
  }
  rerunMain.value = main;
  rerunAnalysis.value = analysis;
  presetRerunChoice(run);
  rerunOpen.value = true;
}

function confirmRerun() {
  if (rerunMain.value === "none" && rerunAnalysis.value === "none") {
    message.warning("请至少选择一个步骤");
    return Promise.reject(new Error("scope"));
  }
  if (rerunMain.value !== "skeleton" && rerunAnalysis.value === "diagnosis") {
    message.warning("对比诊断需要新生成的龙骨");
    return Promise.reject(new Error("scope"));
  }
  if (!creatorName.value) {
    message.warning(NEED_NAME);
    return Promise.reject(new Error("name"));
  }
  if (rerunBlocked.value) {
    message.warning(TEST_DELETED);
    return Promise.reject(new Error("deleted"));
  }
  const run = currentRun.value;
  if (!run) return Promise.reject(new Error("run"));
  const url = rerunPosition.value == null
    ? `${api}/runs/${run.run_id}/rerun`
    : `${api}/runs/${run.run_id}/items/${rerunPosition.value}/rerun`;
  rerunOpen.value = false;
  return postRerun(url, rerunStart.value, rerunMain.value, rerunAnalysis.value, choicePayload(rerunChoice));
}

function rerunAll(stepId) {
  openRerun(stepId, null);
}

function rerunOne(position, stepId) {
  openRerun(stepId, position);
}

function askDelete(run) {
  Modal.confirm({
    title: `删除运行 #${run.id}（建立人：${run.created_by || "—"}）？删除后无法恢复。`,
    okText: "删除",
    okType: "danger",
    cancelText: "取消",
    onOk: () => removeRun(run.id),
  });
}

async function removeRun(id) {
  const headers = getAuthHeaders();
  if (!headers) return;
  try {
    await axios.delete(`${api}/runs/${id}`, { headers });
    if (currentRun.value?.run_id === id) currentRun.value = null;
    await loadHistory();
  } catch (error) {
    const detail = error.response?.data?.detail;
    message.error(typeof detail === "string" ? detail : "删除失败");
  }
}

function closeMenu() {
  openMenu.value = null;
}

function filenameFrom(res, fallback) {
  const header = res.headers?.["content-disposition"] || "";
  const matched = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (matched) {
    try {
      return decodeURIComponent(matched[1]);
    } catch {
      return fallback;
    }
  }
  return fallback;
}

async function downloadFile(url, fallback) {
  const headers = getAuthHeaders();
  if (!headers) return;
  const res = await axios.get(url, { headers, responseType: "blob" });
  const blobUrl = URL.createObjectURL(res.data);
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = filenameFrom(res, fallback);
  link.click();
  URL.revokeObjectURL(blobUrl);
}

function downloadStep(item, step) {
  downloadFile(
    `${api}/runs/${currentRun.value.run_id}/items/${item.position}/steps/${step}/docx`,
    `第${item.position}篇_${step}.docx`
  );
}

function downloadItem(item) {
  downloadFile(
    `${api}/runs/${currentRun.value.run_id}/items/${item.position}/export.zip`,
    `第${item.position}篇.zip`
  );
}

function downloadAll() {
  if (!currentRun.value) return;
  downloadFile(`${api}/runs/${currentRun.value.run_id}/export.zip`, `运行${currentRun.value.run_id}.zip`);
}

onMounted(async () => {
  window.addEventListener("click", closeMenu);
  if (!getAuthHeaders()) return;
  await loadMeta();
  await loadPrompts();
  await loadCreators();
  await loadSets();
  await loadHistory();
  const running = history.value.find((run) => ACTIVE.has(run.status));
  const target = running || history.value[0];
  if (target) await openRun(target.id);
  if (running) ensureTimer();
});

onUnmounted(() => {
  window.removeEventListener("click", closeMenu);
  if (hitTimer) clearTimeout(hitTimer);
  stopTimer();
});
</script>

<template>
  <div class="bench">
    <div class="bench-header">
      <div class="header-left" @click="() => (window.location.hash = '/tools')">
        <ArrowLeftOutlined class="header-back" />
      </div>
      <div class="header-title">PanAI 4.0 测试台</div>
    </div>

    <div class="topline">
      <div class="tabs-top" role="tablist">
        <button type="button" class="tabtop" :class="{ active: tab === 'run' }" role="tab" @click="tab = 'run'">运行</button>
        <button type="button" class="tabtop" :class="{ active: tab === 'prompts' }" role="tab" @click="tab = 'prompts'">Prompt 版本</button>
      </div>
      <label class="me">
        <span>我是：</span>
        <input
          v-model="creator"
          class="me-input"
          :class="{ empty: !creatorName }"
          list="panai4-creators"
          :maxlength="30"
          placeholder="填写你的名字"
          @change="saveCreator"
          @blur="saveCreator"
        />
        <datalist id="panai4-creators">
          <option v-for="name in creatorNames" :key="name" :value="name" />
        </datalist>
      </label>
    </div>

    <div v-show="tab === 'prompts'" class="page-single">
      <PanAI4Prompts
        :api="api"
        :get-auth-headers="getAuthHeaders"
        :creator="creatorName"
        :prompts="prompts"
        :focus="focusTest"
        @reload="onPromptsChanged"
      />
    </div>

    <div v-show="tab === 'run'" class="page">
      <div class="main">
        <section class="section">
          <div class="section-head">
            <h2 class="section-title"><span class="section-num">1</span>输入</h2>
            <div class="setbar">
              <label class="meta">题组</label>
              <select v-model="selectedSetId" class="select">
                <option value="">选择题组</option>
                <option v-for="item in sets" :key="item.id" :value="item.id">{{ item.name }}（{{ item.item_count }} 篇）</option>
              </select>
              <button type="button" class="btn" @click="loadSelected">载入</button>
              <button type="button" class="btn" @click="saveCurrent">保存</button>
              <button type="button" class="btn" @click="askSaveAs">另存为</button>
              <button type="button" class="btn" :disabled="!loadedSetId" @click="askDeleteSet">删除</button>
            </div>
          </div>
          <div class="section-body">
            <div class="items">
              <div v-for="(row, index) in rows" :key="index" class="item">
                <div class="item-top">
                  <span class="item-no">第 {{ index + 1 }} 篇</span>
                  <input v-model="row.title" class="title-input" :aria-label="`第${index + 1}篇篇题`" placeholder="输入篇题" />
                  <button type="button" class="btn btn-icon" aria-label="在下面加一篇" @click="addRow(index)">
                    <svg class="icon" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>
                  </button>
                  <button type="button" class="btn btn-icon" aria-label="删除这一篇" :disabled="rows.length <= 1" @click="removeRow(index)">
                    <svg class="icon" viewBox="0 0 24 24"><path d="M5 12h14" /></svg>
                  </button>
                </div>
                <div class="item-outline">
                  <template v-if="row.expanded">
                    <div class="outline-tools">
                      <span class="field-label">{{ (row.outline || "").trim() ? `原纲目 · 已贴 ${outlineCount(row)} 字` : "原纲目" }}</span>
                      <button type="button" class="btn-link" @click="row.expanded = false">收起</button>
                    </div>
                    <textarea v-model="row.outline" class="outline-text" placeholder="原纲目全文" />
                  </template>
                  <div v-else-if="(row.outline || '').trim()" class="outline-bar">
                    <span>原纲目 · 已贴 {{ outlineCount(row) }} 字</span>
                    <button type="button" class="btn-link" @click="row.expanded = true">展开</button>
                  </div>
                  <div v-else class="outline-bar empty">
                    <span>无原纲目：只跑负担说明、新生成的龙骨</span>
                    <button type="button" class="btn-link" @click="row.expanded = true">贴上原纲目</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="section-foot">
            <div class="scopes">
              <div class="scope-line">
                <span class="field-label">主线</span>
                <label><input v-model="mainScope" type="radio" value="none" /> 不跑</label>
                <label><input v-model="mainScope" type="radio" value="burden" /> 只跑负担说明</label>
                <label><input v-model="mainScope" type="radio" value="skeleton" /> 跑到新生成的龙骨</label>
              </div>
              <div class="scope-line">
                <span class="field-label">分析</span>
                <label><input v-model="analysisScope" type="radio" value="none" /> 不跑</label>
                <label><input v-model="analysisScope" type="radio" value="orig_skeleton" /> 只跑原纲目的龙骨</label>
                <label :class="{ muted: mainScope !== 'skeleton' }">
                  <input v-model="analysisScope" type="radio" value="diagnosis" :disabled="mainScope !== 'skeleton'" /> 跑到对比诊断
                </label>
                <span v-if="mainScope !== 'skeleton'" class="meta">对比诊断需要新生成的龙骨</span>
              </div>
              <div class="scope-line version-line">
                <span class="field-label">Prompt 版本</span>
                <div class="versions">
                  <div class="vbar" :class="{ test: footSummary.parts.length, open: versionsOpen }">
                    <svg v-if="footSummary.parts.length" class="icon" viewBox="0 0 24 24"><path d="M12 9v4M12 17h.01" /><circle cx="12" cy="12" r="9" /></svg>
                    <span v-if="!footSummary.parts.length">全部使用当前版</span>
                    <span v-else>{{ footSummary.parts.join("；") }}{{ footSummary.all ? "" : "，其余使用当前版" }}</span>
                    <span class="grow"></span>
                    <button type="button" class="btn-link" @click="versionsOpen = !versionsOpen">{{ versionsOpen ? "收起" : "更改" }}</button>
                  </div>
                  <div v-if="versionsOpen" class="vgrid" :class="{ test: footSummary.parts.length }">
                    <div v-for="item in PROMPT_STEPS" :key="item.step">
                      <label class="field-label" :for="`choice-${item.step}`">{{ item.name }} {{ item.label }}</label>
                      <select :id="`choice-${item.step}`" v-model="promptChoice[item.step]" class="select vselect" :class="{ test: isTestChoice(promptChoice, item.step) }">
                        <option value="">{{ currentVersionOf(item.step) }}（当前版）</option>
                        <option v-if="promptChoice[item.step] === DELETED_CHOICE" :value="DELETED_CHOICE" disabled>（已删除）请重新选择</option>
                        <option v-for="test in testsFor(item.step)" :key="test.id" :value="test.id">{{ test.version_name }} · {{ test.created_by }}</option>
                      </select>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div class="input-foot">
              <div class="note">
                <label class="field-label">备注（这次测什么）</label>
                <input v-model="note" placeholder="例如：测 Prompt1 v0.3，看团体面是否带出" />
              </div>
              <div class="estimate">共 {{ rows.length }} 篇<br /><strong>预估约 {{ money(estimate) }} 美元</strong></div>
              <button type="button" class="btn btn-primary" :disabled="scopeBlocked || !creatorName || choiceDeleted" @click="startRun">开始运行</button>
            </div>
          </div>
          <p v-if="!creatorName" class="warn outside">{{ NEED_NAME }}（页面顶端“我是”）。</p>
          <p v-else-if="scopeBlocked" class="warn outside">请至少选择一个步骤。</p>
          <p v-else-if="choiceDeleted" class="warn outside">{{ TEST_DELETED }}。</p>
        </section>

        <section class="section">
          <div class="section-head">
            <h2 class="section-title"><span class="section-num">2</span>流程</h2>
            <div v-if="currentActive" class="queue">
              <span v-if="currentRun.status === 'queued'" class="chip chip-wait">排队中 · 前面还有 {{ currentRun.queue_ahead }} 个</span>
              <span v-else class="chip chip-run">运行中</span>
              <span class="meta">同时最多跑 {{ currentRun.max_concurrent_runs }} 个</span>
              <button type="button" class="btn btn-sm" @click="askCancel(currentRun)">取消</button>
            </div>
            <div class="flow-viewing" v-if="currentRun">
              <span>运行 #{{ currentRun.run_id }} · 已完成 {{ currentRun.completed_count }} / {{ currentRun.total_count }} 篇 · 累计 {{ money(currentRun.cost_usd) }} 美元</span>
              <label class="meta">当前显示</label>
              <select class="select viewing" :value="focusPosition" @change="onViewChange">
                <option v-for="item in currentRun.items" :key="item.position" :value="item.position">第 {{ item.position }} 篇（{{ statusText(item.status) }}）</option>
              </select>
            </div>
            <div v-else class="meta">尚无选取的运行</div>
          </div>
          <div class="section-body">
            <div class="flow">
              <div class="flow-row">
                <span class="flow-label">主线</span>
                <template v-for="(cell, index) in MAIN_CELLS" :key="cell.id">
                  <span v-if="index" class="connector"></span>
                  <div class="step" :class="cell.designed ? 'todo' : cellOf(cell.id).kind">
                    <div class="step-name">{{ cell.label }}</div>
                    <div class="step-state">{{ cell.designed ? "待设计" : cellOf(cell.id).text }}</div>
                  </div>
                </template>
              </div>
              <div class="flow-row">
                <span class="flow-label">分析</span>
                <template v-for="(cell, index) in ANALYSIS_CELLS" :key="cell.id">
                  <span v-if="index" class="connector"></span>
                  <div class="step" :class="cellOf(cell.id).kind">
                    <div class="step-name">{{ cell.label }}</div>
                    <div class="step-state">{{ cellOf(cell.id).text }}</div>
                  </div>
                </template>
              </div>
            </div>
          </div>
        </section>

        <div class="results-toolbar">
          <h2 class="section-title"><span class="section-num">3</span>结果</h2>
          <div class="toolbar-group">
            <button type="button" class="btn btn-sm" @click="expandAll(true)">全部展开</button>
            <button type="button" class="btn btn-sm" @click="expandAll(false)">全部收起</button>
            <div class="menu-wrap" @click.stop>
              <button type="button" class="btn btn-sm" :disabled="!currentRun" @click="openMenu = openMenu === 'all' ? null : 'all'">
                整次从某一步重跑
                <svg class="icon" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6" /></svg>
              </button>
              <div v-if="openMenu === 'all'" class="menu">
                <button v-for="step in RERUN_STEPS" :key="step.id" type="button" @click="rerunAll(step.id)">{{ step.label }}</button>
              </div>
            </div>
            <button type="button" class="btn btn-sm" :disabled="!currentRun" @click="downloadAll">全部导出</button>
          </div>
        </div>

        <p v-if="!currentRun" class="meta">尚无选取的运行</p>
        <article v-for="item in currentRun?.items || []" :key="item.id" class="card" :class="{ open: isCardOpen(item) }">
          <div class="card-head" @click="toggleCard(item)">
            <svg class="icon chev" viewBox="0 0 24 24"><path d="m9 6 6 6-6 6" /></svg>
            <span class="item-no">第 {{ item.position }} 篇</span>
            <span class="card-title" :title="item.title">{{ item.title }}</span>
            <span :class="chipClass(item.status)" :title="itemChipText(item)">{{ itemChipText(item) }}</span>
            <span class="card-meta">{{ itemCost(item) ? money(itemCost(item)) + " 美元" : "—" }} · {{ durationText(itemDuration(item) || null) }}</span>
            <div class="menu-wrap" @click.stop>
              <button type="button" class="btn btn-sm" @click="openMenu = openMenu === item.position ? null : item.position">
                只重跑这一篇
                <svg class="icon" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6" /></svg>
              </button>
              <div v-if="openMenu === item.position" class="menu">
                <button v-for="step in RERUN_STEPS" :key="step.id" type="button" @click="rerunOne(item.position, step.id)">{{ step.label }}</button>
              </div>
            </div>
            <button type="button" class="btn btn-sm" @click.stop="downloadItem(item)">导出本篇</button>
          </div>
          <div v-if="isCardOpen(item)" class="card-body">
            <template v-for="(block, blockIndex) in displayBlocks(item)" :key="blockIndex">
              <div v-if="block.kind === 'skip'" class="skipline">
                <svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" /><path d="M8 12h8" /></svg>
                {{ block.names }}　跳过（待设计）
              </div>
              <div v-else-if="block.kind === 'unselected'" class="unselected-line">{{ block.label }}　未选择</div>
              <div v-else class="block" :class="{ open: isStepOpen(item, block.step) }">
                <div class="block-head" @click="toggleStep(item, block.step)">
                  <svg class="icon chev" viewBox="0 0 24 24"><path d="m9 6 6 6-6 6" /></svg>
                  <span class="block-name">{{ block.step.label }}</span>
                  <span :class="chipClass(block.step.status === 'skipped' ? 'pending' : block.step.status)">{{ block.step.status === 'skipped' ? '跳过' : stepChipText(block.step) }}</span>
                  <span class="block-meta">
                    <template v-if="block.step.prompt_name">
                      <span v-if="block.step.prompt_test_version_id && block.step.prompt_test_deleted" class="test-tag">{{ block.step.prompt_name }} {{ block.step.prompt_version }}（已删除）</span>
                      <button
                        v-else-if="block.step.prompt_test_version_id"
                        type="button"
                        class="btn-link test-link"
                        :title="`测试版，建立人：${block.step.prompt_test_created_by || '—'}`"
                        @click.stop="gotoTest(block.step.prompt_test_version_id)"
                      >{{ block.step.prompt_name }} {{ block.step.prompt_version }}</button>
                      <template v-else>{{ block.step.prompt_name }} {{ block.step.prompt_version }}</template>
                    </template>
                    <template v-if="block.step.input_tokens != null"> · 输入 {{ block.step.input_tokens.toLocaleString('zh-CN') }} / 输出 {{ block.step.output_tokens.toLocaleString('zh-CN') }}</template>
                    <template v-if="block.step.cost_usd != null"> · {{ money(block.step.cost_usd) }} 美元</template>
                    <template v-if="block.step.duration_ms != null"> · {{ durationText(block.step.duration_ms) }}</template>
                    <template v-if="stepClosed(block.step)"> · {{ stepReason(block.step) }}</template>
                  </span>
                  <button
                    v-if="block.step.status === 'done'"
                    type="button"
                    class="btn btn-sm"
                    @click.stop="downloadStep(item, block.step.step)"
                  >导出 docx</button>
                </div>
                <div v-if="isStepOpen(item, block.step)" class="block-body">
                  <p v-if="stepClosed(block.step)" class="reason">{{ stepReason(block.step) }}</p>
                  <template v-else-if="block.step.step === 'burden' && splitBurden(block.step.output_text)">
                    <div class="tabs">
                      <button
                        v-for="tab in BURDEN_TABS"
                        :key="tab.mark"
                        type="button"
                        class="tab"
                        :class="{ active: currentBurdenTab(item) === tab.mark }"
                        @click="burdenTab[burdenKey(item)] = tab.mark"
                      >{{ tab.label }}</button>
                    </div>
                    <div class="output">{{ splitBurden(block.step.output_text)[currentBurdenTab(item)] }}</div>
                  </template>
                  <div v-else class="output">{{ displayOutput(block.step) }}</div>
                  <div class="block-links">
                    <button type="button" class="btn-link" @click="toggleExtra(item, block.step, 'think')">查看思考过程</button>
                    <button type="button" class="btn-link" @click="toggleExtra(item, block.step, 'prompt')">查看送出的 prompt</button>
                  </div>
                  <div v-if="extraShown(item, block.step, 'think')" class="output extra">{{ block.step.thinking_text || "（无）" }}</div>
                  <div v-if="extraShown(item, block.step, 'prompt')" class="output extra">{{ block.step.prompt_text || "（无）" }}</div>
                </div>
              </div>
            </template>
          </div>
        </article>
      </div>

      <aside class="section aside">
        <div class="section-head">
          <h2 class="section-title"><span class="section-num">4</span>历史记录</h2>
          <label class="toggle"><input v-model="onlyMine" type="checkbox" /> 只看我的</label>
        </div>
        <div class="section-body">
          <div
            v-for="run in history"
            :key="run.id"
            class="hist"
            :class="{ selected: currentRun?.run_id === run.id }"
            @click="openRun(run.id)"
          >
            <div class="hist-top">
              <span class="hist-no">#{{ run.id }}</span>
              <span class="hist-actions">
                <span :class="chipClass(run.status)">{{ statusText(run.status) }}</span>
                <button
                  v-if="!ACTIVE.has(run.status)"
                  type="button"
                  class="hist-del"
                  :aria-label="`删除运行 #${run.id}`"
                  @click.stop="askDelete(run)"
                >
                  <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M4 7h16" />
                    <path d="M9 7V5h6v2" />
                    <path d="M8 7l1 12h6l1-12" />
                  </svg>
                </button>
              </span>
            </div>
            <div class="hist-line">{{ run.created_by || "—" }} · {{ formatTime(run.created_at) }} · {{ run.item_count }} 篇 · {{ money(run.cost_usd) }} 美元</div>
            <div v-if="run.status === 'queued'" class="hist-line">前面还有 {{ run.queue_ahead }} 个</div>
            <div v-if="run.uses_test" class="hist-tags"><span class="chip chip-test">含测试版</span></div>
            <div v-if="histSource(run)" class="hist-src">{{ histSource(run) }}</div>
            <div v-if="histNote(run)" class="hist-note">{{ histNote(run) }}</div>
          </div>
          <p v-if="onlyMine && !creatorName" class="meta">填写顶端的名字后，这里只列出你建立的运行。</p>
          <p v-else-if="!history.length" class="meta">还没有运行。</p>
        </div>
      </aside>
    </div>

    <a-modal v-model:open="rerunOpen" title="确认要跑到哪里" ok-text="开始重跑" cancel-text="取消" @ok="confirmRerun">
      <p class="meta">从「{{ ({ burden: "负担说明", skeleton: "新生成的龙骨", orig_skeleton: "原纲目的龙骨", diagnosis: "对比诊断" })[rerunStart] }}」重跑。预设为这次运行原来的选择。</p>
      <div class="scopes dialog-scopes">
        <div class="scope-line">
          <span class="field-label">主线</span>
          <label><input v-model="rerunMain" type="radio" value="none" :disabled="rerunStart === 'skeleton' || rerunStart === 'diagnosis'" /> 不跑</label>
          <label><input v-model="rerunMain" type="radio" value="burden" :disabled="rerunStart === 'skeleton' || rerunStart === 'diagnosis'" /> 只跑负担说明</label>
          <label><input v-model="rerunMain" type="radio" value="skeleton" /> 跑到新生成的龙骨</label>
        </div>
        <div class="scope-line">
          <span class="field-label">分析</span>
          <label><input v-model="rerunAnalysis" type="radio" value="none" :disabled="rerunStart === 'orig_skeleton' || rerunStart === 'diagnosis'" /> 不跑</label>
          <label><input v-model="rerunAnalysis" type="radio" value="orig_skeleton" :disabled="rerunStart === 'diagnosis'" /> 只跑原纲目的龙骨</label>
          <label>
            <input v-model="rerunAnalysis" type="radio" value="diagnosis" :disabled="rerunMain !== 'skeleton'" /> 跑到对比诊断
          </label>
          <span v-if="rerunMain !== 'skeleton'" class="meta">对比诊断需要新生成的龙骨</span>
        </div>
      </div>
      <p class="field-label dialog-label">Prompt 版本（预设为这次运行原来的选择）</p>
      <div class="vgrid dialog-vgrid">
        <div v-for="item in PROMPT_STEPS" :key="item.step">
          <label class="field-label" :for="`rerun-${item.step}`">{{ item.name }} {{ item.label }}</label>
          <select
            :id="`rerun-${item.step}`"
            v-model="rerunChoice[item.step]"
            class="select vselect"
            :class="{ test: isTestChoice(rerunChoice, item.step), bad: rerunChoice[item.step] === DELETED_CHOICE && rerunNeeds(item.step) }"
          >
            <option value="">{{ currentVersionOf(item.step) }}（当前版）</option>
            <option v-if="rerunChoice[item.step] === DELETED_CHOICE" :value="DELETED_CHOICE" disabled>（已删除）请重新选择</option>
            <option v-for="test in testsFor(item.step)" :key="test.id" :value="test.id">{{ test.version_name }} · {{ test.created_by }}</option>
          </select>
        </div>
      </div>
      <p v-if="rerunBlocked" class="warn">{{ TEST_DELETED }}。</p>
    </a-modal>
    <a-modal v-model:open="nameOpen" title="另存为题组" ok-text="保存" cancel-text="取消" @ok="confirmSaveAs">
      <a-input v-model:value="nameText" placeholder="题组名称" @pressEnter="confirmSaveAs" />
    </a-modal>
  </div>
</template>

<style scoped>
.bench {
  --bg:#f3f1ec;
  --panel:#ffffff;
  --subtle:#faf9f6;
  --sunken:#f0ede6;
  --line:#e2ddd2;
  --line-strong:#cfc8b9;
  --ink:#1f1d1a;
  --ink-2:#55504a;
  --ink-3:#8a8479;
  --primary:#1e3a5f;
  --primary-soft:#e6edf6;
  --ok:#2f6b3a;
  --ok-soft:#e5f0e3;
  --run:#9a5b12;
  --run-soft:#fbeedc;
  --err:#a8322a;
  --err-soft:#f8e4e1;
  --wait:#6b665d;
  --wait-soft:#eeebe4;
  --test:#6a3fa0;
  --test-soft:#efe8f8;
  --radius:12px;
  --radius-sm:8px;
  --shadow:0 1px 2px rgba(31,29,26,.05), 0 2px 8px rgba(31,29,26,.04);
  --font:"PingFang SC","Microsoft YaHei","Noto Sans SC",sans-serif;
  --font-title:"Songti SC","STSong","SimSun","Noto Serif SC",serif;
  min-height: 100vh;
  background: var(--bg);
  color: var(--ink);
  font-family: var(--font);
  font-size: 14px;
  line-height: 1.6;
}
.bench :deep(button),
.bench :deep(input),
.bench :deep(textarea),
.bench :deep(select) {
  font: inherit;
  color: inherit;
}
.bench-header {
  padding: 10px 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: large;
  font-weight: bold;
  color: #55bbff;
  background-color: #001529;
}
.header-left { cursor: pointer; display: flex; align-items: center; }
.header-left:hover .header-back { color: #1677ff; transform: scale(1.1); transition: 0.2s; }
.header-title { flex: 1; text-align: center; }

.page { max-width: 1600px; margin: 0 auto; padding: 24px 32px 48px; display: grid; grid-template-columns: minmax(0,1fr) 300px; gap: 24px; align-items: start; }
.main { display: flex; flex-direction: column; gap: 20px; min-width: 0; }
.section { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden; }
.section-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 20px; border-bottom: 1px solid var(--line); }
.section-title { display: flex; align-items: center; gap: 10px; margin: 0; font-size: 16px; font-weight: 700; }
.section-num { width: 24px; height: 24px; border-radius: 50%; background: var(--primary); color: #fff; font-size: 13px; display: inline-flex; align-items: center; justify-content: center; }
.section-body { padding: 20px; }
.section-foot { padding: 16px 20px; background: var(--sunken); border-top: 1px solid var(--line); }
.meta { font-size: 12px; color: var(--ink-3); }
.btn { height: 36px; padding: 0 14px; border: 1px solid var(--line-strong); background: var(--panel); border-radius: var(--radius-sm); cursor: pointer; display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
.btn:hover { background: var(--subtle); }
.btn-sm { height: 30px; padding: 0 10px; font-size: 13px; }
.btn-icon { width: 36px; padding: 0; justify-content: center; }
.btn.btn-primary { background: var(--primary); border-color: var(--primary); color: #ffffff; font-weight: 700; height: 42px; padding: 0 24px; }
.btn.btn-primary:hover { background: #16304f; color: #ffffff; }
.btn.btn-primary[disabled],
.btn.btn-primary:disabled { background: #e6e6e6; border-color: #d9d9d9; color: #595959; }
.btn[disabled] { background: var(--sunken); color: var(--ink-3); border-color: var(--line); cursor: not-allowed; }
.bench .btn-link { border: 0; background: none; padding: 0; color: #2f6fdb; cursor: pointer; font-size: 13px; }
.bench .btn-link:hover { color: #1a4fad; text-decoration: underline; }
.icon { width: 16px; height: 16px; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; flex-shrink: 0; }
.chip { display: inline-flex; align-items: center; gap: 6px; height: 24px; padding: 0 10px; border-radius: 12px; font-size: 12px; font-weight: 600; white-space: nowrap; max-width: 420px; overflow: hidden; text-overflow: ellipsis; }
.chip::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
.chip-ok { background: var(--ok-soft); color: var(--ok); }
.chip-run { background: var(--run-soft); color: var(--run); }
.chip-err { background: var(--err-soft); color: var(--err); }
.chip-wait { background: var(--wait-soft); color: var(--wait); }
.setbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.select { height: 36px; min-width: 260px; padding: 0 10px; border: 1px solid var(--line-strong); border-radius: var(--radius-sm); background: var(--panel); }
.items { display: flex; flex-direction: column; gap: 12px; }
.item { border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--subtle); }
.item-top { display: flex; align-items: center; gap: 10px; padding: 12px; }
.item-no { flex-shrink: 0; min-width: 52px; height: 26px; padding: 0 8px; border-radius: 13px; background: var(--primary-soft); color: var(--primary); font-size: 12px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center; }
.field-label { display: block; font-size: 12px; color: var(--ink-3); margin-bottom: 4px; }
.title-input { flex-grow: 1; height: 40px; padding: 0 12px; border: 1px solid var(--line-strong); border-radius: var(--radius-sm); background: var(--panel); font-size: 15px; min-width: 0; }
.item-outline { padding: 0 12px 12px 74px; }
.outline-tools { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.outline-tools .field-label { margin: 0; }
.outline-bar { display: flex; align-items: center; justify-content: space-between; height: 38px; padding: 0 12px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--panel); font-size: 13px; color: var(--ink-2); }
.outline-bar.empty { border-style: dashed; background: transparent; color: var(--ink-3); }
.outline-text { width: 100%; height: 220px; padding: 12px 14px; border: 1px solid var(--line-strong); border-radius: var(--radius-sm); background: var(--panel); line-height: 1.8; font-size: 13px; resize: vertical; }
.input-foot { display: flex; align-items: flex-end; gap: 16px; }
.note { flex-grow: 1; }
.note input { width: 100%; height: 40px; padding: 0 12px; border: 1px solid var(--line-strong); border-radius: var(--radius-sm); background: var(--panel); }
.estimate { font-size: 13px; color: var(--ink-2); text-align: right; line-height: 1.5; }
.estimate strong { color: var(--ink); font-size: 15px; }
.warn { margin: 0; font-size: 13px; color: var(--run); }
.warn.outside { padding: 10px 20px 14px; }
.flow { display: flex; flex-direction: column; gap: 14px; }
.flow-row { display: flex; align-items: center; gap: 0; flex-wrap: wrap; }
.flow-label { width: 56px; flex-shrink: 0; font-size: 12px; font-weight: 700; color: var(--ink-3); }
.step { min-width: 132px; padding: 8px 14px; border-radius: var(--radius-sm); border: 1px solid var(--line); background: var(--panel); text-align: center; }
.step-name { font-size: 13px; font-weight: 700; }
.step-state { font-size: 11px; color: var(--ink-3); }
.step.done { background: var(--ok-soft); border-color: #c7ddc3; }
.step.done .step-state { color: var(--ok); }
.step.running { background: var(--primary); border-color: var(--primary); color: #fff; }
.step.running .step-state { color: #d8e3f1; }
.step.failed { background: var(--err-soft); border-color: #ebc3be; }
.step.failed .step-state { color: var(--err); }
.step.pending { background: var(--panel); }
.step.todo { background: transparent; border-style: dashed; color: var(--ink-3); }
.step.unselected { background: var(--sunken); border-style: solid; border-color: var(--line-strong); color: var(--ink-3); }
.unselected-line { display: flex; align-items: center; gap: 10px; padding: 10px 14px; border: 1px solid var(--line-strong); border-radius: var(--radius-sm); background: var(--sunken); color: var(--ink-3); font-size: 13px; }
.scopes { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }
.scope-line { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; font-size: 13px; }
.scope-line .field-label { margin: 0; min-width: 28px; }
.dialog-scopes { margin-top: 12px; }
.muted { color: var(--ink-3); }
.connector { width: 28px; height: 2px; background: var(--line-strong); flex-shrink: 0; }
.flow-viewing { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--ink-2); flex-wrap: wrap; justify-content: flex-end; }
.select.viewing { min-width: 160px; height: 30px; font-size: 13px; }
.results-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 0 4px; }
.results-toolbar h2 { margin: 0; }
.toolbar-group { display: flex; gap: 8px; flex-wrap: wrap; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow); overflow: visible; }
.card-head { display: flex; align-items: center; gap: 12px; padding: 14px 18px; cursor: pointer; }
.card-head:hover { background: var(--subtle); }
.card.open .card-head { border-bottom: 1px solid var(--line); background: var(--subtle); }
.chev { transition: transform .15s; }
.card.open > .card-head .chev,
.block.open > .block-head .chev { transform: rotate(90deg); }
.card-title { flex-grow: 1; min-width: 0; font-family: var(--font-title); font-size: 17px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.card-meta { font-size: 12px; color: var(--ink-3); white-space: nowrap; }
.card-body { padding: 16px 18px; display: flex; flex-direction: column; gap: 12px; }
.block { border: 1px solid var(--line); border-radius: var(--radius-sm); overflow: hidden; background: var(--panel); }
.block-head { display: flex; align-items: center; gap: 10px; padding: 10px 14px; background: var(--panel); cursor: pointer; }
.block-name { font-weight: 700; font-size: 14px; }
.block-meta { margin-left: auto; font-size: 12px; color: var(--ink-3); white-space: nowrap; }
.block-body { border-top: 1px solid var(--line); background: var(--subtle); }
.tabs { display: flex; gap: 4px; padding: 8px 14px 0; background: var(--sunken); border-bottom: 1px solid var(--line); }
.tab { padding: 6px 14px; border-radius: 6px 6px 0 0; font-size: 13px; color: var(--ink-2); border: 1px solid transparent; border-bottom: 0; cursor: pointer; background: none; }
.tab.active { background: var(--subtle); border-color: var(--line); color: var(--ink); font-weight: 700; margin-bottom: -1px; }
.output { padding: 14px 18px; font-size: 14px; line-height: 1.95; white-space: pre-wrap; max-height: 420px; overflow: auto; user-select: text; }
.block-links { display: flex; gap: 18px; padding: 8px 18px 12px; }
.reason { margin: 0; padding: 12px 18px 0; color: var(--ink-2); }
.skipline { display: flex; align-items: center; gap: 10px; padding: 10px 14px; border: 1px dashed var(--line-strong); border-radius: var(--radius-sm); color: var(--ink-3); font-size: 13px; }
.aside { position: sticky; top: 16px; max-height: calc(100vh - 32px); display: flex; flex-direction: column; }
.aside .section-body { padding: 12px; overflow: auto; display: flex; flex-direction: column; gap: 8px; }
.hist { display: block; width: 100%; text-align: left; padding: 10px 12px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--panel); cursor: pointer; }
.hist:hover { background: var(--subtle); }
.hist.selected { border-color: var(--primary); background: var(--primary-soft); }
.hist-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.hist-actions { display: inline-flex; align-items: center; gap: 4px; }
.hist-del { width: 24px; height: 24px; border: 0; background: none; padding: 0; color: var(--ink-3); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; }
.hist-del:hover { color: var(--err); }
.hist-no { font-weight: 700; font-size: 14px; }
.hist-line { font-size: 12px; color: var(--ink-3); }
.hist-note { font-size: 12px; color: var(--ink-2); margin-top: 2px; }
.hist-src { font-size: 12px; color: var(--primary); margin-top: 2px; }
.menu-wrap { position: relative; }
.menu { position: absolute; right: 0; top: calc(100% + 4px); z-index: 5; min-width: 140px; background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius-sm); box-shadow: var(--shadow); display: flex; flex-direction: column; padding: 4px; }
.menu button { border: 0; background: none; text-align: left; padding: 6px 10px; border-radius: 6px; cursor: pointer; }
.menu button:hover { background: var(--subtle); }
.extra { margin: 0 18px 12px; background: var(--panel); border-radius: var(--radius-sm); }
.topline { max-width: 1600px; margin: 0 auto; padding: 16px 32px 0; display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; }
.tabs-top { display: flex; gap: 4px; border-bottom: 1px solid var(--line-strong); flex-grow: 1; }
.tabtop { padding: 10px 22px; font-size: 15px; font-weight: 600; color: var(--ink-2); background: none; border: 1px solid transparent; border-bottom: 0; border-radius: 10px 10px 0 0; cursor: pointer; }
.tabtop.active { background: var(--panel); border-color: var(--line-strong); color: var(--primary); margin-bottom: -1px; }
.me { display: flex; align-items: center; gap: 6px; font-size: 14px; color: var(--ink-2); padding-bottom: 6px; white-space: nowrap; }
.me-input { width: 200px; height: 34px; padding: 0 10px; border: 1px solid var(--line-strong); border-radius: var(--radius-sm); background: var(--panel); }
.me-input.empty { border-color: var(--run); background: var(--run-soft); }
.page-single { max-width: 1600px; margin: 0 auto; padding: 24px 32px 48px; }
.chip-test { background: var(--test-soft); color: var(--test); }
.version-line { align-items: flex-start; }
.version-line > .field-label { padding-top: 10px; }
.versions { flex-grow: 1; min-width: 0; }
.vbar { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--panel); font-size: 13px; }
.vbar .grow { flex-grow: 1; }
.vbar.test { border-color: #cdb8ea; background: var(--test-soft); color: var(--test); font-weight: 600; }
.vbar.open { border-bottom-left-radius: 0; border-bottom-right-radius: 0; }
.vgrid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; padding: 12px; border: 1px solid var(--line); border-top: 0; border-radius: 0 0 var(--radius-sm) var(--radius-sm); background: var(--panel); }
.vgrid.test { border-color: #cdb8ea; }
.dialog-vgrid { grid-template-columns: repeat(2, minmax(0, 1fr)); border-top: 1px solid var(--line); border-radius: var(--radius-sm); }
.dialog-label { margin: 14px 0 6px; }
.select.vselect { width: 100%; min-width: 0; height: 34px; font-size: 13px; }
.select.vselect.test { border-color: var(--test); color: var(--test); font-weight: 600; }
.select.vselect.bad { border-color: var(--err); color: var(--err); }
.queue { display: flex; align-items: center; gap: 10px; font-size: 13px; margin-left: auto; }
.bench .btn-link.test-link { color: var(--test); font-weight: 600; font-size: 12px; }
.bench .btn-link.test-link:hover { color: #4f2a7e; }
.test-tag { color: var(--test); font-weight: 600; opacity: .75; }
.toggle { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--ink-2); cursor: pointer; }
.hist-tags { margin-top: 4px; }
</style>

<script setup>
import { ref, reactive, watch, onMounted, computed } from "vue";
import { ArrowLeftOutlined, CheckOutlined, CopyOutlined, DownloadOutlined } from "@ant-design/icons-vue";
import axios from "axios";
import { message } from "ant-design-vue";
import { toastSuccess } from "../utils/Dialog";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";
const activeTab = ref("query");

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

// ---------- 健康状态 ----------
const healthLoading = ref(false);
const health = ref(null);

async function fetchHealth() {
  const headers = getAuthHeaders();
  if (!headers) return;
  healthLoading.value = true;
  try {
    const res = await axios.get(`${apiBase}/api/kg_rag/health`, { headers });
    health.value = res.data;
  } catch (e) {
    health.value = null;
    message.error(e.response?.data?.error || e.message || "健康检查失败");
  } finally {
    healthLoading.value = false;
  }
}

// ---------- Tab 1：全流程查询 ----------
const queryText = ref("");
const queryLoading = ref(false);
const queryResult = ref(null);
/** 并发 Opus 4.7 对比：主流程完成后用 Step4 prompt 调 generate_step5（Opus 4.7） */
const queryResultOpus = ref(null);
const compareOpus = ref(false);
const compareOpusPromptUnavailable = ref(false);
const opusCompareError = ref("");
const opusOutlineCopied = ref(false);

/** 与后端 KG-RAG 约定一致的 Claude 模型 ID（全流程下拉） */
const claudeModelOptions = [
  { value: "claude-sonnet-4-6", label: "Claude Sonnet 4.6" },
  { value: "claude-opus-4-6", label: "Claude Opus 4.6" },
];

/** Step1~2 对比测试：固定 2 个 Claude + 2 个 GPT，多选并行 */
const step12BenchmarkModels = [
  { value: "claude-sonnet-4-6", label: "Claude Sonnet 4.6" },
  { value: "claude-opus-4-6", label: "Claude Opus 4.6" },
  { value: "claude-opus-4-7", label: "Claude Opus 4.7" },
  { value: "gpt-5.4", label: "GPT-5.4" },
  { value: "gpt-5.4-thinking", label: "GPT-5.4 Thinking" },
];

// 检索 + LLM 可调参数（与后端 DEFAULT_PARAMS 对齐；Step1/2 拆分调试见「Step1~2 测试」Tab）
const params = ref({
  bm25_top_k: 30,
  dense_top_k: 0, // 0：后端按 bm25_top_k / dense 路数自动计算每路 top_k
  num_candidates: 100,
  rrf_k: 60,
  bm25_weight: 1,
  dense_weight: 1,
  rerank_top_n: 15,
  skeleton_route_top_k: 45,
  skeleton_route_max_per_node: 15, // 路3 每扩展节点去重后并入条数
  temperature: 0.3,
  llm_model: "claude-sonnet-4-6",
  skip_query_rewrite: false,
  skip_skeleton_route: false,
  skip_generation: false,
  skip_cache: false,
});

/** 纲目制作（与后端 params 字段名一致；由 buildQueryParams 并入请求） */
const audience = ref("");
const burdenDescription = ref("");
const outlineNature = ref("一般性");
const depth = ref("general");

/** 纲目翻译 / 繁体（全流程 Step5 完成后按需请求 ai_search 接口） */
const includeEnglish = ref(false);
const includeTraditional = ref(false);
const englishOutline = ref("");
const traditionalOutline = ref("");
const translating = ref(false);
/** Step5 纲目展示 Tab：zh | en | tw */
const outlineResultTab = ref("zh");

function buildQueryParams() {
  return {
    ...params.value,
    audience: audience.value,
    burden_description: burdenDescription.value,
    outline_nature: outlineNature.value,
    depth: depth.value,
  };
}

// ---------- 两阶段概念抽取 ----------
const conceptStage = ref("idle"); // idle | candidates_ready | generating
const conceptLoading = ref(false);
const conceptCandidates = ref(null); // { surface, deep_candidates, reasoning }
const selectedSurface = ref([]);
const selectedDeep = ref([]);

watch(
  [queryText, outlineNature, burdenDescription, audience],
  () => {
    if (conceptStage.value !== "idle") {
      conceptStage.value = "idle";
      conceptCandidates.value = null;
      selectedSurface.value = [];
      selectedDeep.value = [];
    }
  }
);

async function extractConcepts() {
  const q = (queryText.value || "").trim();
  if (!q) {
    message.warning("请输入查询主题");
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;
  conceptLoading.value = true;
  try {
    const res = await axios.post(
      `${apiBase}/api/kg_rag/extract_concepts`,
      {
        query: q,
        outline_nature: outlineNature.value,
        burden_description: burdenDescription.value,
        audience: audience.value,
      },
      { headers }
    );
    conceptCandidates.value = res.data;
    selectedSurface.value = [];
    selectedDeep.value = [];
    conceptStage.value = "candidates_ready";
    toastSuccess("概念抽取完成，请筛选内在意义概念");
  } catch (e) {
    message.error(e.response?.data?.error || e.message || "概念抽取失败");
  } finally {
    conceptLoading.value = false;
  }
}

async function copyStep12Summary() {
  const text = step12SummaryText.value;
  if (!text || !String(text).trim()) {
    message.warning("没有可复制的内容");
    return;
  }
  try {
    await navigator.clipboard.writeText(String(text));
    toastSuccess("汇总已复制到剪贴板");
  } catch (e) {
    message.error(e?.message || "复制失败");
  }
}

function downloadTxtFile(content, filename) {
  const blob = new Blob([content ?? ""], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function getCurrentOutlineTextForDownload() {
  const tab = outlineResultTab.value;
  if (tab === "en") return englishOutline.value || "";
  if (tab === "tw") return traditionalOutline.value || "";
  return queryResult.value?.answer || "";
}

async function copyCurrentOutlineText() {
  const text = getCurrentOutlineTextForDownload();
  if (!text || !String(text).trim()) {
    message.warning("当前没有可复制的纲目文本");
    return;
  }
  try {
    await navigator.clipboard.writeText(String(text));
    toastSuccess("已复制当前纲目");
  } catch (e) {
    message.error(e?.message || "复制失败");
  }
}

async function copyOpusOutlineText() {
  const text = queryResultOpus.value?.answer;
  if (!text || !String(text).trim()) {
    message.warning("当前没有可复制的 Opus 对比纲目");
    return;
  }
  try {
    await navigator.clipboard.writeText(String(text));
    opusOutlineCopied.value = true;
    toastSuccess("已复制到剪贴板");
    setTimeout(() => {
      opusOutlineCopied.value = false;
    }, 2000);
  } catch (e) {
    message.error(e?.message || "复制失败");
  }
}

function downloadCurrentOutlineTxt() {
  const text = getCurrentOutlineTextForDownload();
  if (!text || !String(text).trim()) {
    message.warning("当前没有可下载的内容");
    return;
  }
  const tab = outlineResultTab.value;
  const suffix = tab === "en" ? "en" : tab === "tw" ? "zh-tw" : "zh";
  downloadTxtFile(text, `kg-rag-outline-${suffix}.txt`);
  toastSuccess("已开始下载");
}

async function runFullQuery() {
  const q = (queryText.value || "").trim();
  if (!q) {
    message.warning("请输入查询问题");
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;
  queryLoading.value = true;
  queryResult.value = null;
  queryResultOpus.value = null;
  compareOpusPromptUnavailable.value = false;
  opusCompareError.value = "";
  opusOutlineCopied.value = false;
  englishOutline.value = "";
  traditionalOutline.value = "";
  outlineResultTab.value = "zh";
  try {
    const qParams = buildQueryParams();
    if (conceptStage.value === "candidates_ready" && conceptCandidates.value && selectedDeep.value.length > 0) {
      qParams.preset_surface = selectedSurface.value;
      qParams.preset_deep = selectedDeep.value;
    }
    const res = await axios.post(`${apiBase}/api/kg_rag/query`, { query: q, params: qParams }, { headers });
    queryResult.value = res.data;
    if (compareOpus.value) {
      const step4Prompt = String(res.data?.steps?.step4?.prompt ?? "").trim();
      if (!step4Prompt) {
        compareOpusPromptUnavailable.value = true;
      } else {
        try {
          const opusRes = await axios.post(
            `${apiBase}/api/kg_rag/generate_step5`,
            {
              prompt: step4Prompt,
              model: "claude-opus-4-7",
              temperature: 0.3,
            },
            { headers }
          );
          queryResultOpus.value = opusRes.data;
        } catch (e2) {
          opusCompareError.value = e2.response?.data?.error || e2.message || "Opus 对比生成失败";
        }
      }
    }
    const ans = res.data?.answer;
    if (ans && (includeEnglish.value || includeTraditional.value)) {
      translating.value = true;
      const reqs = [];
      if (includeEnglish.value) {
        reqs.push(
          axios.post(
            `${apiBase}/api/ai_search/translate_outline`,
            {
              chinese_outline: ans,
              outline_topic: (queryText.value || "").trim() || undefined,
            },
            { headers }
          )
        );
      }
      if (includeTraditional.value) {
        reqs.push(
          axios.post(`${apiBase}/api/ai_search/outline_to_traditional`, { content: ans }, { headers })
        );
      }
      try {
        const settled = await Promise.allSettled(reqs);
        let i = 0;
        if (includeEnglish.value) {
          const s = settled[i++];
          if (s.status === "fulfilled") {
            const d = s.value.data || {};
            englishOutline.value = d.answer_en || "";
            if (d.error && !englishOutline.value) {
              message.warning(`英文纲目：${d.error}`);
            }
          } else {
            message.error(
              s.reason?.response?.data?.detail ||
                s.reason?.message ||
                "英文纲目翻译请求失败"
            );
          }
        }
        if (includeTraditional.value) {
          const s = settled[i++];
          if (s.status === "fulfilled") {
            const d = s.value.data || {};
            traditionalOutline.value = d.answer_zh_tw || "";
            if (d.error && !traditionalOutline.value) {
              message.warning(`繁体纲目：${d.error}`);
            }
          } else {
            message.error(
              s.reason?.response?.data?.detail ||
                s.reason?.message ||
                "繁体转换请求失败"
            );
          }
        }
      } finally {
        translating.value = false;
      }
    }
    toastSuccess("查询完成");
  } catch (e) {
    message.error(e.response?.data?.error || e.message || "查询失败");
  } finally {
    queryLoading.value = false;
  }
}

function chunkPreview(text, maxLen = 200) {
  if (!text || typeof text !== "string") return "";
  return text.length <= maxLen ? text : text.slice(0, maxLen) + "…";
}

/** 展示后端估算的 USD 费用（6 位小数内 trim 尾随 0） */
function formatUsd(n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const s = Number(n).toFixed(6).replace(/\.?0+$/, "");
  return s || "0";
}

function formatSec(n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const s = (Number(n) / 1000).toFixed(2);
  return s || "0";
}

function opusCompareTotalCostUsd() {
  const main = Number(queryResult.value?.llm_usage?.totals?.cost_usd);
  const opus = Number(queryResultOpus.value?.cost_usd);
  const hasMain = !Number.isNaN(main);
  const hasOpus = !Number.isNaN(opus);
  if (!hasMain && !hasOpus) return null;
  return (hasMain ? main : 0) + (hasOpus ? opus : 0);
}

function opusCompareTotalElapsedMs() {
  const main = Number(queryResult.value?.llm_usage?.total_elapsed_ms);
  const opus = Number(queryResultOpus.value?.elapsed_ms);
  const hasMain = !Number.isNaN(main);
  const hasOpus = !Number.isNaN(opus);
  if (!hasMain && !hasOpus) return null;
  return (hasMain ? main : 0) + (hasOpus ? opus : 0);
}

function formatStep2Path(p) {
  const from = p?.from || "";
  const relation = p?.relation || "";
  const to = p?.to || "";
  const via = p?.via || "";
  const hops = p?.hops;
  const hopsText = hops != null ? `（${hops}跳）` : "";
  if (via && Number(hops) === 2) {
    const relParts = String(relation).split("→").map((s) => s.trim()).filter(Boolean);
    const viaName = String(via).trim();
    if (relParts.length === 2 && viaName) {
      return `${from} ──${relParts[0]}──► ${viaName} ──${relParts[1]}──► ${to}${hopsText}`;
    }
  }
  if (via && Number(hops) === 3) {
    const relParts = String(relation).split("→").map((s) => s.trim()).filter(Boolean);
    const viaParts = String(via).split("→").map((s) => s.trim()).filter(Boolean);
    if (relParts.length === 3 && viaParts.length === 2) {
      return `${from} ──${relParts[0]}──► ${viaParts[0]} ──${relParts[1]}──► ${viaParts[1]} ──${relParts[2]}──► ${to}${hopsText}`;
    }
  }
  return `${from} ──${relation}──► ${to}${hopsText}`;
}

/** 与 pack_llm_usage_response 中 calls[].step 及 step_elapsed_ms 键一致 */
const STEP_ELAPSED_ORDER = ["firewall", "step1", "step2", "query_rewrite", "step5"];
const STEP_ELAPSED_LABELS = {
  firewall: "防火墙匹配",
  step1: "Step1",
  step2: "Step2",
  query_rewrite: "Query 改写",
  step5: "Step5",
};
function stepElapsedLabel(key) {
  return STEP_ELAPSED_LABELS[key] || key;
}
function orderedStepElapsedEntries(stepElapsedMs) {
  if (!stepElapsedMs || typeof stepElapsedMs !== "object") return [];
  return STEP_ELAPSED_ORDER.filter((k) => stepElapsedMs[k] != null).map((k) => ({
    key: k,
    label: stepElapsedLabel(k),
    ms: stepElapsedMs[k],
  }));
}

// ---------- Tab 2：图谱浏览器 ----------
const graphMode = ref("explore"); // explore | path | stats
const exploreConcept = ref("");
const exploreHops = ref(1);
const pathConceptA = ref("");
const pathConceptB = ref("");
const pathMaxHops = ref(3);
const graphLoading = ref(false);
const exploreResult = ref(null);
const pathResult = ref(null);
const statsResult = ref(null);

/** Tab2 邻居表列：关系列用 rel_from ──type──► rel_to 展示 */
const neighborTableColumns = [
  { title: "邻居", dataIndex: "neighbor", key: "neighbor" },
  { title: "关系", key: "edge" },
];

function formatNeighborEdge(record) {
  if (record.relations && record.relations.length) {
    return record.relations.join(" ／ ");
  }
  return record.relation_type || "相关";
}

async function runExplore() {
  const c = (exploreConcept.value || "").trim();
  if (!c) {
    message.warning("请输入概念名称");
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;
  graphLoading.value = true;
  exploreResult.value = null;
  try {
    const res = await axios.get(`${apiBase}/api/kg_rag/graph/explore`, {
      headers,
      params: { concept: c, hops: exploreHops.value },
    });
    exploreResult.value = res.data;
  } catch (e) {
    message.error(e.response?.data?.error || e.message || "邻居查询失败");
  } finally {
    graphLoading.value = false;
  }
}

async function runPath() {
  const a = (pathConceptA.value || "").trim();
  const b = (pathConceptB.value || "").trim();
  if (!a || !b) {
    message.warning("请输入起点和终点概念");
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;
  graphLoading.value = true;
  pathResult.value = null;
  try {
    const res = await axios.get(`${apiBase}/api/kg_rag/graph/path`, {
      headers,
      params: { concept_a: a, concept_b: b, max_hops: pathMaxHops.value },
    });
    pathResult.value = res.data;
  } catch (e) {
    message.error(e.response?.data?.error || e.message || "路径查询失败");
  } finally {
    graphLoading.value = false;
  }
}

async function runStats() {
  const headers = getAuthHeaders();
  if (!headers) return;
  graphLoading.value = true;
  statsResult.value = null;
  try {
    const res = await axios.get(`${apiBase}/api/kg_rag/graph/stats`, { headers });
    statsResult.value = res.data;
  } catch (e) {
    message.error(e.response?.data?.error || e.message || "图谱统计失败");
  } finally {
    graphLoading.value = false;
  }
}

function pathSegmentDisplay(pathItem) {
  const nodes = pathItem.path_nodes || [];
  const rels = pathItem.relations || [];
  const parts = [];
  for (let i = 0; i < nodes.length - 1; i++) {
    const rel = rels[i];
    const relType = (rel && typeof rel === "object") ? (rel.type || "相关") : (rel || "相关");
    const forward = (rel && typeof rel === "object") ? rel.forward !== false : true;
    if (forward) {
      parts.push(nodes[i]);
      parts.push(` ──${relType}──► `);
    } else {
      parts.push(nodes[i]);
      parts.push(` ◄──${relType}── `);
    }
  }
  if (nodes.length) parts.push(nodes[nodes.length - 1]);
  return parts.join("");
}

function chunkPreview150(text) {
  if (!text || typeof text !== "string") return "";
  return text.length <= 150 ? text : text.slice(0, 150) + "…";
}

// ---------- Tab 3：Prompt 预览 ----------
const promptPreviewQuery = ref("");
const promptPreviewLoading = ref(false);
const promptPreviewResult = ref(null);

// ---------- Tab 4：Step1~2 测试 ----------
const step12Query = ref("");
const step12Mode = ref("step1_only"); // step1_only | step1_step2
const step12SelectedModels = ref([]);
const step12Loading = ref(false);
/** 并行结果：{ model, label, ok, data?, error? }[] */
const step12Results = ref(null);
const step12Phase = ref("idle"); // idle | step1_done
const step12ConceptSelections = reactive({});
const hasAnyStep12DeepSelected = computed(() =>
  Object.values(step12ConceptSelections).some(sel => sel && sel.deep && sel.deep.length > 0)
);

/** 最下方汇总窗口：按固定标题输出题目、Step1；Step1+2 时再输出 Step2 */
const step12SummaryText = computed(() => {
  const rows = step12Results.value;
  if (!rows || !rows.length) return "";
  const lines = [];
  const joinList = (arr) => ((arr && arr.length ? arr : []).join("、") || "（无）");
  const q = (step12Query.value || "").trim();
  lines.push(`题目：${q || "（空）"}`);
  lines.push("");

  lines.push("Step1：概念抽取");
  lines.push("");
  for (const item of rows) {
    lines.push(item.label);
    const step1Cost = item.data?.steps?.step1?.llm_usage?.cost_usd;
    const step1Ms = item.data?.steps?.step1?.elapsed_ms;
    lines.push(`Step1 价格：$${formatUsd(step1Cost)} USD`);
    lines.push(`Step1 耗时：${formatSec(step1Ms)} s`);
    if (!item.ok) {
      lines.push("字面意义候选：");
      lines.push(`（请求失败）${item.error || ""}`);
      lines.push("内在意义、经历、实行候选：");
      lines.push("（请求失败）");
    } else {
      const s1 = item.data?.steps?.step1;
      const rs = s1?.reasoning != null ? String(s1.reasoning).trim() : "";
      lines.push("推理说明：");
      lines.push(rs || "（无）");
      lines.push("字面意义候选：");
      lines.push(joinList(s1?.surface));
      lines.push("内在意义、经历、实行候选：");
      lines.push(joinList(s1?.deep));
      if (s1?.error) {
        lines.push("Step1 异常：");
        lines.push(s1.error);
      }
    }
    lines.push("");
  }

  if (step12Mode.value !== "step1_only") {
    lines.push("Step2：概念骨架");
    lines.push("");
    for (const item of rows) {
      lines.push(item.label);
      const step2Cost = item.data?.steps?.step2?.llm_usage?.cost_usd;
      const step2Ms = item.data?.steps?.step2?.elapsed_ms;
      lines.push(`Step2 价格（单次骨架 LLM）：$${formatUsd(step2Cost)} USD`);
      lines.push(`Step2 耗时（图谱查询+骨架 LLM 总墙钟）：${formatSec(step2Ms)} s`);
      if (!item.ok) {
        lines.push("路径：");
        lines.push("（—）");
        lines.push("骨架：");
        lines.push("（—）");
        lines.push("扩展节点（deep）：");
        lines.push("（—）");
      } else {
        const s2 = item.data?.steps?.step2;
        if (s2?.skipped && s2?.reason === "stop_after_step1") {
          lines.push("路径：");
          lines.push("（未执行，仅 Step1）");
          lines.push("骨架：");
          lines.push("（未执行）");
          lines.push("扩展节点（deep）：");
          lines.push("（未执行）");
        } else if (s2?.skipped) {
          lines.push("路径：");
          lines.push("（未执行骨架）");
          lines.push("骨架：");
          lines.push("（未执行）");
          lines.push("扩展节点（deep）：");
          lines.push("（未执行）");
        } else {
          const paths = s2?.paths?.length
            ? s2.paths
                .map((p) => formatStep2Path(p))
                .join("\n")
            : "（无）";
          lines.push("路径：");
          lines.push(paths);
          const sk = s2?.skeleton?.length
            ? s2.skeleton.map((t, i) => {
                const step = typeof t === "object" ? t.step || t : t;
                const pe = typeof t === "object" && t.path_evidence ? `\n   ↳ ${t.path_evidence}` : "";
                const sa = typeof t === "object" && t.scripture_anchor ? `\n   📖 ${t.scripture_anchor}` : "";
                return `${i + 1}. ${step}${pe}${sa}`;
              }).join("\n")
            : "（无）";
          lines.push("骨架：");
          lines.push(sk);
          lines.push("扩展节点（deep）：");
          lines.push(joinList(s2?.expanded_nodes));
        }
      }
      lines.push("");
    }
  }
  return lines.join("\n").replace(/\n+$/, "");
});

const step12ModeOptions = [
  { label: "仅 Step1（概念抽取）", value: "step1_only" },
  { label: "Step1 + Step2（含概念骨架）", value: "step1_step2" },
];

async function runStep12Test() {
  const q = (step12Query.value || "").trim();
  if (!q) {
    message.warning("请输入查询问题");
    return;
  }
  const selected = new Set((step12SelectedModels.value || []).filter(Boolean));
  const models = step12BenchmarkModels.map((m) => m.value).filter((id) => selected.has(id));
  if (!models.length) {
    message.warning("请至少勾选一个模型");
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;
  const mode = step12Mode.value;
  step12Loading.value = true;
  step12Results.value = null;
  step12Phase.value = "idle";
  for (const key of Object.keys(step12ConceptSelections)) {
    delete step12ConceptSelections[key];
  }
  const baseParams = {
    stop_after_step1: true,
    skip_generation: true,
  };
  try {
    const settled = await Promise.allSettled(
      models.map((modelId) =>
        axios.post(
          `${apiBase}/api/kg_rag/query`,
          { query: q, params: { ...buildQueryParams(), ...baseParams, step1_model: modelId, llm_model: modelId } },
          { headers }
        )
      )
    );
    step12Results.value = models.map((modelId, i) => {
      const opt = step12BenchmarkModels.find((o) => o.value === modelId);
      const label = opt ? opt.label : modelId;
      const s = settled[i];
      if (s.status === "fulfilled") {
        return { model: modelId, label, ok: true, data: s.value.data };
      }
      const err = s.reason;
      const errMsg = err?.response?.data?.error || err?.message || "请求失败";
      return { model: modelId, label, ok: false, error: errMsg };
    });
    for (const item of step12Results.value) {
      if (item.ok && item.data?.steps?.step1) {
        step12ConceptSelections[item.model] = { surface: [], deep: [] };
      }
    }
    const okN = step12Results.value.filter((r) => r.ok).length;
    if (okN === models.length) {
      toastSuccess(`已完成 ${okN} 路 Step1`);
    } else {
      message.warning(`部分失败：${okN} / ${models.length} 路成功`);
    }
    if (mode === "step1_step2") {
      step12Phase.value = "step1_done";
    }
  } catch (e) {
    message.error(e?.message || "执行失败");
  } finally {
    step12Loading.value = false;
  }
}

async function runStep12ContinueStep2() {
  const headers = getAuthHeaders();
  if (!headers) return;
  const modelsToRun = (step12Results.value || []).filter(item => {
    if (!item.ok) return false;
    const sel = step12ConceptSelections[item.model];
    return sel && sel.deep.length > 0;
  });
  if (!modelsToRun.length) {
    message.warning("请至少为一个模型勾选内在意义概念");
    return;
  }
  step12Loading.value = true;
  try {
    const settled = await Promise.allSettled(
      modelsToRun.map(item => {
        const sel = step12ConceptSelections[item.model];
        return axios.post(
          `${apiBase}/api/kg_rag/query`,
          {
            query: step12Query.value.trim(),
            params: {
              ...buildQueryParams(),
              stop_after_step2: true,
              skip_generation: true,
              step1_model: item.model,
              llm_model: item.model,
              preset_surface: sel.surface,
              preset_deep: sel.deep,
            },
          },
          { headers }
        );
      })
    );
    modelsToRun.forEach((item, i) => {
      const s = settled[i];
      const resultItem = step12Results.value.find(r => r.model === item.model);
      if (!resultItem) return;
      if (s.status === "fulfilled") {
        const newData = s.value.data;
        resultItem.data.steps.step2 = newData.steps?.step2;
        resultItem.data.stopped_after = newData.stopped_after;
        if (newData.llm_usage) {
          const existingCalls = resultItem.data.llm_usage?.calls || [];
          const newCalls = (newData.llm_usage?.calls || []).filter(c => c.step !== "step1");
          resultItem.data.llm_usage = {
            ...resultItem.data.llm_usage,
            calls: [...existingCalls, ...newCalls],
          };
        }
      } else {
        const err = s.reason;
        const errMsg = err?.response?.data?.error || err?.message || "Step2 请求失败";
        if (resultItem.data) {
          resultItem.data.steps = resultItem.data.steps || {};
          resultItem.data.steps.step2 = { skipped: true, reason: errMsg };
        }
      }
    });
    const okN = modelsToRun.filter((_, i) => settled[i].status === "fulfilled").length;
    toastSuccess(`Step2 完成：${okN} / ${modelsToRun.length} 路成功`);
  } catch (e) {
    message.error(e?.message || "Step2 执行失败");
  } finally {
    step12Loading.value = false;
    step12Phase.value = "idle";
  }
}

async function runPromptPreview() {
  const q = (promptPreviewQuery.value || "").trim();
  if (!q) {
    message.warning("请输入查询");
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;
  promptPreviewLoading.value = true;
  promptPreviewResult.value = null;
  try {
    const res = await axios.post(
      `${apiBase}/api/kg_rag/prompt_preview`,
      { query: q, params: buildQueryParams() },
      { headers }
    );
    promptPreviewResult.value = res.data;
    toastSuccess("Prompt 已生成");
  } catch (e) {
    message.error(e.response?.data?.error || e.message || "生成失败");
  } finally {
    promptPreviewLoading.value = false;
  }
}

// ---------- Tab 5：防火墙测试 ----------
const firewallQuery = ref("");
const firewallLoading = ref(false);
const firewallResult = ref(null);

async function runFirewallTest() {
  const q = (firewallQuery.value || "").trim();
  if (!q) {
    message.warning("请输入纲目主题");
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;
  firewallLoading.value = true;
  firewallResult.value = null;
  try {
    const res = await axios.post(
      `${apiBase}/api/kg_rag/test_firewall`,
      { query: q },
      { headers }
    );
    firewallResult.value = res.data;
    toastSuccess("防火墙测试完成");
  } catch (e) {
    message.error(e.response?.data?.error || e.message || "防火墙测试失败");
  } finally {
    firewallLoading.value = false;
  }
}

// ---------- 生命周期 ----------
onMounted(() => {
  fetchHealth();
});
</script>

<template>
  <div class="kg-rag-header">
    <div class="header-left" @click="() => (window.location.hash = '/tools')">
      <ArrowLeftOutlined class="header-back" />
    </div>
    <div class="header-title">KG-RAG 测试工作台</div>
    <div class="header-health">
      <template v-if="healthLoading"><span class="health-text">检查中…</span></template>
      <template v-else-if="health">
        <span class="health-item"><span class="health-dot" :class="{ ok: health.elasticsearch?.available }" title="Elasticsearch" /> ES</span>
        <span class="health-item"><span class="health-dot" :class="{ ok: health.neo4j?.available }" title="Neo4j" /> Neo4j</span>
        <a-button type="link" size="small" class="health-refresh" @click="fetchHealth">刷新</a-button>
      </template>
      <template v-else><span class="health-text">—</span></template>
    </div>
  </div>
  <div class="kg-rag-page">
    <a-tabs v-model:activeKey="activeTab" class="main-tabs">
      <!-- Tab 1：全流程查询 -->
      <a-tab-pane key="query" tab="全流程查询">
        <a-card class="tab-card">
          <a-row :gutter="24">
            <a-col :xs="24" :md="10" :lg="9">
              <div class="query-section">
                <a-textarea
                  v-model:value="queryText"
                  placeholder="输入查询问题..."
                  :rows="4"
                  class="query-input"
                />
                <a-collapse class="param-collapse outline-collapse" :default-active-key="['outline']">
                  <a-collapse-panel key="outline" header="纲目制作选项">
                    <a-row :gutter="[12, 12]">
                      <a-col :span="24">
                        <div class="param-item">
                          <span class="param-label">面对对象</span>
                          <a-input
                            v-model:value="audience"
                            placeholder="例如：一般性、初信者、大专学生..."
                            allow-clear
                            size="small"
                            class="param-control"
                          />
                        </div>
                      </a-col>
                      <a-col :span="24">
                        <div class="param-item param-item-stack">
                          <span class="param-label">负担说明</span>
                          <a-textarea
                            v-model:value="burdenDescription"
                            placeholder="约50字概括纲目摘要，说明纲目负担"
                            :rows="3"
                            allow-clear
                            class="param-control"
                          />
                        </div>
                      </a-col>
                      <a-col :span="24">
                        <div class="param-item param-item-stack">
                          <span class="param-label">纲目性质</span>
                          <a-radio-group v-model:value="outlineNature" button-style="solid" size="small" class="param-control">
                            <a-radio-button value="一般性">一般性</a-radio-button>
                            <a-radio-button value="高真理浓度">高真理浓度</a-radio-button>
                            <a-radio-button value="高生命浓度">高生命浓度</a-radio-button>
                            <a-radio-button value="重实行应用">重实行应用</a-radio-button>
                          </a-radio-group>
                        </div>
                      </a-col>
                      <a-col :span="24">
                        <div class="param-item param-item-stack">
                          <span class="param-label">模式</span>
                          <a-radio-group v-model:value="depth" button-style="solid" size="small" class="param-control">
                            <a-radio-button value="general">普通</a-radio-button>
                            <a-radio-button value="deep">深度</a-radio-button>
                          </a-radio-group>
                        </div>
                      </a-col>
                      <a-col :span="24">
                        <div class="param-item param-checkboxes outline-translate-checks">
                          <a-checkbox v-model:checked="includeEnglish">同时生成英文纲目</a-checkbox>
                          <a-checkbox v-model:checked="includeTraditional">同时生成繁体纲目</a-checkbox>
                          <a-checkbox v-model:checked="compareOpus">并发 Opus 4.7 对比</a-checkbox>
                        </div>
                      </a-col>
                    </a-row>
                  </a-collapse-panel>
                </a-collapse>
                <a-collapse class="param-collapse" :default-active-key="['params']">
                  <a-collapse-panel key="params" header="检索与 LLM 参数">
                    <a-row :gutter="[12, 12]">
                      <a-col :span="12"><div class="param-item"><span class="param-label">BM25 Top-K</span><a-input-number v-model:value="params.bm25_top_k" :min="10" :max="100" size="small" class="param-control" /></div></a-col>
                      <a-col :span="12"><div class="param-item"><span class="param-label">Dense Top-K（0=自动）</span><a-input-number v-model:value="params.dense_top_k" :min="0" :max="100" size="small" class="param-control" /></div></a-col>
                      <a-col :span="12"><div class="param-item"><span class="param-label">Num Candidates</span><a-input-number v-model:value="params.num_candidates" :min="50" :max="300" size="small" class="param-control" /></div></a-col>
                      <a-col :span="12"><div class="param-item"><span class="param-label">RRF K</span><a-input-number v-model:value="params.rrf_k" :min="20" :max="100" size="small" class="param-control" /></div></a-col>
                      <a-col :span="12"><div class="param-item"><span class="param-label">BM25 权重</span><a-input-number v-model:value="params.bm25_weight" :min="0.1" :max="3" :step="0.1" size="small" class="param-control" /></div></a-col>
                      <a-col :span="12"><div class="param-item"><span class="param-label">Dense 权重</span><a-input-number v-model:value="params.dense_weight" :min="0.1" :max="3" :step="0.1" size="small" class="param-control" /></div></a-col>
                      <a-col :span="12"><div class="param-item"><span class="param-label">Rerank Top-N</span><a-input-number v-model:value="params.rerank_top_n" :min="5" :max="50" size="small" class="param-control" /></div></a-col>
                      <a-col :span="12"><div class="param-item"><span class="param-label">路3 Top-K</span><a-input-number v-model:value="params.skeleton_route_top_k" :min="1" :max="80" size="small" class="param-control" /></div></a-col>
                      <a-col :span="12"><div class="param-item"><span class="param-label">路3 每节点保留</span><a-input-number v-model:value="params.skeleton_route_max_per_node" :min="1" :max="30" size="small" class="param-control" /></div></a-col>
                      <a-col :span="12"><div class="param-item"><span class="param-label">Temperature</span><a-input-number v-model:value="params.temperature" :min="0" :max="1" :step="0.1" size="small" class="param-control" /></div></a-col>
                      <a-col :span="24">
                        <div class="param-item param-item-stack">
                          <span class="param-label">Claude 模型</span>
                          <a-select
                            v-model:value="params.llm_model"
                            :options="claudeModelOptions"
                            size="small"
                            class="param-control param-llm-select"
                            :dropdown-match-select-width="false"
                          />
                          <p class="param-explain">
                            全流程：Step1 默认 Opus 4.7；Query 改写固定 Opus 4.6；Step5 纲目生成默认 Sonnet 4.6（可通过请求参数 step5_model 覆盖）；测试台勾选「并发 Opus 4.7 对比」时，主流程完成后会用同一 Step4 prompt 再调 Opus 4.7 仅生成对比纲目。下方所选模型仅用于 Step2（单次骨架 LLM）。仅测 Step1 或 Step1+2 请用 Tab「Step1~2 测试」。
                            与路1 / 路2 / 路3 的 Elasticsearch 检索参数无关。
                          </p>
                          <p class="param-explain param-explain-secondary">
                            Temperature 主要作用于 Step5；前面各步温度由后端固定为 0。
                          </p>
                        </div>
                      </a-col>
                      <a-col :span="24"><div class="param-item param-checkboxes"><a-checkbox v-model:checked="params.skip_query_rewrite">跳过 Query Rewrite</a-checkbox><a-checkbox v-model:checked="params.skip_skeleton_route">跳过路3，并跳过 Step1～2（图谱概念与骨架）</a-checkbox><a-checkbox v-model:checked="params.skip_generation">跳过生成 / 仅检索</a-checkbox><a-checkbox v-model:checked="params.skip_cache">跳过缓存（强制重跑）</a-checkbox></div></a-col>
                    </a-row>
                  </a-collapse-panel>
                </a-collapse>
                <!-- 两阶段概念抽取面板 -->
                <div v-if="conceptStage === 'candidates_ready' && conceptCandidates" class="concept-candidates-panel">
                  <div class="concept-section">
                    <span class="concept-label">字面意义（surface）</span>
                    <a-checkbox-group v-model:value="selectedSurface" class="concept-checkbox-group">
                      <a-checkbox v-for="s in conceptCandidates.surface" :key="s" :value="s">{{ s }}</a-checkbox>
                    </a-checkbox-group>
                    <span v-if="!conceptCandidates.surface?.length" class="concept-empty">（无）</span>
                  </div>
                  <div class="concept-section">
                    <span class="concept-label">内在意义候选（deep）</span>
                    <a-checkbox-group v-model:value="selectedDeep" class="concept-checkbox-group">
                      <a-checkbox v-for="d in conceptCandidates.deep_candidates" :key="d" :value="d">{{ d }}</a-checkbox>
                    </a-checkbox-group>
                  </div>
                  <div v-if="conceptCandidates.reasoning" class="concept-section">
                    <span class="concept-label">reasoning</span>
                    <div class="concept-reasoning">{{ conceptCandidates.reasoning }}</div>
                  </div>
                </div>
                <div class="query-btn-row">
                  <a-button :loading="conceptLoading" @click="extractConcepts">抽取概念</a-button>
                  <a-button
                    type="primary"
                    :loading="queryLoading"
                    class="query-btn"
                    @click="runFullQuery"
                    :disabled="conceptStage === 'candidates_ready' && selectedDeep.length === 0"
                  >
                    {{ conceptStage === 'candidates_ready' ? '生成纲目' : '开始查询' }}
                  </a-button>
                  <span v-if="conceptStage === 'candidates_ready' && selectedDeep.length === 0" class="concept-warn">请至少选择一个内在意义概念</span>
                </div>
              </div>
            </a-col>
            <a-col :xs="24" :md="14" :lg="15">
              <div v-if="!queryResult" class="result-placeholder">执行查询后，结果将在此分步展示。</div>
              <template v-else>
                <div v-if="queryResult.cached" class="params-used-banner" style="color:#52c41a;font-weight:600">
                  ✓ 命中缓存（cache_key: {{ queryResult.cache_key || '—' }}）
                </div>
                <div v-if="queryResult.firewall?.matched" class="firewall-banner">
                  <span class="firewall-banner-label">防火墙命中：</span>{{ queryResult.firewall.matched }}
                  <span v-if="queryResult.firewall.note" class="firewall-banner-note">
                    · 精粹：{{ queryResult.firewall.note }}
                  </span>
                </div>
                <div
                  v-if="queryResult.params_used || queryResult.steps?.weight"
                  class="params-used-banner"
                >
                  <template v-if="queryResult.params_used">
                    面对对象：{{ queryResult.params_used.audience || "—" }}
                    · 纲目性质：{{ queryResult.params_used.outline_nature ?? "—" }}
                    · 模式：{{ queryResult.params_used.depth === "deep" ? "深度" : "普通" }}
                    <span v-if="(queryResult.params_used.burden_description || '').trim()">
                      · 负担说明：已填写
                    </span>
                    <span v-else> · 负担说明：— </span>
                  </template>
                  <template v-if="queryResult.steps?.weight">
                    <span v-if="queryResult.params_used"> | </span>
                    加权命中（BM25/Dense/路3）：
                    {{ queryResult.steps.weight.bm25_weighted ?? "—" }} /
                    {{ queryResult.steps.weight.dense_weighted ?? "—" }} /
                    {{ queryResult.steps.weight.route3_weighted ?? "—" }}
                  </template>
                </div>
                <div v-if="queryResult.llm_usage" class="llm-usage-banner">
                  <div class="llm-usage-line">
                    LLM 合计 · 输入 <strong>{{ queryResult.llm_usage.totals?.input_tokens ?? "—" }}</strong>
                    · 输出 <strong>{{ queryResult.llm_usage.totals?.output_tokens ?? "—" }}</strong> tokens
                    · 估算约 <strong>${{ formatUsd(queryResult.llm_usage.totals?.cost_usd) }}</strong> USD
                  </div>
                  <div
                    v-if="
                      queryResult.llm_usage.total_elapsed_ms != null ||
                      (queryResult.llm_usage.step_elapsed_ms &&
                        Object.keys(queryResult.llm_usage.step_elapsed_ms).length)
                    "
                    class="llm-usage-timing"
                  >
                    <div v-if="queryResult.llm_usage.total_elapsed_ms != null" class="llm-usage-line llm-usage-timing-total">
                      总耗时 <strong>{{ formatSec(queryResult.llm_usage.total_elapsed_ms) }}</strong> s（自请求开始至返回，含检索等非 LLM 阶段）
                    </div>
                    <div
                      v-if="orderedStepElapsedEntries(queryResult.llm_usage.step_elapsed_ms).length"
                      class="llm-usage-line llm-usage-timing-steps"
                    >
                      分步 LLM 耗时：
                      <template
                        v-for="(row, i) in orderedStepElapsedEntries(queryResult.llm_usage.step_elapsed_ms)"
                        :key="row.key"
                      >
                        <span v-if="i > 0"> · </span>
                        <span class="llm-usage-step-chip">{{ row.label }} <strong>{{ formatSec(row.ms) }}</strong> s</span>
                      </template>
                    </div>
                  </div>
                  <a-collapse v-if="(queryResult.llm_usage.calls || []).length" ghost size="small" class="llm-usage-collapse">
                    <a-collapse-panel key="usage" header="分步明细与计价说明">
                      <ul class="llm-usage-calls">
                        <li v-for="(c, idx) in queryResult.llm_usage.calls" :key="idx">
                          <span class="call-step">{{ c.step }}</span>
                          · {{ c.model }}（计价 {{ c.billing_model }}）
                          · in {{ c.input_tokens }} / out {{ c.output_tokens }}
                          · ≈${{ formatUsd(c.cost_usd) }}
                          <span
                            v-if="queryResult.llm_usage.step_elapsed_ms && queryResult.llm_usage.step_elapsed_ms[c.step] != null"
                            class="call-elapsed"
                          >
                            · 耗时 {{ formatSec(queryResult.llm_usage.step_elapsed_ms[c.step]) }} s</span>
                          <div class="rate-desc">{{ c.rate_description }}</div>
                        </li>
                      </ul>
                      <p class="usage-disclaimer">{{ queryResult.llm_usage.disclaimer }}</p>
                      <ul class="usage-refs">
                        <li v-for="(ref, i) in (queryResult.llm_usage.pricing_references || [])" :key="i">{{ ref }}</li>
                      </ul>
                    </a-collapse-panel>
                  </a-collapse>
                </div>
                <a-steps direction="vertical" :current="7" class="result-steps">
                  <a-step title="Step 1 概念抽取（从图谱词表匹配）">
                    <template #description>
                      <a-card size="small" class="step-card">
                      <div v-if="queryResult.steps?.step1">
                        <div class="step1-layer">
                          <span class="step1-layer-label">字面意义候选：</span>
                          <a-tag v-for="c in (queryResult.steps.step1.surface || [])" :key="`surface-${c}`">{{ c }}</a-tag>
                        </div>
                        <div class="step1-layer">
                          <span class="step1-layer-label">内在意义、经历、实行候选：</span>
                          <a-tag color="blue" v-for="c in (queryResult.steps.step1.deep || [])" :key="`deep-${c}`">{{ c }}</a-tag>
                        </div>
                        <div class="step1-layer">
                          <span class="step1-layer-label">合并送 Step2：</span>
                          <a-tag color="green" v-for="c in (queryResult.steps.step1.concepts || [])" :key="`merged-${c}`">{{ c }}</a-tag>
                        </div>
                        <a-collapse v-if="queryResult.steps.step1.raw_response">
                          <a-collapse-panel key="raw" header="原始 LLM 响应">
                            <pre class="raw-pre">{{ queryResult.steps.step1.raw_response }}</pre>
                          </a-collapse-panel>
                        </a-collapse>
                      </div>
                    </a-card>
                  </template>
                </a-step>
                <a-step title="Step 2 概念骨架（路径 + 单次 LLM）">
                  <template #description>
                    <a-card size="small" class="step-card">
                      <div v-if="queryResult.steps?.step2 && !queryResult.steps.step2.skipped" class="step2-meta">
                        <span>总耗时 {{ formatSec(queryResult.steps.step2.elapsed_ms) }} s</span>
                        <span v-if="queryResult.steps.step2.llm_usage"> · 估算 ${{ formatUsd(queryResult.steps.step2.llm_usage.cost_usd) }} USD</span>
                        <span v-else> · 无 LLM 费用</span>
                      </div>
                      <div
                        v-else-if="queryResult.steps?.step2?.skipped && queryResult.steps.step2.reason === 'stop_after_step1'"
                        class="step2-meta step2-meta-muted"
                      >Step2 未执行（在 Step1 后停止）</div>
                      <div v-else-if="queryResult.steps?.step2?.skipped" class="step2-meta step2-meta-muted">Step2 已跳过（无概念或跳过骨架路由）</div>
                      <div v-if="queryResult.steps?.step2?.skeleton && queryResult.steps.step2.skeleton.length" class="step2-block">
                        <div class="step2-title">纲目逻辑骨架</div>
                        <ol class="step2-ol">
                          <li v-for="(s, i) in queryResult.steps.step2.skeleton" :key="`s-${i}`">
                            {{ typeof s === 'object' ? s.step : s }}
                            <div v-if="s && typeof s === 'object' && s.path_evidence" class="skeleton-path-evidence">↳ {{ s.path_evidence }}</div>
                            <div v-if="s && typeof s === 'object' && s.scripture_anchor" class="skeleton-path-evidence">📖 {{ s.scripture_anchor }}</div>
                          </li>
                        </ol>
                      </div>
                      <div v-if="(queryResult.steps?.step2?.expanded_nodes || []).length" class="step2-block">
                        <div class="step2-title">扩展节点（deep）</div>
                        <a-tag v-for="e in queryResult.steps.step2.expanded_nodes" :key="e">{{ e }}</a-tag>
                      </div>
                      <a-collapse v-if="(queryResult.steps?.step2?.paths || []).length" class="step2-inner-collapse" :bordered="false">
                        <a-collapse-panel key="paths" :header="`概念间路径 · ${queryResult.steps.step2.paths.length} 条`">
                          <div v-for="(p, i) in (queryResult.steps.step2.paths || [])" :key="`p-${i}`" class="step2-line">
                            {{ formatStep2Path(p) }}
                          </div>
                        </a-collapse-panel>
                      </a-collapse>
                      <template
                        v-if="queryResult.steps?.step2 && !queryResult.steps.step2.skipped && !(queryResult.steps.step2.paths || []).length && !(queryResult.steps.step2.skeleton || []).length"
                      >
                        无 1～3 跳路径或未调用骨架 LLM（路径为空时不请求 LLM）
                      </template>
                    </a-card>
                  </template>
                </a-step>
                <a-step title="Query 改写">
                  <template #description>
                    <a-card size="small" class="step-card">
                      <template v-if="(queryResult.steps?.step3?.rewritten_queries || []).length">
                        <div
                          v-for="(rq, ri) in queryResult.steps.step3.rewritten_queries"
                          :key="ri"
                          class="rewritten-query-text"
                        >{{ ri + 1 }}. {{ rq }}</div>
                      </template>
                      <div v-else class="rewritten-query-text">—（跳过改写）</div>
                    </a-card>
                  </template>
                </a-step>
                <a-step title="Step 3 检索结果">
                  <template #description>
                    <a-card size="small" class="step-card">
                      <a-tabs size="small">
                        <a-tab-pane key="main" tab="主检索结果">
                          <div
                            v-for="(r, i) in (queryResult.steps?.step3?.main_results || [])"
                            :key="r.chunk_id || i"
                            class="chunk-row"
                          >
                            <div class="chunk-meta">
                              #{{ i + 1 }} · {{ r.chunk_id }} · score {{ (r.score != null ? r.score : r._score).toFixed(3) }}
                              <a-tag
                                v-if="r.source_routes && r.source_routes.length"
                                :color="r.source_routes.length === 2 ? 'orange' : r.source_routes[0] === 'bm25' ? 'blue' : 'green'"
                                class="source-route-tag"
                              >{{ r.source_routes.length === 2 ? 'BM25+Dense' : r.source_routes[0] === 'bm25' ? 'BM25' : 'Dense' }}</a-tag>
                            </div>
                            <div class="chunk-text">{{ chunkPreview(r.text) }}</div>
                            <div v-if="r.book_title || r.message_title" class="chunk-meta">
                              {{ r.book_title }} / {{ r.message_title }} / {{ r.section_title }}
                            </div>
                          </div>
                        </a-tab-pane>
                        <a-tab-pane key="bm25" tab="BM25 原始">
                          <div
                            v-for="(r, i) in (queryResult.steps?.step3?.bm25_results || [])"
                            :key="r.chunk_id || i"
                            class="chunk-row"
                          >
                            <div class="chunk-meta">#{{ i + 1 }} · {{ r.chunk_id }} · {{ (r._score || r.score || 0).toFixed(3) }}</div>
                            <div class="chunk-text">{{ chunkPreview(r.text) }}</div>
                            <div v-if="r.source_zh" class="chunk-source">{{ r.source_zh }}</div>
                          </div>
                        </a-tab-pane>
                        <a-tab-pane key="dense" tab="Dense 原始">
                          <div
                            v-for="(r, i) in (queryResult.steps?.step3?.dense_results || [])"
                            :key="r.chunk_id || i"
                            class="chunk-row"
                          >
                            <div class="chunk-meta">#{{ i + 1 }} · {{ r.chunk_id }} · {{ (r._score || r.score || 0).toFixed(3) }}</div>
                            <div class="chunk-text">{{ chunkPreview(r.text) }}</div>
                            <div v-if="r.source_zh" class="chunk-source">{{ r.source_zh }}</div>
                            <div v-if="r.rewritten_query" class="chunk-rewritten-query">改写Query: "{{ r.rewritten_query }}"</div>
                          </div>
                        </a-tab-pane>
                        <a-tab-pane
                          v-if="(queryResult.steps?.step3?.expanded_results || []).length"
                          key="route3"
                          tab="路3 扩展结果"
                        >
                          <div
                            v-for="(r, i) in (queryResult.steps.step3.expanded_results || [])"
                            :key="r.chunk_id || i"
                            class="chunk-row"
                          >
                            <div class="chunk-meta">
                              #{{ i + 1 }} · expanded_from: {{ r.expanded_from }} · {{ r.chunk_id }} ·
                              {{ (r.score != null ? r.score : r._score || 0).toFixed(3) }}
                            </div>
                            <div class="chunk-text">{{ chunkPreview(r.text) }}</div>
                            <div v-if="r.source_zh" class="chunk-source">{{ r.source_zh }}</div>
                          </div>
                        </a-tab-pane>
                      </a-tabs>
                    </a-card>
                  </template>
                </a-step>
                <a-step title="Step 4 Prompt">
                  <template #description>
                    <a-card size="small" class="step-card">
                      <div class="prompt-meta">
                        {{ queryResult.steps?.step4?.prompt_type || "—" }} · 约
                        {{ queryResult.steps?.step4?.token_estimate ?? "—" }} tokens
                      </div>
                      <a-textarea
                        :value="queryResult.steps?.step4?.prompt"
                        readonly
                        :rows="12"
                        class="prompt-textarea"
                      />
                    </a-card>
                  </template>
                </a-step>
                <a-step title="Step 5 生成结果">
                  <template #description>
                    <a-card size="small" class="step-card">
                      <template v-if="queryResult.steps?.step5?.skipped"> 已跳过 </template>
                      <template v-else-if="queryResult.answer">
                        <div class="answer-outline-wrap">
                          <div class="answer-outline-toolbar">
                            <a-space wrap>
                              <a-button type="default" size="small" @click="copyCurrentOutlineText">
                                <template #icon><CopyOutlined /></template>
                                复制当前纲目
                              </a-button>
                              <a-button type="default" size="small" @click="downloadCurrentOutlineTxt">
                                <template #icon><DownloadOutlined /></template>
                                下载 TXT
                              </a-button>
                            </a-space>
                            <span v-if="translating" class="answer-translating">
                              <a-spin size="small" />
                              翻译 / 繁体处理中…
                            </span>
                          </div>
                          <a-tabs v-model:activeKey="outlineResultTab" size="small" class="answer-outline-tabs">
                            <a-tab-pane key="zh" tab="中文纲目">
                              <pre class="answer-pre answer-pre-outline">{{ queryResult.answer }}</pre>
                            </a-tab-pane>
                            <a-tab-pane v-if="includeEnglish" key="en" tab="英文纲目">
                              <div v-if="translating && !englishOutline" class="answer-translating-block">
                                <a-spin tip="翻译中…" />
                              </div>
                              <pre v-else class="answer-pre answer-pre-outline">{{ englishOutline || "（暂无）" }}</pre>
                            </a-tab-pane>
                            <a-tab-pane v-if="includeTraditional" key="tw" tab="繁体纲目">
                              <div v-if="translating && !traditionalOutline" class="answer-translating-block">
                                <a-spin tip="转换中…" />
                              </div>
                              <pre v-else class="answer-pre answer-pre-outline">{{ traditionalOutline || "（暂无）" }}</pre>
                            </a-tab-pane>
                          </a-tabs>
                        </div>
                        <div v-if="compareOpus" class="opus-compare-section">
                          <div class="opus-compare-title">Opus 4.7 对比纲目</div>
                          <p v-if="compareOpusPromptUnavailable" class="opus-compare-unavailable">
                            Step 4 prompt 不可用，无法生成对比纲目
                          </p>
                          <p v-else-if="opusCompareError" class="opus-compare-unavailable">{{ opusCompareError }}</p>
                          <template v-else-if="queryResultOpus">
                            <div class="answer-outline-toolbar opus-compare-toolbar">
                              <span class="opus-compare-meta">
                                总价格：<strong>{{
                                  opusCompareTotalCostUsd() != null
                                    ? "$" + formatUsd(opusCompareTotalCostUsd())
                                    : "—"
                                }}</strong>
                                　总耗时：<strong>{{
                                  opusCompareTotalElapsedMs() != null
                                    ? formatSec(opusCompareTotalElapsedMs()) + "s"
                                    : "—"
                                }}</strong>
                              </span>
                              <a-button type="default" size="small" @click="copyOpusOutlineText">
                                <template #icon>
                                  <CheckOutlined v-if="opusOutlineCopied" style="color: #52c41a" />
                                  <CopyOutlined v-else />
                                </template>
                                {{ opusOutlineCopied ? "已复制" : "复制对比纲目" }}
                              </a-button>
                            </div>
                            <pre class="answer-pre answer-pre-outline">{{ queryResultOpus.answer }}</pre>
                          </template>
                        </div>
                      </template>
                      <template v-else-if="queryResult.steps?.step5?.error">
                        {{ queryResult.steps.step5.error }}
                      </template>
                      <template v-else> — </template>
                    </a-card>
                  </template>
                  </a-step>
                </a-steps>
              </template>
            </a-col>
          </a-row>
        </a-card>
      </a-tab-pane>

      <!-- Tab 2：图谱浏览器 -->
      <a-tab-pane key="graph" tab="图谱浏览器">
        <a-card class="tab-card">
          <div class="graph-ops">
            <a-radio-group v-model:value="graphMode" button-style="solid" size="middle">
              <a-radio-button value="explore">邻居查询</a-radio-button>
              <a-radio-button value="path">路径查询</a-radio-button>
              <a-radio-button value="stats">图谱统计</a-radio-button>
            </a-radio-group>
          </div>
          <a-divider style="margin: 12px 0" />
          <div v-if="graphMode === 'explore'" class="graph-form">
            <a-input v-model:value="exploreConcept" placeholder="概念名称" class="graph-input" />
            <a-select v-model:value="exploreHops" :options="[1,2,3,4,5].map(h=>({label: h, value: h}))" class="graph-select" />
            <a-button type="primary" :loading="graphLoading" @click="runExplore">查询</a-button>
          </div>
          <div v-if="graphMode === 'path'" class="graph-form">
            <a-input v-model:value="pathConceptA" placeholder="起点概念" class="graph-input graph-input-sm" />
            <a-input v-model:value="pathConceptB" placeholder="终点概念" class="graph-input graph-input-sm" />
            <a-select v-model:value="pathMaxHops" :options="[1,2,3,4,5].map(h=>({label: h, value: h}))" class="graph-select" />
            <a-button type="primary" :loading="graphLoading" @click="runPath">查询</a-button>
          </div>
          <div v-if="graphMode === 'stats'" class="graph-form">
            <a-button type="primary" :loading="graphLoading" @click="runStats">查看统计</a-button>
          </div>
          <div class="graph-result">
          <template v-if="graphMode === 'explore' && exploreResult">
            <a-table
              :columns="neighborTableColumns"
              :data-source="exploreResult.neighbors || []"
              :pagination="false"
              :row-key="(_, index) => `nb-${index}`"
              size="small"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'edge'">
                  <span class="neighbor-edge-text">{{ formatNeighborEdge(record) }}</span>
                </template>
              </template>
            </a-table>
          </template>
          <template v-else-if="graphMode === 'path' && pathResult">
            <p>路径数：{{ pathResult.path_count ?? 0 }}</p>
            <p v-if="pathResult.shortest_path">最短路径：{{ pathSegmentDisplay(pathResult.shortest_path) }}</p>
            <div v-if="(pathResult.paths || []).length">
              <p>所有路径：</p>
              <ul>
                <li v-for="(p, i) in pathResult.paths" :key="i">{{ pathSegmentDisplay(p) }}</li>
              </ul>
            </div>
          </template>
          <template v-else-if="graphMode === 'stats' && statsResult">
            <a-descriptions bordered size="small" :column="1">
              <a-descriptions-item label="Neo4j 可用">{{ statsResult.available ? "是" : "否" }}</a-descriptions-item>
              <a-descriptions-item label="概念数">{{ statsResult.concept_count ?? 0 }}</a-descriptions-item>
              <a-descriptions-item label="关系数">{{ statsResult.relation_count ?? 0 }}</a-descriptions-item>
              <a-descriptions-item label="关系类型分布">
                <span v-for="(cnt, type) in (statsResult.relation_types || {})" :key="type">
                  {{ type }}: {{ cnt }} &nbsp;
                </span>
              </a-descriptions-item>
            </a-descriptions>
          </template>
          </div>
        </a-card>
      </a-tab-pane>

      <!-- Tab 3：Prompt 预览 -->
      <a-tab-pane key="prompt_preview" tab="Prompt 预览">
        <a-card class="tab-card">
          <div class="prompt-preview-input">
            <a-textarea v-model:value="promptPreviewQuery" placeholder="输入查询问题..." :rows="3" class="query-input" />
            <p class="hint">
              纲目制作选项、检索与 LLM 参数均与「全流程查询」左侧共用。仅测 Step1 或 Step1+2 请用 Tab「Step1～2 测试」；本预览为完整 Step1～4。
            </p>
            <a-button type="primary" :loading="promptPreviewLoading" @click="runPromptPreview">生成 Prompt</a-button>
          </div>
          <div v-if="promptPreviewResult" class="prompt-preview-result">
            <div
              v-if="promptPreviewResult.params_used || promptPreviewResult.steps?.weight"
              class="params-used-banner params-used-banner-compact"
            >
              <template v-if="promptPreviewResult.params_used">
                面对对象：{{ promptPreviewResult.params_used.audience || "—" }}
                · 纲目性质：{{ promptPreviewResult.params_used.outline_nature ?? "—" }}
                · 模式：{{ promptPreviewResult.params_used.depth === "deep" ? "深度" : "普通" }}
                <span v-if="(promptPreviewResult.params_used.burden_description || '').trim()">
                  · 负担说明：已填写
                </span>
                <span v-else> · 负担说明：— </span>
              </template>
              <template v-if="promptPreviewResult.steps?.weight">
                <span v-if="promptPreviewResult.params_used"> | </span>
                加权命中（BM25/Dense/路3）：
                {{ promptPreviewResult.steps.weight.bm25_weighted ?? "—" }} /
                {{ promptPreviewResult.steps.weight.dense_weighted ?? "—" }} /
                {{ promptPreviewResult.steps.weight.route3_weighted ?? "—" }}
              </template>
            </div>
            <div v-if="promptPreviewResult.llm_usage" class="llm-usage-banner llm-usage-banner-compact prompt-preview-usage">
              <div class="llm-usage-line">
                LLM（至 Step4，无 Step5）· 输入 <strong>{{ promptPreviewResult.llm_usage.totals?.input_tokens ?? "—" }}</strong>
                · 输出 <strong>{{ promptPreviewResult.llm_usage.totals?.output_tokens ?? "—" }}</strong> tokens
                · ≈<strong>${{ formatUsd(promptPreviewResult.llm_usage.totals?.cost_usd) }}</strong>
              </div>
            </div>
            <a-alert
              v-if="promptPreviewResult.stopped_after === 'step1'"
              type="warning"
              show-icon
              class="stopped-after-alert"
              message="响应在 Step1 结束"
              description="未执行 Step2～4，无最终 Prompt；折叠区可查看 Step1 概念。（通常来自 API 直接传参，而非本 Tab 默认行为）"
            />
            <a-alert
              v-else-if="promptPreviewResult.stopped_after === 'step2'"
              type="warning"
              show-icon
              class="stopped-after-alert"
              message="响应在 Step2 结束"
              description="未执行 Step3～4，无最终 Prompt；折叠区可查看 Step1～2。（通常来自 API 直接传参）"
            />
            <div v-if="!promptPreviewResult.steps?.step4?.skipped" class="prompt-meta-row">
              <a-tag :color="promptPreviewResult.steps?.step4?.prompt_type === 'skeleton' ? 'blue' : 'default'">
                {{ promptPreviewResult.steps?.step4?.prompt_type === "skeleton" ? "骨架式 Prompt" : "平铺式 Prompt" }}
              </a-tag>
              <span class="prompt-token-hint">约 {{ promptPreviewResult.steps?.step4?.token_estimate ?? "—" }} tokens</span>
            </div>
            <a-textarea
              v-if="!promptPreviewResult.steps?.step4?.skipped"
              :value="promptPreviewResult.steps?.step4?.prompt"
              readonly
              :rows="16"
              class="prompt-full-textarea"
            />
            <a-collapse class="steps-summary" :bordered="false">
            <a-collapse-panel key="step1" header="Step 1 概念抽取（从图谱词表匹配）">
              <div class="step1-layer">
                <span class="step1-layer-label">字面意义候选：</span>
                <a-tag v-for="c in (promptPreviewResult.steps?.step1?.surface || [])" :key="`psurface-${c}`">{{ c }}</a-tag>
              </div>
              <div class="step1-layer">
                <span class="step1-layer-label">内在意义、经历、实行候选：</span>
                <a-tag color="blue" v-for="c in (promptPreviewResult.steps?.step1?.deep || [])" :key="`pdeep-${c}`">{{ c }}</a-tag>
              </div>
              <div class="step1-layer">
                <span class="step1-layer-label">合并送 Step2：</span>
                <a-tag color="green" v-for="c in (promptPreviewResult.steps?.step1?.concepts || [])" :key="`pmerged-${c}`">{{ c }}</a-tag>
              </div>
            </a-collapse-panel>
            <a-collapse-panel key="step2" header="Step 2 概念骨架（路径 + 单次 LLM）">
              <div v-if="promptPreviewResult.steps?.step2 && !promptPreviewResult.steps.step2.skipped" class="step2-meta">
                <span>总耗时 {{ formatSec(promptPreviewResult.steps.step2.elapsed_ms) }} s</span>
                <span v-if="promptPreviewResult.steps.step2.llm_usage"> · 估算 ${{ formatUsd(promptPreviewResult.steps.step2.llm_usage.cost_usd) }} USD</span>
                <span v-else> · 无 LLM 费用</span>
              </div>
              <div v-if="promptPreviewResult.steps?.step2?.skeleton && promptPreviewResult.steps.step2.skeleton.length" class="step2-block">
                <div class="step2-title">纲目逻辑骨架</div>
                <ol class="step2-ol">
                  <li v-for="(s, i) in promptPreviewResult.steps.step2.skeleton" :key="`ps-${i}`">
                    {{ typeof s === 'object' ? s.step : s }}
                    <div v-if="s && typeof s === 'object' && s.path_evidence" class="skeleton-path-evidence">↳ {{ s.path_evidence }}</div>
                    <div v-if="s && typeof s === 'object' && s.scripture_anchor" class="skeleton-path-evidence">📖 {{ s.scripture_anchor }}</div>
                  </li>
                </ol>
              </div>
              <div v-if="(promptPreviewResult.steps?.step2?.expanded_nodes || []).length" class="step2-block">
                <div class="step2-title">扩展节点（deep）</div>
                <a-tag v-for="e in promptPreviewResult.steps.step2.expanded_nodes" :key="`pe-${e}`">{{ e }}</a-tag>
              </div>
              <a-collapse v-if="(promptPreviewResult.steps?.step2?.paths || []).length" class="step2-inner-collapse" :bordered="false">
                <a-collapse-panel key="paths" :header="`概念间路径 · ${promptPreviewResult.steps.step2.paths.length} 条`">
                  <div v-for="(p, i) in (promptPreviewResult.steps.step2.paths || [])" :key="`pp-${i}`" class="step2-line">
                    {{ formatStep2Path(p) }}
                  </div>
                </a-collapse-panel>
              </a-collapse>
              <template
                v-if="promptPreviewResult.steps?.step2 && !promptPreviewResult.steps.step2.skipped && !(promptPreviewResult.steps.step2.paths || []).length && !(promptPreviewResult.steps.step2.skeleton || []).length"
              >
                无 1～3 跳路径或未调用骨架 LLM
              </template>
            </a-collapse-panel>
            <a-collapse-panel key="step3" header="Step 3 检索统计">
              主检索 {{ (promptPreviewResult.steps?.step3?.main_results || []).length }} 条，
              扩展 {{ (promptPreviewResult.steps?.step3?.expanded_results || []).length }} 条
            </a-collapse-panel>
            </a-collapse>
          </div>
        </a-card>
      </a-tab-pane>

      <!-- Tab 4：Step1~2 测试 -->
      <a-tab-pane key="step12" tab="Step1~2 测试">
        <a-card class="tab-card">
          <a-row :gutter="[16, 16]">
            <a-col :span="24">
              <div class="query-section step12-section">
                <a-textarea
                  v-model:value="step12Query"
                  placeholder="输入查询问题…"
                  :rows="4"
                  class="query-input"
                />
                <div class="step12-options">
                  <span class="step12-options-label">范围</span>
                  <a-radio-group v-model:value="step12Mode" class="step12-radio-group">
                    <a-radio v-for="opt in step12ModeOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</a-radio>
                  </a-radio-group>
                </div>
                <p class="hint step12-gpt-hint">
                  勾选多个模型后点击执行，将<strong>同时</strong>发起多路请求（浏览器并行）；下方按<strong>自上而下</strong>展示，顺序固定为 Sonnet 4.6 → Opus 4.6 → Opus 4.7 → GPT-5.4 → GPT-5.4 Thinking。最底部为 Step1/Step2 纯文本汇总。每路 Step1/Step2 使用同一模型；<strong>GPT-5.4 Thinking</strong> 为 <code>gpt-5.4</code> + 更高 <code>reasoning.effort</code>（非 Pro）。GPT 需 <code>OPENAI_API_KEY</code>。
                </p>
                <div class="param-item param-item-stack step12-model-row">
                  <span class="param-label">并行模型（多选）</span>
                  <a-checkbox-group v-model:value="step12SelectedModels" class="step12-checkbox-group">
                    <a-row :gutter="[8, 8]">
                      <a-col v-for="m in step12BenchmarkModels" :key="m.value" :span="12">
                        <a-checkbox :value="m.value">{{ m.label }}</a-checkbox>
                      </a-col>
                    </a-row>
                  </a-checkbox-group>
                </div>
                <a-button type="primary" :loading="step12Loading" class="query-btn" @click="runStep12Test">并行执行</a-button>
              </div>
            </a-col>
            <a-col :span="24">
              <div v-if="!step12Results" class="result-placeholder">勾选模型并执行后，自上而下展示各路 Step1 / Step2；页末为汇总文本。</div>
              <div v-else class="step12-results-stack">
                <a-card
                  v-for="item in step12Results"
                  :key="item.model"
                  size="small"
                  class="step12-model-card step12-model-card-stack"
                  :title="item.label"
                >
                    <template v-if="!item.ok">
                      <a-alert type="error" :message="item.error" show-icon />
                    </template>
                    <template v-else>
                      <div class="step12-model-id">{{ item.model }}</div>
                      <div v-if="item.data?.llm_usage" class="llm-usage-banner llm-usage-banner-compact">
                        <div class="llm-usage-line">
                          LLM · 输入 <strong>{{ item.data.llm_usage.totals?.input_tokens ?? "—" }}</strong>
                          · 输出 <strong>{{ item.data.llm_usage.totals?.output_tokens ?? "—" }}</strong> tokens
                          · ≈<strong>${{ formatUsd(item.data.llm_usage.totals?.cost_usd) }}</strong>
                        </div>
                        <a-collapse v-if="(item.data.llm_usage.calls || []).length" ghost size="small" class="llm-usage-collapse">
                          <a-collapse-panel key="usage" header="明细">
                            <ul class="llm-usage-calls">
                              <li v-for="(c, idx) in item.data.llm_usage.calls" :key="idx">
                                {{ c.step }} · {{ c.model }}（{{ c.billing_model }}）· in {{ c.input_tokens }} / out {{ c.output_tokens }}
                                · ≈${{ formatUsd(c.cost_usd) }}
                                <div class="rate-desc">{{ c.rate_description }}</div>
                              </li>
                            </ul>
                            <p class="usage-disclaimer">{{ item.data.llm_usage.disclaimer }}</p>
                            <ul class="usage-refs">
                              <li v-for="(ref, i) in (item.data.llm_usage.pricing_references || [])" :key="i">{{ ref }}</li>
                            </ul>
                          </a-collapse-panel>
                        </a-collapse>
                      </div>
                      <a-alert
                        v-if="item.data?.stopped_after === 'step1' && step12Phase !== 'step1_done'"
                        type="info"
                        show-icon
                        class="stopped-after-alert step12-mini-alert"
                        message="仅 Step1"
                      />
                      <a-alert
                        v-else-if="item.data?.stopped_after === 'step2'"
                        type="info"
                        show-icon
                        class="stopped-after-alert step12-mini-alert"
                        message="Step1+2 完成"
                      />
                      <a-steps direction="vertical" :current="2" class="result-steps step12-steps step12-steps-in-card">
                        <a-step title="Step 1">
                          <template #description>
                            <a-card size="small" class="step-card step12-nested-card">
                              <div v-if="item.data?.steps?.step1">
                                <div class="step1-layer">
                                  <span class="step1-layer-label">字面意义候选：</span>
                                  <template v-if="step12ConceptSelections[item.model]">
                                    <a-checkbox-group v-model:value="step12ConceptSelections[item.model].surface" class="concept-checkbox-group">
                                      <a-checkbox v-for="c in (item.data.steps.step1.surface || [])" :key="`${item.model}-s-${c}`" :value="c">{{ c }}</a-checkbox>
                                    </a-checkbox-group>
                                  </template>
                                  <template v-else>
                                    <a-tag v-for="c in (item.data.steps.step1.surface || [])" :key="`${item.model}-s-${c}`">{{ c }}</a-tag>
                                  </template>
                                </div>
                                <div class="step1-layer">
                                  <span class="step1-layer-label">内在意义、经历、实行候选：</span>
                                  <template v-if="step12ConceptSelections[item.model]">
                                    <a-checkbox-group v-model:value="step12ConceptSelections[item.model].deep" class="concept-checkbox-group">
                                      <a-checkbox v-for="c in (item.data.steps.step1.deep || [])" :key="`${item.model}-d-${c}`" :value="c">{{ c }}</a-checkbox>
                                    </a-checkbox-group>
                                  </template>
                                  <template v-else>
                                    <a-tag color="blue" v-for="c in (item.data.steps.step1.deep || [])" :key="`${item.model}-d-${c}`">{{ c }}</a-tag>
                                  </template>
                                </div>
                                <div v-if="step12ConceptSelections[item.model] && step12ConceptSelections[item.model].deep.length === 0 && step12Phase === 'step1_done'" class="concept-warn" style="margin: 4px 0;">
                                  请勾选至少一个内在意义概念
                                </div>
                                <a-collapse v-if="item.data.steps.step1.raw_response">
                                  <a-collapse-panel key="raw" header="原始响应">
                                    <pre class="raw-pre">{{ item.data.steps.step1.raw_response }}</pre>
                                  </a-collapse-panel>
                                </a-collapse>
                                <p v-if="item.data.steps.step1.error" class="step12-error">{{ item.data.steps.step1.error }}</p>
                              </div>
                            </a-card>
                          </template>
                        </a-step>
                        <a-step title="Step 2（路径 + 骨架）">
                          <template #description>
                            <a-card size="small" class="step-card step12-nested-card">
                              <div v-if="item.data?.steps?.step2 && !item.data.steps.step2.skipped" class="step2-meta step12-step2-meta">
                                <span>总耗时 {{ formatSec(item.data.steps.step2.elapsed_ms) }} s</span>
                                <span v-if="item.data.steps.step2.llm_usage"> · ${{ formatUsd(item.data.steps.step2.llm_usage.cost_usd) }}</span>
                                <span v-else> · 无 LLM 费用</span>
                              </div>
                              <template v-if="item.data?.steps?.step2?.skipped && item.data.steps.step2.reason === 'stop_after_step1'">
                                <span class="step-skipped-hint">未执行（仅 Step1）</span>
                              </template>
                              <template v-else-if="item.data?.steps?.step2?.skipped">
                                <span class="step-skipped-hint">未执行骨架</span>
                              </template>
                              <template v-else>
                                <div v-if="item.data?.steps?.step2?.skeleton?.length" class="step2-block">
                                  <div class="step2-title">骨架</div>
                                  <ol class="step2-ol">
                                    <li v-for="(s, i) in item.data.steps.step2.skeleton" :key="`${item.model}-sk-${i}`">
                                      {{ typeof s === 'object' ? s.step : s }}
                                      <div v-if="s && typeof s === 'object' && s.path_evidence" class="skeleton-path-evidence">↳ {{ s.path_evidence }}</div>
                                      <div v-if="s && typeof s === 'object' && s.scripture_anchor" class="skeleton-path-evidence">📖 {{ s.scripture_anchor }}</div>
                                    </li>
                                  </ol>
                                </div>
                                <div v-if="(item.data?.steps?.step2?.expanded_nodes || []).length" class="step2-block">
                                  <a-tag v-for="e in item.data.steps.step2.expanded_nodes" :key="`${item.model}-ex-${e}`">{{ e }}</a-tag>
                                </div>
                                <a-collapse v-if="(item.data?.steps?.step2?.paths || []).length" class="step2-inner-collapse" :bordered="false">
                                  <a-collapse-panel key="paths" :header="`路径 · ${item.data.steps.step2.paths.length} 条`">
                                    <div v-for="(p, i) in (item.data.steps.step2.paths || [])" :key="`${item.model}-p-${i}`" class="step2-line">
                                      {{ formatStep2Path(p) }}
                                    </div>
                                  </a-collapse-panel>
                                </a-collapse>
                                <template
                                  v-if="!(item.data?.steps?.step2?.paths || []).length && !(item.data?.steps?.step2?.expanded_nodes || []).length && !(item.data?.steps?.step2?.skeleton || []).length"
                                >
                                  <span class="step-skipped-hint">无路径 / 无骨架</span>
                                </template>
                              </template>
                            </a-card>
                          </template>
                        </a-step>
                      </a-steps>
                    </template>
                </a-card>
              </div>
              <div v-if="step12Phase === 'step1_done'" class="step12-continue-wrap">
                <a-button
                  type="primary"
                  :loading="step12Loading"
                  :disabled="!hasAnyStep12DeepSelected"
                  @click="runStep12ContinueStep2"
                >
                  用所选概念继续 Step2
                </a-button>
                <span v-if="!hasAnyStep12DeepSelected" class="concept-warn" style="margin-left: 12px;">请至少为一个模型勾选内在意义概念</span>
              </div>
            </a-col>
            <a-col v-if="step12Results" :span="24">
              <div class="step12-summary-wrap">
                <div class="step12-summary-head">
                  <span class="step12-summary-title">汇总（Step1 + Step2 纯文本）</span>
                  <a-button type="default" size="small" @click="copyStep12Summary">
                    <template #icon><CopyOutlined /></template>
                    复制汇总
                  </a-button>
                </div>
                <a-textarea
                  :value="step12SummaryText"
                  readonly
                  class="step12-summary-textarea"
                  :rows="22"
                  placeholder="执行后将在此生成与上方一致的纯文本汇总"
                />
              </div>
            </a-col>
          </a-row>
        </a-card>
      </a-tab-pane>

      <!-- Tab 5：防火墙测试 -->
      <a-tab-pane key="firewall" tab="防火墙测试">
        <a-card class="tab-card">
          <div class="firewall-section">
            <a-input
              v-model:value="firewallQuery"
              placeholder="输入纲目主题"
              class="firewall-input"
              @pressEnter="runFirewallTest"
            />
            <a-button type="primary" :loading="firewallLoading" class="firewall-btn" @click="runFirewallTest">测试</a-button>
          </div>
          <div v-if="firewallResult" class="firewall-result">
            <template v-if="firewallResult.matched">
              <div class="firewall-hit">
                <span class="firewall-label">命中：</span>
                <span class="firewall-value">{{ firewallResult.matched }}</span>
              </div>
              <div class="firewall-hit">
                <span class="firewall-label">精粹：</span>
                <span class="firewall-value">{{ firewallResult.note || "（无）" }}</span>
              </div>
            </template>
            <template v-else>
              <div class="firewall-miss">未命中</div>
            </template>
          </div>
        </a-card>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<style scoped lang="less">
/* 页面标题区：与 ToolsHeader 风格一致，标题 + 健康指示器一行 */
.kg-rag-header {
  padding: 10px 20px;
  display: flex;
  align-items: center;
  font-size: large;
  font-weight: bold;
  color: #55bbff;
  background-color: #001529;
  margin-bottom: 16px;
  gap: 12px;
  .header-left {
    cursor: pointer;
    display: flex;
    align-items: center;
    &:hover .header-back {
      color: #1677ff;
      transform: scale(1.1);
      transition: 0.2s;
    }
  }
  .header-title {
    flex: 1;
    text-align: center;
  }
  .header-health {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 13px;
    font-weight: normal;
    color: rgba(255, 255, 255, 0.85);
    .health-item {
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .health-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #ff4d4f;
      flex-shrink: 0;
      &.ok {
        background: #52c41a;
      }
    }
    .health-text {
      color: rgba(255, 255, 255, 0.65);
    }
    .health-refresh {
      color: #55bbff;
      padding: 0 4px;
    }
  }
}

.kg-rag-page {
  padding: 1em;
  max-width: 1400px;
  margin: 0 auto;
}

.main-tabs {
  :deep(.ant-tabs-content) {
    padding-top: 12px;
  }
}

.tab-card {
  margin-bottom: 16px;
}

/* Tab 1 全流程查询 */
.query-section {
  margin-bottom: 16px;
}
.query-input {
  margin-bottom: 16px;
}
.outline-collapse {
  margin-bottom: 16px;
  :deep(.ant-collapse-header) {
    align-items: center;
  }
}
.firewall-banner {
  font-size: 13px;
  color: #d46b08;
  font-weight: 600;
  line-height: 1.55;
  margin-bottom: 12px;
  padding: 8px 10px;
  background: #fff7e6;
  border: 1px solid #ffd591;
  border-radius: 6px;
  .firewall-banner-label {
    color: #ad4e00;
  }
  .firewall-banner-note {
    font-weight: normal;
    color: #874d00;
  }
}
.params-used-banner {
  font-size: 12px;
  color: #444;
  line-height: 1.55;
  margin-bottom: 12px;
  padding: 8px 10px;
  background: #f6f8fa;
  border-radius: 6px;
  border: 1px solid #e8e8e8;
}
.params-used-banner-compact {
  margin-bottom: 10px;
}
.param-collapse {
  margin-bottom: 16px;
  :deep(.ant-collapse-header) {
    align-items: center;
  }
}
.param-item {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 0;
  .param-label {
    min-width: 88px;
    font-size: 13px;
    color: #333;
    flex-shrink: 0;
  }
  .param-control {
    flex: 1;
    min-width: 0;
  }
  .param-select {
    width: 100%;
  }
  &.param-item-stack {
    flex-direction: column;
    align-items: stretch;
    gap: 6px;
    .param-label {
      min-width: 0;
    }
  }
  &.param-checkboxes {
    padding-top: 4px;
    .param-label {
      min-width: 0;
    }
  }
}
.param-explain {
  font-size: 12px;
  color: #666;
  line-height: 1.55;
  margin: 0;
}
.param-explain-secondary {
  color: #888;
  margin-top: -2px;
}
.param-llm-select {
  width: 100%;
  max-width: 100%;
}
.stopped-after-alert {
  margin-bottom: 12px;
}
.step-skipped-hint {
  color: #888;
  font-size: 13px;
}
.step12-section .step12-options {
  margin: 12px 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.step12-options-label {
  font-size: 13px;
  color: #666;
}
.step12-radio-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.step12-model-row {
  margin-bottom: 10px;
}
.step12-gpt-hint {
  margin: 0 0 12px;
  font-size: 13px;
  color: #595959;
  line-height: 1.55;
}
.step12-checkbox-group {
  width: 100%;
}
.step12-results-row {
  align-items: stretch;
}
.step12-results-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.step12-model-card {
  height: 100%;
  min-height: 280px;
  :deep(.ant-card-body) {
    max-height: 70vh;
    overflow-y: auto;
  }
}
.step12-model-card-stack {
  min-height: 0;
  width: 100%;
  :deep(.ant-card-body) {
    max-height: min(70vh, 520px);
    overflow-y: auto;
  }
}
.step12-summary-wrap {
  margin-top: 8px;
  padding-top: 16px;
  border-top: 1px solid #f0f0f0;
}
.step12-summary-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.step12-summary-title {
  font-weight: 600;
  font-size: 14px;
  color: #333;
}
.step12-summary-textarea {
  font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
  font-size: 13px;
  line-height: 1.5;
  resize: vertical;
}
.step12-model-id {
  font-size: 11px;
  color: #888;
  font-family: ui-monospace, monospace;
  margin-bottom: 8px;
  word-break: break-all;
}
.step12-mini-alert {
  margin-bottom: 8px;
  padding: 6px 10px;
  :deep(.ant-alert-message) {
    font-size: 12px;
  }
}
.step12-steps-in-card {
  :deep(.ant-steps-item-description) {
    padding-bottom: 8px;
  }
}
.step12-nested-card {
  margin-top: 4px;
  :deep(.ant-card-body) {
    padding: 8px;
  }
}
.step12-steps {
  margin-top: 4px;
}
.step12-error {
  color: #cf1322;
  font-size: 13px;
  margin-top: 8px;
}
.step12-continue-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 16px 0;
}

.llm-usage-timing {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
  font-size: 12px;
  color: rgba(0, 0, 0, 0.65);
  .llm-usage-timing-total {
    margin-bottom: 4px;
  }
  .llm-usage-timing-steps {
    line-height: 1.6;
  }
  .llm-usage-step-chip {
    white-space: nowrap;
  }
}
.llm-usage-calls .call-elapsed {
  color: rgba(0, 0, 0, 0.55);
}
.llm-usage-banner {
  margin-bottom: 16px;
  padding: 10px 12px;
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.55;
  color: #333;
  &.llm-usage-banner-compact {
    margin-bottom: 8px;
    padding: 8px 10px;
    font-size: 12px;
  }
  .llm-usage-line {
    margin: 0;
  }
  .llm-usage-collapse {
    margin-top: 6px;
    :deep(.ant-collapse-header) {
      padding: 4px 0 !important;
      font-size: 12px;
    }
    :deep(.ant-collapse-content-box) {
      padding: 0 0 4px !important;
    }
  }
  .llm-usage-calls {
    list-style: none;
    padding: 0;
    margin: 0 0 8px;
    li {
      margin-bottom: 8px;
      padding-bottom: 6px;
      border-bottom: 1px solid #f0f0f0;
      &:last-child {
        border-bottom: none;
        margin-bottom: 0;
        padding-bottom: 0;
      }
    }
  }
  .call-step {
    font-weight: 600;
    color: #389e0d;
  }
  .rate-desc {
    font-size: 12px;
    color: #666;
    margin-top: 2px;
  }
  .usage-disclaimer {
    font-size: 12px;
    color: #888;
    margin: 8px 0 4px;
  }
  .usage-refs {
    font-size: 11px;
    color: #666;
    padding-left: 1.2em;
    margin: 0;
    li {
      word-break: break-all;
    }
  }
}

.query-btn-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 8px;
}
.query-btn {
  width: 100%;
  margin-top: 0;
}
.query-btn-row .query-btn {
  flex: 1;
  width: auto;
}
.concept-warn {
  color: #fa541c;
  font-size: 12px;
  white-space: nowrap;
}
.concept-candidates-panel {
  background: #f6f9ff;
  border: 1px solid #d6e4ff;
  border-radius: 6px;
  padding: 12px 14px;
  margin-top: 8px;
  margin-bottom: 4px;
}
.concept-section {
  margin-bottom: 10px;
  &:last-child { margin-bottom: 0; }
}
.concept-label {
  font-weight: 600;
  font-size: 13px;
  color: #333;
  display: block;
  margin-bottom: 4px;
}
.concept-hint {
  font-weight: 400;
  color: #888;
  font-size: 12px;
}
.concept-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.concept-empty {
  color: #aaa;
  font-size: 12px;
}
.concept-checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
}
.concept-reasoning {
  font-size: 12px;
  color: #666;
  line-height: 1.6;
  background: #fff;
  padding: 6px 8px;
  border-radius: 4px;
  border: 1px solid #eee;
}

.result-placeholder {
  color: #999;
  padding: 32px 24px;
  text-align: center;
  background: #fafafa;
  border-radius: 8px;
}

.result-steps {
  :deep(.ant-steps-item-description) {
    padding-bottom: 20px;
  }
  :deep(.ant-steps-item) {
    .ant-steps-item-container {
      .ant-steps-item-content {
        .ant-steps-item-title {
          font-weight: 500;
        }
      }
    }
  }
}

.step-card {
  margin-top: 12px;
  margin-bottom: 4px;
  :deep(.ant-card-body) {
    padding: 12px;
  }
  .step1-layer {
    margin-bottom: 6px;
    &:last-child {
      margin-bottom: 0;
    }
  }
  .step1-layer-label {
    color: #666;
    margin-right: 6px;
    font-size: 12px;
  }
  .step2-meta {
    font-size: 12px;
    color: rgba(0, 0, 0, 0.65);
    margin-bottom: 10px;
    line-height: 1.5;
  }
  .step2-meta-split {
    margin-top: 4px;
    color: rgba(0, 0, 0, 0.45);
  }
  .step2-meta-muted {
    color: rgba(0, 0, 0, 0.45);
  }
  .step12-step2-meta {
    margin-bottom: 8px;
  }
  .step2-block {
    margin-bottom: 8px;
    &:last-child {
      margin-bottom: 0;
    }
  }
  .step2-inner-collapse {
    background: transparent;
    margin-bottom: 6px;
    :deep(.ant-collapse-header) {
      padding: 4px 0 !important;
      font-size: 12px;
      color: #666;
    }
    :deep(.ant-collapse-content-box) {
      padding: 6px 0 !important;
    }
  }
  .step2-title {
    color: #666;
    font-size: 12px;
    margin-bottom: 4px;
  }
  .step2-line {
    font-size: 12px;
    color: #333;
    margin-bottom: 2px;
  }
  .step2-ol {
    margin: 0;
    padding-left: 20px;
    li {
      font-size: 14px;
      color: #333;
      line-height: 1.7;
    }
  }
  .skeleton-path-evidence {
    font-size: 12px;
    color: #6090c0;
    margin-top: 2px;
    margin-bottom: 3px;
    line-height: 1.4;
  }
  .answer-toolbar {
    margin-bottom: 8px;
  }
  .outline-translate-checks {
    flex-wrap: wrap;
    gap: 12px;
  }
  .answer-outline-wrap {
    width: 100%;
  }
  .opus-compare-section {
    margin-top: 16px;
    padding-top: 12px;
    border-top: 1px solid #f0f0f0;
  }
  .opus-compare-title {
    font-weight: 600;
    margin-bottom: 8px;
    font-size: 14px;
  }
  .opus-compare-unavailable {
    margin: 0 0 8px;
    font-size: 13px;
    color: #8c8c8c;
  }
  .opus-compare-toolbar {
    margin-bottom: 8px;
  }
  .opus-compare-meta {
    font-size: 13px;
    color: #333;
    line-height: 1.5;
    flex: 1;
    min-width: 0;
  }
  .answer-outline-toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 8px;
  }
  .answer-translating {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: #666;
  }
  .answer-outline-tabs {
    :deep(.ant-tabs-content) {
      padding-top: 8px;
    }
  }
  .answer-translating-block {
    min-height: 120px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .raw-pre,
  .answer-pre {
    white-space: pre-wrap;
    word-break: break-all;
    font-size: 12px;
    max-height: 200px;
    overflow: auto;
    margin: 0;
    color: #333;
  }
  .answer-pre-outline {
    max-height: 420px;
  }
  .prompt-meta {
    margin-bottom: 8px;
    font-size: 13px;
    color: #666;
  }
  .prompt-textarea {
    font-family: monospace;
    font-size: 12px;
  }
  .chunk-row {
    margin-bottom: 10px;
    padding: 10px 12px;
    background: #f5f5f5;
    border-radius: 6px;
    &:last-child {
      margin-bottom: 0;
    }
    .chunk-meta {
      font-size: 12px;
      color: #8c8c8c;
      margin-bottom: 4px;
      line-height: 1.4;
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 4px;
    }
    .source-route-tag {
      font-size: 11px;
      line-height: 1.2;
      padding: 0 4px;
      margin: 0;
    }
    .chunk-text {
      font-size: 13px;
      color: #333;
      line-height: 1.5;
      margin-bottom: 2px;
    }
    .chunk-source {
      font-size: 11px;
      color: #999;
      margin-top: 2px;
      line-height: 1.4;
    }
    .chunk-rewritten-query {
      font-size: 11px;
      color: #bbb;
      margin-top: 2px;
      line-height: 1.4;
    }
  }
}

/* Tab 5 防火墙测试 */
.firewall-section {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  .firewall-input {
    flex: 1;
    max-width: 400px;
  }
}
.firewall-result {
  padding: 16px;
  background: #fafafa;
  border-radius: 8px;
  .firewall-hit {
    margin-bottom: 8px;
    font-size: 14px;
    &:last-child {
      margin-bottom: 0;
    }
  }
  .firewall-label {
    color: #666;
    font-weight: 500;
  }
  .firewall-value {
    color: #333;
  }
  .firewall-miss {
    color: #999;
    font-size: 14px;
  }
}

/* Tab 2 图谱浏览器 */
.graph-ops {
  margin-bottom: 12px;
}
.graph-form {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
  .graph-input {
    width: 200px;
  }
  .graph-input-sm {
    width: 140px;
  }
  .graph-select {
    width: 80px;
  }
}
.graph-result {
  min-height: 120px;
  padding: 16px;
  background: #fafafa;
  border-radius: 8px;
  margin-top: 16px;
  :deep(.ant-table) {
    font-size: 13px;
  }
  :deep(.ant-descriptions-item-label) {
    font-weight: 500;
    color: #333;
  }
  p, ul {
    margin-bottom: 8px;
    font-size: 13px;
    color: #333;
  }
}

/* Tab 3 Prompt 预览 */
.prompt-preview-input {
  margin-bottom: 16px;
  .hint {
    color: #666;
    font-size: 12px;
    margin: 8px 0 12px;
  }
}

.prompt-preview-result {
  margin-top: 16px;
  .prompt-preview-usage {
    margin-bottom: 12px;
  }
  .prompt-meta-row {
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }
  .prompt-token-hint {
    font-size: 13px;
    color: #666;
  }
  .prompt-full-textarea {
    font-family: monospace;
    font-size: 12px;
    margin-bottom: 16px;
    resize: none;
  }
  .steps-summary {
    :deep(.ant-collapse-item) {
      .ant-collapse-header {
        padding: 8px 0;
        font-size: 13px;
      }
      .ant-collapse-content-box {
        padding: 8px 0 12px;
      }
    }
  }
}
</style>

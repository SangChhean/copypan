<script setup>
import ToolsHeader from "@/components/toolbox/ToolsHeader.vue";
import { computed, onMounted, ref } from "vue";
import { DownloadOutlined } from "@ant-design/icons-vue";
import { toastError } from "@/components/utils/Dialog.js";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";

const stages = [
  { no: 1, short: "壹　倪柝声" },
  { no: 2, short: "贰　李 1932-1973" },
  { no: 3, short: "叁　李 1974-1984" },
  { no: 4, short: "肆　李1985-1990" },
  { no: 5, short: "伍　李1991-1997" },
];

const tab = ref("pano");
const seriesList = ref([]);
const seriesListLoaded = ref(false);
const seriesNo = ref(null);
const loadingSeries = ref(false);
const term = ref("基督");
const topK = ref(80);
const searching = ref(false);
const activeStage = ref(null);
const articles = ref([]);
const items = ref([]);
const groups = ref([]);
const nGroups = ref(0);
const expanded = ref({});
const count = ref(0);
const estimatedTokens = ref(0);
const groupingUsage = ref(null);
const segmentUsage = ref(undefined);
const plainText = ref("");
const sourceGroupLabel = ref("");
const statsVisible = ref(false);
const segmentGroupResults = ref([]);
const generating = ref(false);
const formatting = ref(false);
const error = ref("");
const dragPayload = ref(null);
const dropTargetGi = ref(null);
const ministerializeResults = ref([]);
const ministerializing = ref(false);
const ministerializeError = ref("");
const articleExpanded = ref({});
const totalCumulativeCost = ref(0);
const ministerializeUsage = ref(null);
const activeFilterStatus = ref({});
const currentMsgNo = ref(1);
const reprocessFiles = ref([]);
const reprocessParsed = ref([]);
const reprocessing = ref(false);
const reprocessError = ref("");

const indentMap = {
  bible_reading: 0,
  ot1: 0,
  ot2: 1,
  ot3: 2,
  ot4: 3,
  ot5: 4,
  ot6: 4,
  ot7: 4,
};
const indentEm = (type) => `${(indentMap[type] ?? 1) * 1.5}em`;

const hasResults = computed(() =>
  groups.value.length > 0
    ? true
    : tab.value === "pano"
      ? articles.value.length > 0
      : items.value.length > 0
);

const showSeriesEmptyHint = computed(
  () =>
    tab.value === "pano" &&
    seriesListLoaded.value &&
    !loadingSeries.value &&
    seriesList.value.length === 0
);

const countLabel = computed(() =>
  tab.value === "pano" ? `共${count.value}篇` : `共${count.value}条`
);

const busy = computed(
  () => searching.value || generating.value || formatting.value || ministerializing.value || reprocessing.value
);

function authHeaders(json = true) {
  const token = localStorage.getItem("token");
  if (!token) {
    window.location.hash = "/login";
    return null;
  }
  const h = { Authorization: `Bearer ${token}` };
  if (json) h["Content-Type"] = "application/json";
  return h;
}

function parseApiError(res, data) {
  let detail = data?.detail;
  if (Array.isArray(detail)) {
    detail = detail.map((x) => x?.msg || x?.message || JSON.stringify(x)).join("；");
  }
  return detail || data?.error || data?.message || `请求失败（${res.status}）`;
}

function clearResults() {
  articles.value = [];
  items.value = [];
  groups.value = [];
  nGroups.value = 0;
  expanded.value = {};
  count.value = 0;
  estimatedTokens.value = 0;
  groupingUsage.value = null;
  segmentUsage.value = undefined;
  plainText.value = "";
  sourceGroupLabel.value = "";
  statsVisible.value = false;
  segmentGroupResults.value = [];
  segmentUsage.value = undefined;
  activeStage.value = null;
  error.value = "";
  ministerializeResults.value = [];
  ministerializeError.value = "";
  articleExpanded.value = {};
  ministerializeUsage.value = null;
}

function onTabChange(key) {
  if (generating.value || reprocessing.value) return;
  if (tab.value === key) return;
  tab.value = key;
  if (key !== "reprocess") clearResults();
}

function toggle(key) {
  expanded.value[key] = !expanded.value[key];
}

function applySearchResult(data) {
  groups.value = data.groups || [];
  nGroups.value = data.n_groups || groups.value.length || 0;
  if (tab.value === "pano") {
    articles.value = data.articles || [];
  } else {
    items.value = data.items || [];
  }
  count.value = data.count || 0;
  estimatedTokens.value = data.estimated_tokens || 0;
  groupingUsage.value = data.grouping_usage || null;
  plainText.value = data.plain_text || "";
  sourceGroupLabel.value = data.source_group_label || "";
  statsVisible.value = true;
  expanded.value = {};
  segmentGroupResults.value = [];
  segmentUsage.value = undefined;
  const groupCost = parseFloat(data.grouping_usage?.cost_usd || 0);
  totalCumulativeCost.value =
    Math.round((totalCumulativeCost.value + groupCost) * 1000000) / 1000000;
}

function formatCost(v) {
  return Number(v || 0).toFixed(4);
}

function recordKey(rec) {
  return tab.value === "pano" ? rec.id : rec.chunk_id;
}

function onGroupsEdited() {
  segmentUsage.value = undefined;
  segmentGroupResults.value = [];
}

function onDragStart(ev, sourceGi, key) {
  if (generating.value || !key) return;
  dragPayload.value = { sourceGi, key };
  if (ev.dataTransfer) ev.dataTransfer.effectAllowed = "move";
}

function onGroupDragOver(gi) {
  if (!dragPayload.value || dragPayload.value.sourceGi === gi) return;
  dropTargetGi.value = gi;
}

function onGroupDragLeave(gi) {
  if (dropTargetGi.value === gi) dropTargetGi.value = null;
}

async function onGroupDrop(targetGi) {
  dropTargetGi.value = null;
  const payload = dragPayload.value;
  dragPayload.value = null;
  if (!payload || payload.sourceGi === targetGi) return;

  const field = tab.value === "pano" ? "articles" : "items";
  const src = groups.value[payload.sourceGi];
  const dst = groups.value[targetGi];
  if (!src || !dst) return;

  const list = [...(src[field] || [])];
  const idx = list.findIndex((r) => recordKey(r) === payload.key);
  if (idx < 0) return;

  const [rec] = list.splice(idx, 1);
  src[field] = list;
  dst[field] = [...(dst[field] || []), rec];

  try {
    await recomputeGroupsFromLocal();
    expanded.value = {};
  } catch (e) {
    error.value = "调整分组失败：" + e.message;
    toastError(error.value);
  }
}

async function recomputeGroupsFromLocal() {
  const headers = authHeaders();
  if (!headers) return;

  const url =
    tab.value === "pano"
      ? `${apiBase}/api/progress/groups/recompute/pano`
      : `${apiBase}/api/progress/groups/recompute/entry`;

  const body = {
    groups: groups.value.map((g) => ({
      title: g.title || "",
      burden: g.burden || "",
      ...(tab.value === "pano"
        ? { articles: g.articles || [] }
        : { items: g.items || [] }),
    })),
  };

  const res = await fetch(url, { method: "POST", headers, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(parseApiError(res, data));

  groups.value = data.groups || [];
  nGroups.value = data.n_groups ?? groups.value.length;
  onGroupsEdited();
}

onMounted(async () => {
  const headers = authHeaders();
  if (!headers) return;
  loadingSeries.value = true;
  try {
    const res = await fetch(`${apiBase}/api/progress/series-list`, { headers });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(parseApiError(res, data));
    seriesList.value = data.series || [];
    seriesListLoaded.value = true;
    if (seriesList.value.length) {
      seriesNo.value = seriesList.value[0].series_no;
      currentMsgNo.value = 1;
    }
  } catch (e) {
    error.value = "加载系列列表失败：" + e.message;
    toastError(error.value);
  } finally {
    loadingSeries.value = false;
  }
});

function onSeriesChange() {
  currentMsgNo.value = 1;
}

async function onStageClick(stageNo) {
  if (tab.value === "pano") {
    if (seriesNo.value == null) {
      error.value = "请先选择系列编号";
      return;
    }
  } else if (!term.value.trim()) {
    error.value = "请输入词条名称";
    return;
  }

  const headers = authHeaders();
  if (!headers) return;

  // 切换阶段时清空职事化结果
  ministerializeResults.value = [];
  ministerializeError.value = "";
  articleExpanded.value = {};
  ministerializeUsage.value = null;
  segmentGroupResults.value = [];
  segmentUsage.value = undefined;

  error.value = "";
  searching.value = true;
  activeStage.value = stageNo;

  try {
    const url =
      tab.value === "pano"
        ? `${apiBase}/api/progress/pano/search`
        : `${apiBase}/api/progress/entry/search`;
    const body =
      tab.value === "pano"
        ? { series_no: seriesNo.value, source_group_no: stageNo }
        : { term: term.value.trim(), source_group_no: stageNo, top_k: topK.value };

    const res = await fetch(url, { method: "POST", headers, body: JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(parseApiError(res, data));
    applySearchResult(data);
  } catch (e) {
    error.value = "检索失败：" + e.message;
    toastError(error.value);
  } finally {
    searching.value = false;
  }
}

async function generate() {
  if (!plainText.value || generating.value) return;
  const headers = authHeaders();
  if (!headers) return;

  generating.value = true;
  segmentGroupResults.value = [];
  segmentUsage.value = undefined;

  const base =
    tab.value === "pano"
      ? `${apiBase}/api/progress/pano/generate/segment`
      : `${apiBase}/api/progress/entry/generate/segment`;

  try {
    const body = { content: plainText.value };
    if (tab.value === "entry") body.term = term.value.trim();
    if (groups.value.length > 0) {
      body.groups = groups.value.map((g) => ({
        title: g.title || "",
        burden: g.burden || "",
        plain_text: g.plain_text || "",
        record_count: g.record_count || 0,
      }));
    }

    const res = await fetch(base, { method: "POST", headers, body: JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(parseApiError(res, data));
    segmentGroupResults.value = data.group_results || [];
    segmentUsage.value = data.segment_usage ?? data.usage ?? null;
    const segCost = parseFloat((data.segment_usage ?? data.usage)?.cost_usd || 0);
    totalCumulativeCost.value =
      Math.round((totalCumulativeCost.value + segCost) * 1000000) / 1000000;
  } catch (e) {
    error.value = "生成失败：" + e.message;
    toastError(error.value);
  } finally {
    generating.value = false;
  }
}

async function formatDownload() {
  const headers = authHeaders();
  if (!headers) return;

  formatting.value = true;
  try {
    if (segmentGroupResults.value.length > 1) {
      const res = await fetch(`${apiBase}/api/progress/format_download_batch`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          items: segmentGroupResults.value.map((g) => ({
            text: g.text || "",
            title: g.title || "",
          })),
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(parseApiError(res, data));
      }
      await saveBlobResponse(res, "分段纲目.zip");
      return;
    }

    const singleText = segmentGroupResults.value[0]?.text;
    const singleTitle = segmentGroupResults.value[0]?.title || "";

    if (!singleText) return;

    const res = await fetch(`${apiBase}/api/progress/format_download`, {
      method: "POST",
      headers,
      body: JSON.stringify({ text: singleText, title: singleTitle }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(parseApiError(res, data));
    }
    await saveBlobResponse(res, "纲目.docx");
  } catch (e) {
    error.value = e.message;
    toastError(error.value);
  } finally {
    formatting.value = false;
  }
}

async function saveBlobResponse(res, fallbackName) {
  const blob = await res.blob();
  const disp = res.headers.get("Content-Disposition") || "";
  let filename = fallbackName;
  const m = disp.match(/filename\*=UTF-8''(.+)/i);
  if (m) filename = decodeURIComponent(m[1]);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function toggleArticle(no) {
  articleExpanded.value[no] = !articleExpanded.value[no];
}

function computeFootnotes(lines) {
  const map = new Map();
  let counter = 1;
  for (const line of lines) {
    const src = (line.source_zh || "").trim();
    if (src && !map.has(src)) {
      map.set(src, counter++);
    }
    line.footnote_no = src ? (map.get(src) ?? null) : null;
  }
  const footnotes = [];
  for (const [src, no] of map.entries()) {
    footnotes.push({ no, source_zh: src });
  }
  return footnotes;
}

function onSourceZhChange(article) {
  article.footnotes = computeFootnotes(article.lines);
}

function statusColor(status) {
  return { original: "green", minor: "gold", replaced: "blue", manual: "red" }[status] || "default";
}

function statusLabel(status) {
  return { original: "原文", minor: "微调", replaced: "已替换", manual: "人工处理" }[status] || status;
}

function statusClass(status) {
  return {
    "status-original": status === "original",
    "status-minor": status === "minor",
    "status-replaced": status === "replaced",
    "status-manual": status === "manual",
  };
}

function removeLine(article, idx) {
  article.lines.splice(idx, 1);
  article.footnotes = computeFootnotes(article.lines);
}

async function rerunLine(article, idx) {
  const line = article.lines[idx];
  if (!line) return;
  const headers = authHeaders();
  if (!headers) return;
  try {
    const res = await fetch(`${apiBase}/api/kg_rag/ministerialize`, {
      method: "POST",
      headers,
      body: JSON.stringify({ lines: [line.original] }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(parseApiError(res, data));
    const r = (data.results || [])[0];
    if (r) {
      line.result = r.result || r.original;
      line.status = r.status;
      line.source_zh = r.source || "";
      line.suggestion = r.suggestion || "";
      article.footnotes = computeFootnotes(article.lines);
    }
  } catch (e) {
    toastError("重跑失败：" + e.message);
  }
}

async function ministerialize() {
  if (!segmentGroupResults.value.length || ministerializing.value) return;
  const headers = authHeaders();
  if (!headers) return;

  ministerializing.value = true;
  ministerializeError.value = "";
  ministerializeResults.value = [];
  articleExpanded.value = {};

  try {
    // 收集该阶段所有组的原始 outline 数据（仅 pano Tab 需要）
    const isPano = tab.value === "pano";
    let outlineSources = [];
    if (isPano) {
      for (const grp of groups.value) {
        for (const art of grp.articles || []) {
          for (const item of art.outline || []) {
            if (item.text) {
              outlineSources.push({
                text: item.text,
                source: item.source || "",
              });
            }
          }
        }
      }
    }

    const body = {
      group_results: segmentGroupResults.value.map((g) => ({
        title: g.title || "",
        text: g.text || "",
      })),
      series_title: isPano
        ? seriesList.value.find((s) => s.series_no === seriesNo.value)?.series_title || ""
        : term.value || "",
      stage_no: activeStage.value,
      is_pano: isPano,
      outline_sources: outlineSources,
      global_article_offset: isPano ? currentMsgNo.value + 1 : null,
    };

    const res = await fetch(`${apiBase}/api/progress/ministerialize_segment`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(parseApiError(res, data));

    const articles = data.articles || [];
    articles.forEach((art, idx) => {
      articleExpanded.value[art.article_no] = idx === 0;
    });

    ministerializeResults.value = articles;
    currentMsgNo.value += (data.articles || []).length;
    ministerializeUsage.value = data.total_ministerialize_usage || null;

    const cost = parseFloat(data.total_ministerialize_usage?.cost_usd || 0);
    totalCumulativeCost.value =
      Math.round((totalCumulativeCost.value + cost) * 1000000) / 1000000;
  } catch (e) {
    ministerializeError.value = "职事化失败：" + e.message;
    toastError(ministerializeError.value);
  } finally {
    ministerializing.value = false;
  }
}

async function downloadArticleDocx(article) {
  const headers = authHeaders();
  if (!headers) return;

  const outlineLines = (article.lines || []).map((line) => ({
    text: (line.result || line.original || "").trim(),
    footnote_no: line.footnote_no ?? null,
  }));

  const body = {
    header_lines: article.header_lines || [],
    outline_lines: outlineLines,
    footnotes: article.footnotes || [],
    article_title: article.article_title || "",
  };

  try {
    const res = await fetch(`${apiBase}/api/progress/ministerialize_download`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(parseApiError(res, data));
    }
    const STAGE_SHORT = {
      1: "倪",
      2: "李1932-1973",
      3: "李1974-1984",
      4: "李1985-1990",
      5: "李1991-1997",
    };
    const stageTag = STAGE_SHORT[activeStage.value] ? `（${STAGE_SHORT[activeStage.value]}）` : "";
    const rawTitle = (article.article_title || "").replace(/^第[一二三四五六七八九十百千万亿\d]+篇[\u3000\s]+/, "");
    const filename = `msg. ${article.article_no} ${stageTag}${rawTitle}.docx`;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    toastError("下载失败：" + e.message);
  }
}

function articleStatusCounts(article) {
  const counts = { original: 0, minor: 0, replaced: 0, manual: 0 };
  for (const line of article.lines || []) {
    if (counts[line.status] !== undefined) counts[line.status]++;
  }
  return counts;
}

function filteredLines(article) {
  const filter = activeFilterStatus.value[article.article_no] || null;
  if (!filter) return article.lines || [];
  return (article.lines || []).filter((l) => l.status === filter);
}

function setFilter(articleNo, status) {
  const current = activeFilterStatus.value[articleNo] || null;
  if (current === status) {
    activeFilterStatus.value[articleNo] = null;
  } else {
    activeFilterStatus.value[articleNo] = status;
  }
}

function parseFilename(filename) {
  const normalized = filename.replace(/^ｍ/, "m");
  const STAGE_MAP = {
    倪: 1,
    "李1932-1973": 2,
    "李1974-1984": 3,
    "李1985-1990": 4,
    "李1991-1997": 5,
  };
  const m = normalized.match(/^msg\.\s*(\d+)\s*（([^）]+)）(.+)\.docx$/i);
  if (!m) return null;
  const articleNo = parseInt(m[1], 10);
  const stageTag = m[2].trim();
  const title = m[3].trim();
  const stageNo = STAGE_MAP[stageTag] || null;
  return { articleNo, stageTag, stageNo, title };
}

async function handleReprocessUpload(event) {
  const files = Array.from(event.target.files || []);
  if (!files.length) return;
  reprocessing.value = true;
  reprocessError.value = "";
  reprocessParsed.value = [];
  const headers = authHeaders();
  if (!headers) {
    reprocessing.value = false;
    return;
  }
  const uploadHeaders = Object.fromEntries(
    Object.entries(headers).filter(([k]) => k.toLowerCase() !== "content-type")
  );
  const results = [];
  for (const file of files) {
    const meta = parseFilename(file.name);
    if (!meta) {
      reprocessError.value = `文件名格式不符：${file.name}`;
      continue;
    }
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(`${apiBase}/api/progress/parse_docx_text`, {
        method: "POST",
        headers: uploadHeaders,
        body: form,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "解析失败");
      results.push({
        filename: file.name,
        articleNo: meta.articleNo,
        stageNo: meta.stageNo,
        stageTag: meta.stageTag,
        title: meta.title,
        text: data.text,
        parsed: true,
        ministerializing: false,
      });
    } catch (e) {
      reprocessError.value = `${file.name} 解析失败：${e.message}`;
    }
  }
  results.sort((a, b) => a.articleNo - b.articleNo);
  reprocessParsed.value = results;
  reprocessing.value = false;
  event.target.value = "";
}

async function reprocessMinisterialize(item) {
  item.ministerializing = true;
  try {
    const headers = authHeaders();
    if (!headers) return;
    const esResp = await fetch(`${apiBase}/api/progress/pano/search`, {
      method: "POST",
      headers,
      body: JSON.stringify({ series_no: 5, source_group_no: item.stageNo }),
    });
    const esData = await esResp.json().catch(() => ({}));
    if (!esResp.ok) throw new Error(parseApiError(esResp, esData));
    const outlineSources = [];
    for (const grp of esData.groups || []) {
      for (const art of grp.articles || []) {
        for (const o of art.outline || []) {
          if (o.text && o.source) outlineSources.push({ text: o.text, source: o.source });
        }
      }
    }
    const body = {
      group_results: [{ title: item.title, text: item.text }],
      series_title: "神的行政",
      stage_no: item.stageNo,
      outline_sources: outlineSources,
      is_pano: true,
    };
    const res = await fetch(`${apiBase}/api/progress/ministerialize_segment`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(parseApiError(res, data));
    const art = (data.articles || [])[0];
    if (art) {
      const ZH_NUMS = [
        "〇", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
        "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
        "二十一", "二十二", "二十三", "二十四", "二十五", "二十六", "二十七", "二十八", "二十九", "三十",
      ];
      const zhNo = ZH_NUMS[item.articleNo] || String(item.articleNo);
      if (art.header_lines) {
        art.header_lines[2] = `第${zhNo}篇\u3000${item.title}`;
      }
      art.article_no = item.articleNo;
      item.ministerializeResult = art;
    }
  } catch (e) {
    reprocessError.value = `${item.title} 职事化失败：${e.message}`;
  } finally {
    item.ministerializing = false;
  }
}

async function reprocessAll() {
  reprocessing.value = true;
  reprocessError.value = "";
  for (const item of reprocessParsed.value) {
    if (!item.ministerializeResult) {
      await reprocessMinisterialize(item);
    }
  }
  reprocessing.value = false;
}

async function downloadReprocessDocx(item) {
  const art = item.ministerializeResult;
  if (!art) return;
  const headers = authHeaders();
  if (!headers) return;
  const outlineLines = (art.lines || []).map((line) => ({
    text: (line.result || line.original || "").trim(),
    footnote_no: line.footnote_no ?? null,
  }));
  const body = {
    header_lines: art.header_lines || [],
    outline_lines: outlineLines,
    footnotes: art.footnotes || [],
    article_title: item.title,
  };
  try {
    const res = await fetch(`${apiBase}/api/progress/ministerialize_download`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(parseApiError(res, data));
    }
    const STAGE_SHORT = {
      1: "倪",
      2: "李1932-1973",
      3: "李1974-1984",
      4: "李1985-1990",
      5: "李1991-1997",
    };
    const stageTag = STAGE_SHORT[item.stageNo] ? `（${STAGE_SHORT[item.stageNo]}）` : "";
    const rawTitle = (item.title || "").replace(/^第[一二三四五六七八九十百千万亿\d]+篇[\u3000\s]+/, "");
    const filename = `msg. ${item.articleNo} ${stageTag}${rawTitle}.docx`;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    toastError("下载失败：" + e.message);
  }
}
</script>

<template>
  <div class="progress-outline">
    <ToolsHeader title="主恢复的神圣启示进展" />

    <div class="box">
      <a-spin :spinning="busy">
        <a-tabs :active-key="tab" @change="onTabChange">
          <a-tab-pane key="pano" tab="进展79系列" />
          <a-tab-pane key="entry" tab="新增词条" />
          <a-tab-pane key="reprocess" tab="重新职事化" />
        </a-tabs>

        <div v-if="tab === 'reprocess'" class="reprocess-section">
          <div class="upload-area">
            <input
              id="reprocess-upload"
              type="file"
              accept=".docx"
              multiple
              class="reprocess-upload-input"
              @change="handleReprocessUpload"
            />
            <label for="reprocess-upload" class="upload-btn">选择纲目 DOCX 文件（支持多选）</label>
            <span v-if="reprocessing" class="token-text">处理中…</span>
            <span v-if="reprocessError" class="error-text">{{ reprocessError }}</span>
          </div>

          <div v-if="reprocessParsed.length" class="reprocess-list">
            <div class="reprocess-actions">
              <button
                type="button"
                class="btn-ministerialize"
                :disabled="reprocessing"
                @click="reprocessAll"
              >
                全部职事化加出处
              </button>
            </div>

            <div
              v-for="item in reprocessParsed"
              :key="item.filename"
              class="reprocess-item"
            >
              <div class="reprocess-item-header">
                <span class="article-no">msg. {{ item.articleNo }}</span>
                <span class="stage-tag">（{{ item.stageTag }}）</span>
                <span class="article-title">{{ item.title }}</span>
                <span v-if="item.ministerializeResult" class="cost-tag">
                  ${{ formatCost(item.ministerializeResult.usage?.cost_usd) }}
                </span>
                <button
                  v-if="item.ministerializeResult"
                  type="button"
                  class="btn-download-small"
                  @click="downloadReprocessDocx(item)"
                >
                  含出处下载
                </button>
                <button
                  v-else
                  type="button"
                  class="btn-ministerialize-small"
                  :disabled="reprocessing || item.ministerializing"
                  @click="reprocessMinisterialize(item)"
                >
                  {{ item.ministerializing ? "处理中…" : "职事化" }}
                </button>
              </div>

              <div v-if="item.ministerializeResult" class="reprocess-result">
                <div
                  v-for="(line, li) in item.ministerializeResult.lines"
                  :key="li"
                  class="outline-line-result"
                >
                  <span :class="'status-' + line.status">{{ line.result || line.original }}</span>
                  <span v-if="line.source_zh" class="source-tag">{{ line.footnote_no }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <template v-if="tab !== 'reprocess'">
        <a-card class="section-card" :class="{ locked: generating }">
          <div class="input-row">
            <template v-if="tab === 'pano'">
              <div class="field">
                <span class="label">系列编号</span>
                <a-select
                  v-model:value="seriesNo"
                  :loading="loadingSeries"
                  :disabled="generating"
                  style="min-width: 280px"
                  placeholder="选择系列"
                  @change="onSeriesChange"
                >
                  <a-select-option
                    v-for="s in seriesList"
                    :key="s.series_no"
                    :value="s.series_no"
                  >
                    {{ s.series_no }} — {{ s.series_title }}
                  </a-select-option>
                </a-select>
              </div>
              <div v-if="showSeriesEmptyHint" class="series-empty-hint">
                系列数据暂不可用，请确认索引已导入
              </div>
            </template>
            <template v-else>
              <div class="field grow">
                <span class="label">词条名称</span>
                <a-input
                  v-model:value="term"
                  placeholder="输入词条"
                  :disabled="generating"
                  @press-enter="onStageClick(1)"
                />
              </div>
              <div class="field field-sm">
                <span class="label">top_k</span>
                <a-input-number
                  v-model:value="topK"
                  :min="1"
                  :max="200"
                  :disabled="generating"
                  style="width: 88px"
                />
              </div>
            </template>
          </div>

          <div class="stage-row">
            <a-button
              v-for="st in stages"
              :key="st.no"
              size="small"
              class="stage-btn"
              :type="activeStage === st.no ? 'primary' : 'default'"
              :disabled="searching || generating"
              @click="onStageClick(st.no)"
            >
              {{ st.short }}
            </a-button>
          </div>

          <div v-if="statsVisible" class="meta-row">
            <span class="token-text">材料 Token: {{ estimatedTokens }}</span>
            <span class="token-text cost-summary">
              <template v-if="groupingUsage || segmentUsage !== undefined || ministerializeUsage">
                费用：
                <template v-if="groupingUsage">分组 ${{ formatCost(groupingUsage.cost_usd) }}</template>
                <template v-if="groupingUsage && segmentUsage !== undefined"> · </template>
                <template v-if="segmentUsage !== undefined">
                  纲目 {{ segmentUsage ? '$' + formatCost(segmentUsage.cost_usd) : '未调用模型' }}
                </template>
                <template v-if="ministerializeUsage !== null && ministerializeUsage !== undefined"> · 职事化 ${{ formatCost(ministerializeUsage?.cost_usd) }}</template>
              </template>
            </span>
          </div>

          <div class="gen-row">
            <button
              type="button"
              class="action-btn"
              :disabled="!plainText || generating"
              @click="generate"
            >
              生成分段纲目
            </button>
            <button
              type="button"
              class="action-btn ministerialize-btn"
              :disabled="!segmentGroupResults.length || ministerializing || generating"
              @click="ministerialize"
            >
              {{ ministerializing ? "职事化中…" : "生成纲目职事化" }}
            </button>
          </div>
        </a-card>

        <a-card
          v-if="segmentGroupResults.length || generating"
          class="section-card"
          title="生成结果"
        >
          <div class="stream-box">
            <p v-if="generating" class="generating-hint">正在生成纲目，请稍候…</p>
            <template v-else>
              <div
                v-for="(grp, gi) in segmentGroupResults"
                :key="'seg' + gi + (grp.title || '')"
                class="segment-result-card"
              >
                <h4 class="segment-result-title">{{ grp.title || `分组 ${gi + 1}` }}</h4>
                <pre>{{ grp.text }}</pre>
              </div>
            </template>
          </div>
          <button
            type="button"
            class="action-btn download-btn"
            :disabled="!segmentGroupResults.length || generating || formatting"
            @click="formatDownload"
          >
            <DownloadOutlined />
            {{
              segmentGroupResults.length > 1
                ? "刷格式下载全部（ZIP）"
                : "刷格式下载"
            }}
          </button>
        </a-card>

        <a-card
          v-if="ministerializeResults.length || ministerializing"
          class="section-card"
          title="纲目职事化结果"
        >
          <p v-if="ministerializing" class="generating-hint">正在职事化，请稍候…</p>

          <template v-else>
            <div
              v-for="art in ministerializeResults"
              :key="art.article_no"
              class="article-collapse"
            >
              <div class="article-collapse-head" @click="toggleArticle(art.article_no)">
                <span class="chevron" :class="{ open: articleExpanded[art.article_no] }">›</span>
                <span class="article-collapse-title">
                  第{{ art.article_no }}篇　{{ art.article_title }}
                </span>
                <span v-if="art.usage?.cost_usd > 0" class="article-cost">
                  ${{ formatCost(art.usage.cost_usd) }}
                </span>
                <button
                  type="button"
                  class="action-btn download-article-btn"
                  @click.stop="downloadArticleDocx(art)"
                >
                  <DownloadOutlined /> 含出处下载
                </button>
              </div>

              <div v-show="articleExpanded[art.article_no]" class="article-collapse-body">
                <div class="status-filter-bar">
                  <span
                    class="status-filter-tag all"
                    :class="{ active: !activeFilterStatus[art.article_no] }"
                    @click="setFilter(art.article_no, null)"
                  >
                    全部 {{ (art.lines || []).length }}
                  </span>
                  <span
                    v-for="[key, label, color] in [
                      ['original', '原文', 'green'],
                      ['minor', '微调', 'gold'],
                      ['replaced', '已替换', 'blue'],
                      ['manual', '人工处理', 'red'],
                    ]"
                    :key="key"
                    class="status-filter-tag"
                    :class="[color, { active: activeFilterStatus[art.article_no] === key }]"
                    @click="setFilter(art.article_no, key)"
                  >
                    {{ label }} {{ articleStatusCounts(art)[key] }}
                  </span>
                </div>

                <div class="article-header-block">
                  <p
                    v-for="(line, i) in art.header_lines"
                    :key="i"
                    class="article-header-line"
                    v-html="line.replace('\n', '<br>')"
                  ></p>
                </div>

                <div class="ministerialize-lines">
                  <div
                    v-for="(line, idx) in filteredLines(art)"
                    :key="idx"
                    class="min-line-item"
                  >
                    <div class="min-line-original">
                      <span class="min-line-no">{{ idx + 1 }}.</span>
                      <span class="min-line-text-original">{{ line.original }}</span>
                    </div>

                    <div class="min-line-actions">
                      <a-tag :color="statusColor(line.status)">{{ statusLabel(line.status) }}</a-tag>
                      <a-button size="small" @click="rerunLine(art, idx)">重跑</a-button>
                      <a-button size="small" danger @click="removeLine(art, idx)">删除</a-button>
                    </div>

                    <div class="min-line-result-row">
                      <a-textarea
                        v-model:value="line.result"
                        :rows="2"
                        class="min-line-result-input"
                        :class="statusClass(line.status)"
                      />
                      <sup v-if="line.footnote_no" class="footnote-sup">{{ line.footnote_no }}</sup>
                    </div>

                    <div v-if="line.status === 'minor' && line.suggestion" class="min-line-suggestion">
                      建议：{{ line.suggestion }}
                    </div>

                    <a-input
                      v-if="['replaced', 'minor', 'manual'].includes(line.status)"
                      v-model:value="line.source_zh"
                      class="min-line-source-input"
                      placeholder="手动输入出处，如：创世记生命读经，第一篇；无需括号"
                      @change="onSourceZhChange(art)"
                    />
                  </div>
                </div>

                <div v-if="art.footnotes && art.footnotes.length" class="footnotes-block">
                  <p class="footnotes-title">参考与参读资料：</p>
                  <div
                    v-for="fn in art.footnotes"
                    :key="fn.no"
                    class="footnote-item"
                  >
                    <span class="footnote-no">{{ fn.no }}.</span>
                    <span class="footnote-source">{{ fn.source_zh }}</span>
                  </div>
                </div>

              </div>
            </div>
          </template>

          <a-alert
            v-if="ministerializeError"
            type="error"
            :message="ministerializeError"
            show-icon
            class="error-alert"
          />
        </a-card>

        <a-card v-if="hasResults" class="section-card" :class="{ locked: generating }">
          <template #title>
            <span>检索结果</span>
            <a-tag class="count-tag">{{ countLabel }}</a-tag>
            <a-tag v-if="nGroups > 0" color="purple">{{ nGroups }} 组</a-tag>
            <a-tag v-if="sourceGroupLabel" color="blue">{{ sourceGroupLabel }}</a-tag>
          </template>

          <template v-if="groups.length > 0">
            <p class="group-edit-hint">
              可编辑各组主题与负担；拖动 ⋮⋮ 将参考{{ tab === "pano" ? "篇目" : "段落" }}移至其他组（空组自动删除）
            </p>
            <div
              v-for="(grp, gi) in groups"
              :key="'g' + gi + '-' + (grp.record_ids || []).join(',')"
              class="group-card"
              :class="{ 'drop-target': dropTargetGi === gi }"
              @dragover.prevent="onGroupDragOver(gi)"
              @dragleave="onGroupDragLeave(gi)"
              @drop.prevent="onGroupDrop(gi)"
            >
              <div class="group-index">第 {{ gi + 1 }} 组</div>
              <div class="group-head">
                <label class="field-label" :for="`group-title-${gi}`">主题</label>
                <a-input
                  :id="`group-title-${gi}`"
                  v-model:value="grp.title"
                  class="group-title-input"
                  :disabled="generating"
                  placeholder="本组主题"
                  @change="onGroupsEdited"
                />
                <label class="field-label" :for="`group-burden-${gi}`">负担说明</label>
                <a-textarea
                  :id="`group-burden-${gi}`"
                  v-model:value="grp.burden"
                  class="group-burden-input"
                  :disabled="generating"
                  placeholder="本组负担与方向"
                  :rows="2"
                  @change="onGroupsEdited"
                />
              </div>

              <div class="group-refs">
                <div class="group-refs-head">
                  <span class="field-label section-label">
                    参考{{ tab === "pano" ? "篇目" : "段落" }}
                    <span class="refs-count">（{{ grp.record_count || 0 }}）</span>
                  </span>
                  <span class="group-meta">
                    <template v-if="(grp.record_count || 0) === 1">分段将沿用原文</template>
                    <template v-else-if="(grp.record_count || 0) > 1">分段将调用模型生成</template>
                  </span>
                </div>

              <template v-if="tab === 'pano'">
                <div
                  v-for="(art, idx) in grp.articles || []"
                  :key="art.id || `${gi}-${idx}`"
                  class="collapse-item"
                >
                  <div class="collapse-head">
                    <span
                      class="drag-handle"
                      title="拖到其他组"
                      draggable="true"
                      @dragstart="onDragStart($event, gi, recordKey(art))"
                      @click.stop
                    >⋮⋮</span>
                    <span class="chevron-wrap" @click="toggle(`${gi}-${art.id || idx}`)">
                      <span class="chevron" :class="{ open: expanded[`${gi}-${art.id || idx}`] }">›</span>
                      <span>{{ art.title || `第${art.article_no}篇` }}</span>
                    </span>
                  </div>
                  <div v-show="expanded[`${gi}-${art.id || idx}`]" class="collapse-body">
                    <div v-for="(line, li) in art.outline || []" :key="li" class="outline-line">
                      <span :style="{ paddingLeft: indentEm(line.type) }">{{ line.text }}</span>
                    </div>
                    <p
                      v-for="(para, pi) in art.ministry_excerpt || []"
                      :key="'m' + pi"
                      class="excerpt"
                    >
                      {{ typeof para === "string" ? para : para.text }}
                    </p>
                  </div>
                </div>
              </template>

              <template v-else>
                <div
                  v-for="(it, idx) in grp.items || []"
                  :key="it.chunk_id || `${gi}-${idx}`"
                  class="collapse-item"
                >
                  <div class="collapse-head">
                    <span
                      class="drag-handle"
                      title="拖到其他组"
                      draggable="true"
                      @dragstart="onDragStart($event, gi, recordKey(it))"
                      @click.stop
                    >⋮⋮</span>
                    <span class="chevron-wrap" @click="toggle(`${gi}-${it.chunk_id || idx}`)">
                      <span
                        class="chevron"
                        :class="{ open: expanded[`${gi}-${it.chunk_id || idx}`] }"
                      >›</span>
                      <span>{{ it.source_zh || it.book_title || it.chunk_id }}</span>
                    </span>
                  </div>
                  <div v-show="expanded[`${gi}-${it.chunk_id || idx}`]" class="collapse-body">
                    <p class="detail-text">{{ it.text }}</p>
                  </div>
                </div>
              </template>
              </div>
            </div>
          </template>

          <template v-else-if="tab === 'pano'">
            <div v-for="(art, idx) in articles" :key="art.id || idx" class="collapse-item">
              <div class="collapse-head" @click="toggle(`0-${art.id || idx}`)">
                <span class="chevron" :class="{ open: expanded[`0-${art.id || idx}`] }">›</span>
                <span>{{ art.title || `第${art.article_no}篇` }}</span>
              </div>
              <div v-show="expanded[`0-${art.id || idx}`]" class="collapse-body">
                <div v-for="(line, li) in art.outline || []" :key="li" class="outline-line">
                  <span :style="{ paddingLeft: indentEm(line.type) }">{{ line.text }}</span>
                </div>
                <p v-for="(para, pi) in art.ministry_excerpt || []" :key="'m' + pi" class="excerpt">
                  {{ typeof para === "string" ? para : para.text }}
                </p>
              </div>
            </div>
          </template>

          <template v-else>
            <div v-for="(it, idx) in items" :key="it.chunk_id || idx" class="collapse-item">
              <div class="collapse-head" @click="toggle(`0-${it.chunk_id || idx}`)">
                <span class="chevron" :class="{ open: expanded[`0-${it.chunk_id || idx}`] }">›</span>
                <span>{{ it.source_zh || it.book_title || it.chunk_id }}</span>
              </div>
              <div v-show="expanded[`0-${it.chunk_id || idx}`]" class="collapse-body">
                <p class="detail-text">{{ it.text }}</p>
              </div>
            </div>
          </template>
        </a-card>

        <a-alert v-if="error" type="error" :message="error" show-icon class="error-alert" />
        </template>
      </a-spin>
    </div>

    <div v-if="totalCumulativeCost > 0" class="cumulative-cost-bar">
      <span>
        本阶段
        <b>${{ formatCost((groupingUsage?.cost_usd || 0) + (segmentUsage?.cost_usd || 0) + (ministerializeUsage?.cost_usd || 0)) }}</b>
        · 跨阶段累计
        <b>${{ formatCost(totalCumulativeCost) }}</b>
      </span>
    </div>
  </div>
</template>

<style scoped>
.progress-outline {
  min-height: 100vh;
  background: #f5f6fa;
}

.box {
  width: 70%;
  max-width: 1100px;
  margin: 0 auto;
  padding: 0 16px 32px;
}

.section-card {
  margin-bottom: 16px;
}

.section-card.locked {
  pointer-events: none;
  opacity: 0.55;
}

.input-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 16px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field.grow {
  flex: 1;
  min-width: 200px;
}

.field-sm {
  flex-shrink: 0;
}

.label {
  font-size: 13px;
  color: #666;
}

.stage-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.stage-btn {
  flex: 0 0 auto;
  white-space: nowrap;
}

.meta-row {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.token-text {
  font-size: 13px;
  color: #888;
}

.grouping-cost {
  color: #1677ff;
}

.field-inline {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gen-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.action-btn {
  background: #1677ff;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 8px 20px;
  font-size: 14px;
  cursor: pointer;
}

.action-btn:hover:not(:disabled) {
  background: #4096ff;
}

.action-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.download-btn {
  margin-top: 12px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.gen-cost {
  font-size: 13px;
  color: #1677ff;
}

.stream-box {
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 16px;
  max-height: 400px;
  overflow: auto;
  line-height: 1.7;
}

.generating-hint {
  margin: 0;
  color: #1677ff;
  text-align: center;
  padding: 24px 0;
}

.stream-box pre {
  margin: 0;
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 14px;
}

.segment-result-card {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px dashed #e8e8e8;
}

.segment-result-card:last-child {
  margin-bottom: 0;
  border-bottom: none;
  padding-bottom: 0;
}

.segment-result-title {
  margin: 0 0 8px;
  font-size: 14px;
  color: #1677ff;
}

.count-tag {
  margin-left: 8px;
}

.group-card {
  margin-bottom: 20px;
  padding: 8px 8px 12px;
  border: 1px dashed #e8e8e8;
  border-radius: 8px;
  transition: border-color 0.15s, background 0.15s;
}

.group-card.drop-target {
  border-color: #1677ff;
  background: #f0f7ff;
}

.group-card:last-child {
  margin-bottom: 0;
}

.group-edit-hint {
  margin: 0 0 12px;
  font-size: 12px;
  color: #888;
}

.group-index {
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 600;
  color: #722ed1;
}

.group-head {
  margin-bottom: 12px;
}

.field-label {
  display: block;
  margin-bottom: 4px;
  font-size: 12px;
  font-weight: 500;
  color: #666;
}

.field-label.section-label {
  margin-bottom: 0;
  font-size: 13px;
  color: #444;
}

.refs-count {
  font-weight: 400;
  color: #888;
}

.group-title-input {
  margin-bottom: 10px;
  font-weight: 600;
}

.group-burden-input {
  margin-bottom: 0;
}

.group-refs {
  padding-top: 10px;
  border-top: 1px solid #f0f0f0;
}

.group-refs-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}

.group-meta {
  font-size: 12px;
  color: #999;
  white-space: nowrap;
}

.drag-handle {
  flex-shrink: 0;
  width: 20px;
  color: #bbb;
  cursor: grab;
  user-select: none;
  font-size: 12px;
  letter-spacing: -2px;
  text-align: center;
}

.drag-handle:active {
  cursor: grabbing;
}

.chevron-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  cursor: pointer;
  min-width: 0;
}

.collapse-item {
  border-bottom: 1px solid #f0f0f0;
}

.collapse-head {
  padding: 10px 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #444;
}

.collapse-head:hover {
  background: #f5f5f5;
}

.chevron {
  transition: transform 0.2s;
  color: #999;
}

.chevron.open {
  transform: rotate(90deg);
}

.collapse-body {
  padding: 0 8px 12px 20px;
  font-size: 13px;
  line-height: 1.8;
}

.excerpt,
.detail-text {
  margin: 8px 0 0;
  white-space: pre-wrap;
}

.error-alert {
  margin-top: 8px;
}

.series-empty-hint {
  margin-top: 8px;
  padding: 0.65rem 0.85rem;
  background: #fffbe6;
  border: 1px solid #ffe58f;
  border-radius: 8px;
  color: #ad6800;
  font-size: 0.9em;
  line-height: 1.5;
}

/* ── 职事化折叠卡片 ── */
.article-collapse {
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  margin-bottom: 12px;
  overflow: hidden;
}

.article-collapse-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: #fafafa;
  cursor: pointer;
  user-select: none;
}

.article-collapse-head:hover {
  background: #f0f7ff;
}

.article-collapse-title {
  flex: 1;
  font-weight: 600;
  font-size: 14px;
  color: #1677ff;
}

.article-cost {
  font-size: 12px;
  color: #888;
  white-space: nowrap;
}

.download-article-btn {
  padding: 4px 10px;
  font-size: 12px;
  white-space: nowrap;
}

.article-collapse-body {
  padding: 16px;
  border-top: 1px solid #e8e8e8;
}

.article-header-block {
  text-align: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
}

.article-header-line {
  margin: 2px 0;
  font-size: 14px;
  font-weight: 500;
  line-height: 1.8;
}

.ministerialize-lines {
  margin-bottom: 16px;
}

.min-line-item {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px dashed #f0f0f0;
}

.min-line-item:last-child {
  border-bottom: none;
}

.min-line-original {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
  color: #888;
  font-size: 13px;
}

.min-line-no {
  flex-shrink: 0;
  color: #bbb;
}

.min-line-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}

.min-line-result-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
}

.min-line-result-input {
  flex: 1;
  font-size: 14px;
}

.status-original {
  border-color: #52c41a !important;
}

.status-minor {
  border-color: #faad14 !important;
}

.status-replaced {
  border-color: #1677ff !important;
}

.status-manual {
  border-color: #ff4d4f !important;
}

.footnote-sup {
  font-size: 11px;
  color: #1677ff;
  flex-shrink: 0;
  margin-top: 6px;
}

.min-line-suggestion {
  margin-top: 4px;
  font-size: 12px;
  color: #888;
  padding-left: 4px;
  border-left: 2px solid #faad14;
}

.min-line-source-input {
  margin-top: 6px;
  font-size: 13px;
  color: #555;
}

.footnotes-block {
  margin-top: 16px;
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
  border: 1px solid #f0f0f0;
}

.footnotes-title {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: #444;
}

.footnote-item {
  display: flex;
  gap: 8px;
  font-size: 13px;
  color: #555;
  margin-bottom: 4px;
}

.footnote-no {
  flex-shrink: 0;
  color: #1677ff;
  font-weight: 600;
}

.article-usage-row {
  margin-top: 12px;
  font-size: 12px;
  color: #888;
  text-align: right;
}

.cumulative-cost-bar {
  position: fixed;
  bottom: 24px;
  right: 32px;
  background: #1677ff;
  color: #fff;
  padding: 8px 18px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
  box-shadow: 0 2px 8px rgba(22, 119, 255, 0.25);
  z-index: 999;
}

.ministerialize-cost {
  color: #722ed1;
}

.ministerialize-btn {
  background: #722ed1;
}

.ministerialize-btn:hover:not(:disabled) {
  background: #9254de;
}

.status-filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  padding: 8px 12px;
  background: #f5f5f5;
  border-radius: 6px;
}

.status-filter-tag {
  padding: 2px 10px;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s;
  user-select: none;
}

.status-filter-tag.all {
  background: #fff;
  border-color: #d9d9d9;
  color: #444;
}

.status-filter-tag.all.active {
  background: #444;
  color: #fff;
  border-color: #444;
}

.status-filter-tag.green {
  background: #f6ffed;
  color: #52c41a;
  border-color: #b7eb8f;
}

.status-filter-tag.gold {
  background: #fffbe6;
  color: #d48806;
  border-color: #ffe58f;
}

.status-filter-tag.blue {
  background: #e6f4ff;
  color: #1677ff;
  border-color: #91caff;
}

.status-filter-tag.red {
  background: #fff2f0;
  color: #ff4d4f;
  border-color: #ffccc7;
}

.status-filter-tag.green.active {
  background: #52c41a;
  color: #fff;
  border-color: #52c41a;
}

.status-filter-tag.gold.active {
  background: #d48806;
  color: #fff;
  border-color: #d48806;
}

.status-filter-tag.blue.active {
  background: #1677ff;
  color: #fff;
  border-color: #1677ff;
}

.status-filter-tag.red.active {
  background: #ff4d4f;
  color: #fff;
  border-color: #ff4d4f;
}

.status-filter-cost {
  margin-left: auto;
  font-size: 12px;
  color: #888;
}

.reprocess-section {
  margin-bottom: 16px;
}

.upload-area {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  padding: 20px;
  background: #fff;
  border-radius: 8px;
  border: 1px dashed #d9d9d9;
  margin-bottom: 16px;
}

.reprocess-upload-input {
  display: none;
}

.upload-btn {
  display: inline-block;
  padding: 8px 16px;
  background: #1677ff;
  color: #fff;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.upload-btn:hover {
  background: #4096ff;
}

.error-text {
  color: #ff4d4f;
  font-size: 13px;
}

.reprocess-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.reprocess-actions {
  margin-bottom: 8px;
}

.btn-ministerialize,
.btn-ministerialize-small {
  padding: 6px 14px;
  background: #722ed1;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.btn-ministerialize:disabled,
.btn-ministerialize-small:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-download-small {
  padding: 4px 10px;
  background: #1677ff;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  margin-left: auto;
}

.reprocess-item {
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 12px 16px;
}

.reprocess-item-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.reprocess-item-header .article-no {
  font-weight: 600;
  color: #1677ff;
}

.reprocess-item-header .stage-tag {
  color: #888;
  font-size: 13px;
}

.reprocess-item-header .article-title {
  flex: 1;
  min-width: 120px;
}

.cost-tag {
  font-size: 12px;
  color: #722ed1;
}

.reprocess-result {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
}

.outline-line-result {
  font-size: 13px;
  line-height: 1.6;
  margin-bottom: 4px;
}

.outline-line-result .source-tag {
  margin-left: 6px;
  color: #1677ff;
  font-size: 11px;
}

.status-original { color: #389e0d; }
.status-minor { color: #d48806; }
.status-replaced { color: #1677ff; }
.status-manual { color: #ff4d4f; }
</style>

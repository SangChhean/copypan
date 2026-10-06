<script setup>
import { computed, nextTick, onMounted, ref } from "vue";
import { ArrowLeftOutlined, CopyOutlined, DownloadOutlined } from "@ant-design/icons-vue";
import axios from "axios";
import { message } from "ant-design-vue";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";
const api = `${apiBase}/api/v40burden`;

// 字面值与后端 LAYERS 一致，注意是「显出的外在」。没有默认值，必选。
const NATURES = ["外在", "内在", "最内在", "显出的外在"];
const LAYER_COLORS = { 外在: "blue", 内在: "green", 最内在: "purple", 显出的外在: "orange" };

function getAuthHeaders() {
  const token = localStorage.getItem("token") || null;
  if (!token) {
    window.location.hash = "/login";
    return null;
  }
  return { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
}

function goBack() {
  window.location.hash = "/tools";
}

function errText(e, fallback) {
  const d = e?.response?.data;
  return d?.detail || d?.error || e?.message || fallback;
}

// ---------- 页面信息 ----------
const meta = ref(null);
onMounted(async () => {
  const headers = getAuthHeaders();
  if (!headers) return;
  try {
    meta.value = (await axios.get(`${api}/meta`, { headers })).data;
  } catch {
    meta.value = null;
  }
  loadHistory();
});

// ---------- 生成 ----------
const topicNo = ref("");
const query = ref("");
const nature = ref(undefined);
const audience = ref("");
const excerpt = ref("");
const loading = ref(false);
const result = ref(null);
const errorMsg = ref("");

const canGenerate = computed(() => !!(query.value || "").trim() && !!nature.value && !loading.value);

async function generate() {
  if (!canGenerate.value) return;
  const headers = getAuthHeaders();
  if (!headers) return;
  loading.value = true;
  result.value = null;
  errorMsg.value = "";
  try {
    const res = await axios.post(
      `${api}/generate`,
      {
        topic_no: topicNo.value.trim(),
        query: query.value.trim(),
        outline_nature: nature.value,
        audience: audience.value.trim(),
        reference_excerpt: excerpt.value.trim(),
      },
      { headers, timeout: 300000 }
    );
    result.value = res.data;
    viewingHistory.value = false;
    loadHistory();
  } catch (e) {
    errorMsg.value = errText(e, "生成失败");
  } finally {
    loading.value = false;
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(String(text || ""));
    message.success("已复制");
  } catch (e) {
    message.error(e?.message || "复制失败");
  }
}

function layerColor(layer) {
  return LAYER_COLORS[layer] || "default";
}

// 把 ["词（层）", ...] 按层拆成四行；层名取自最后一对全角括号
function groupTerms(items) {
  const g = Object.fromEntries(NATURES.map((n) => [n, []]));
  const other = [];
  for (const s of items || []) {
    const m = /^(.*)（([^（）]+)）$/.exec(String(s));
    if (m && g[m[2]]) g[m[2]].push(m[1]);
    else other.push(String(s));
  }
  const rows = NATURES.map((n) => ({ layer: n, words: g[n] }));
  if (other.length) rows.push({ layer: "其他", words: other });
  return rows;
}

// ---------- 把属于某层的词标出来 ----------
const markMode = ref("own"); // own 只标本条性质的词 | all 四层都标 | off 不标
const markSingle = ref(false); // 单字词条（神、主、灵…）误中太多，默认不标
const LAYER_BG = { 外在: "#bae0ff", 内在: "#d9f7be", 最内在: "#efdbff", 显出的外在: "#ffe7ba" };

function segments(text, hits, ownLayer) {
  const src = String(text || "");
  if (markMode.value === "off" || !Array.isArray(hits) || !hits.length) return [{ t: src, layer: null }];
  const keep = hits
    .filter((h) => (markSingle.value || !h["单字"]) && (markMode.value === "all" || h["层次"] === ownLayer))
    .sort((a, b) => a["位置"] - b["位置"]);
  const out = [];
  let pos = 0;
  for (const h of keep) {
    const s = h["位置"];
    const e = s + String(h["文字"]).length;
    if (s < pos) continue;
    if (s > pos) out.push({ t: src.slice(pos, s), layer: null });
    out.push({ t: src.slice(s, e), layer: h["层次"] });
    pos = e;
  }
  if (pos < src.length) out.push({ t: src.slice(pos), layer: null });
  return out;
}

function escapeHtml(t) {
  return String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// 带格式复制：同时放 text/html 与 text/plain，粘贴到 Word 会保留底色和加粗
async function copyRich(text, hits, ownLayer) {
  const html =
    '<p style="line-height:1.9;">' +
    segments(text, hits, ownLayer)
      .map((sg) =>
        sg.layer
          ? `<span style="background-color:${LAYER_BG[sg.layer]};font-weight:bold;">${escapeHtml(sg.t)}</span>`
          : escapeHtml(sg.t)
      )
      .join("") +
    "</p>";
  try {
    if (window.ClipboardItem && navigator.clipboard?.write) {
      await navigator.clipboard.write([
        new ClipboardItem({
          "text/html": new Blob([html], { type: "text/html" }),
          "text/plain": new Blob([String(text || "")], { type: "text/plain" }),
        }),
      ]);
    } else {
      const el = document.createElement("div");
      el.contentEditable = "true";
      el.style.cssText = "position:fixed;left:-9999px;top:0;";
      el.innerHTML = html;
      document.body.appendChild(el);
      const range = document.createRange();
      range.selectNodeContents(el);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      document.execCommand("copy");
      sel.removeAllRanges();
      document.body.removeChild(el);
    }
    message.success("已复制（带标记，可粘贴到 Word）");
  } catch (e) {
    message.error(e?.message || "复制失败");
  }
}

function statsRows(stats) {
  if (!stats) return [];
  return NATURES.map((k) => ({
    layer: k,
    count: stats["各层个数"]?.[k] ?? 0,
    ratio: stats["各层比例"]?.[k] ?? 0,
  }));
}

// ---------- 导出 ----------
function exportMarkdown() {
  const no = topicNo.value.trim();
  if (!no) {
    message.warning("请先填写篇题编号");
    return;
  }
  return exportTopic(no);
}

async function exportTopic(no) {
  if (!no) return;
  const headers = getAuthHeaders();
  if (!headers) return;
  try {
    const res = await axios.get(`${api}/export`, { headers, params: { topic_no: no }, responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${no}-v40-item1.md`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    message.error(errText(e, "导出失败"));
  }
}

// ---------- 历史记录（每次生成后端自动保存，页面随时回看） ----------
const history = ref([]);
const historyLoading = ref(false);
const historyFilter = ref("");
const viewingHistory = ref(false);

const historyRows = computed(() => {
  const kw = historyFilter.value.trim().toLowerCase();
  const rows = [...history.value].reverse(); // 新的在前
  if (!kw) return rows;
  return rows.filter((r) =>
    [r.record_id, r.topic_no, r.query, r.outline_nature].some((x) => String(x || "").toLowerCase().includes(kw))
  );
});

const historyColumns = [
  { title: "记录编号", dataIndex: "record_id", key: "record_id", width: 120 },
  { title: "时间", key: "time", width: 150 },
  { title: "篇题", key: "query", width: 240 },
  { title: "纲目性质", key: "nature", width: 100 },
  { title: "各条（层次·字数）", key: "parts", width: 330 },
  { title: "操作", key: "ops", width: 210 },
];

function fmtTime(t) {
  return String(t || "").replace("T", " ");
}

async function loadHistory() {
  const headers = getAuthHeaders();
  if (!headers) return;
  historyLoading.value = true;
  try {
    history.value = (await axios.get(`${api}/records`, { headers })).data?.records || [];
  } catch (e) {
    message.error(errText(e, "读取历史记录失败"));
  } finally {
    historyLoading.value = false;
  }
}

async function fetchRecord(rid) {
  const headers = getAuthHeaders();
  if (!headers) return null;
  try {
    return (await axios.get(`${api}/records/${encodeURIComponent(rid)}`, { headers })).data;
  } catch (e) {
    message.error(errText(e, "读取记录失败"));
    return null;
  }
}

async function openRecord(rid) {
  const rec = await fetchRecord(rid);
  if (!rec) return;
  result.value = rec;
  viewingHistory.value = true;
  errorMsg.value = "";
  await nextTick();
  document.getElementById("v40-result-anchor")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function loadParams(rid) {
  const rec = await fetchRecord(rid);
  if (!rec) return;
  topicNo.value = rec.topic_no && rec.topic_no !== "NA" ? rec.topic_no : "";
  query.value = rec.query || "";
  nature.value = NATURES.includes(rec.outline_nature) ? rec.outline_nature : undefined;
  audience.value = rec.audience || "";
  excerpt.value = rec.reference_excerpt || "";
  window.scrollTo({ top: 0, behavior: "smooth" });
  message.success("已载入到上方参数，可直接重新生成");
}

// ---------- 词条分层统计（任意文字） ----------
const statsText = ref("");
const statsIncludeSingle = ref(false);
const statsLoading = ref(false);
const statsResult = ref(null);

async function runTermStats() {
  const text = (statsText.value || "").trim();
  if (!text) {
    message.warning("请先贴入文字");
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;
  statsLoading.value = true;
  try {
    statsResult.value = (
      await axios.post(`${api}/term_stats`, { text, include_single: statsIncludeSingle.value }, { headers })
    ).data;
  } catch (e) {
    message.error(errText(e, "统计失败"));
  } finally {
    statsLoading.value = false;
  }
}
</script>

<template>
  <div class="v40-header">
    <div class="header-left" @click="goBack"><ArrowLeftOutlined class="header-back" /></div>
    <div class="header-title">【原流程不变】4.0测试台</div>
    <div class="header-right"></div>
  </div>

  <div class="v40-page">
    <a-alert
      type="info"
      show-icon
      class="block"
      message="第1项测试只到负担说明：纲目性质的新值不会进入 Step1–3，也不影响 3.5。"
      :description="
        meta
          ? `模型 ${meta.model}（不传 temperature，失败直接报错，不降级）；max_tokens ${meta.max_tokens}；每条上限 ${meta.char_limit} 字；prompt ${meta.prompt_name}（${meta.prompt_hash}）`
          : ''
      "
    />

    <a-card size="small" title="测试参数" class="block">
      <a-row :gutter="[12, 12]">
        <a-col :xs="24" :md="6">
          <div class="param-label">篇题编号（选填，如 T1）</div>
          <a-input v-model:value="topicNo" placeholder="T1" allow-clear />
        </a-col>
        <a-col :xs="24" :md="18">
          <div class="param-label">篇题 / 主题</div>
          <a-input v-model:value="query" placeholder="请输入纲目主题" allow-clear />
        </a-col>
        <a-col :span="24">
          <div class="param-label">纲目性质（必选）</div>
          <a-radio-group v-model:value="nature" button-style="solid">
            <a-radio-button v-for="n in NATURES" :key="n" :value="n">{{ n }}</a-radio-button>
          </a-radio-group>
        </a-col>
        <a-col :span="24">
          <div class="param-label">面对对象（选填）</div>
          <a-input v-model:value="audience" allow-clear />
        </a-col>
        <a-col :span="24">
          <div class="param-label">参考摘录（选填；填了走情境 A，留空走情境 B 生成三条候选）</div>
          <a-textarea
            v-model:value="excerpt"
            :auto-size="{ minRows: 2, maxRows: 8 }"
            placeholder="粘贴参考段落；留空则生成三条候选"
          />
        </a-col>
        <a-col :span="24" class="actions">
          <a-button type="primary" :loading="loading" :disabled="!canGenerate" @click="generate">生成负担说明</a-button>
          <span v-if="!nature" class="hint">请先选择纲目性质</span>
          <a-button class="push-right" :disabled="!topicNo.trim()" @click="exportMarkdown">
            <template #icon><DownloadOutlined /></template>
            导出本篇题编号的 Markdown
          </a-button>
        </a-col>
      </a-row>
    </a-card>

    <a-alert v-if="errorMsg" type="error" show-icon class="block" :message="errorMsg" />

    <div v-if="loading" class="loading-box"><a-spin /> 正在调用 {{ meta?.model || "模型" }}…</div>

    <template v-if="result">
      <div id="v40-result-anchor"></div>
      <a-card size="small" class="block" :title="`结果　${result.record_id || ''}`">
        <div class="tags">
          <a-tag v-if="viewingHistory" color="red">历史记录（{{ fmtTime(result.time) }}）</a-tag>
          <a-tag color="blue">{{ result.version }}</a-tag>
          <a-tag :color="layerColor(result.outline_nature)">纲目性质：{{ result.outline_nature }}</a-tag>
          <a-tag>情境 {{ result.scenario || "—" }}</a-tag>
          <a-tag>实际模型 {{ result.actual_model }}</a-tag>
          <a-tag>stop_reason {{ result.stop_reason }}</a-tag>
          <a-tag>{{ (result.elapsed_ms / 1000).toFixed(1) }} s</a-tag>
          <a-tag v-if="result.cost_usd != null" color="gold">≈${{ result.cost_usd }}</a-tag>
        </div>
        <div class="mark-bar">
          <span class="stats-title">标出词条：</span>
          <a-radio-group v-model:value="markMode" size="small" button-style="solid">
            <a-radio-button value="own">只标本条性质的词</a-radio-button>
            <a-radio-button value="all">四层都标</a-radio-button>
            <a-radio-button value="off">不标</a-radio-button>
          </a-radio-group>
          <a-checkbox v-model:checked="markSingle">单字词条也标</a-checkbox>
          <span class="legend">
            <mark v-for="n in NATURES" :key="n" class="mk" :style="{ backgroundColor: LAYER_BG[n] }">{{ n }}</mark>
          </span>
        </div>
        <div class="small muted">标记按最大匹配做初筛，可能切错（例如「生命的光照」会切成「生命的光」+「照」），需人工核对。</div>
        <a-alert
          v-for="(w, i) in result.warnings"
          :key="i"
          type="warning"
          show-icon
          class="warn"
          :message="w"
        />
        <a-alert v-if="result.error" type="error" show-icon class="warn" :message="`${result.error}（见下方原始输出）`" />
      </a-card>

      <!-- 情境 B -->
      <template v-if="result.scenario === 'B'">
        <a-card v-for="c in result.candidates" :key="c.index" size="small" class="block">
          <template #title>
            <span>候选{{ ["一", "二", "三"][c.index - 1] }}</span>
            <a-tag :color="layerColor(c.layer)" style="margin-left: 8px">{{ c.layer ? `【${c.layer}】` : "无层次标记" }}</a-tag>
            <a-tag>{{ c.chars }} 字</a-tag>
          </template>
          <template #extra>
            <a-button size="small" type="primary" @click="copyRich(c.text, c.term_hits, c.layer)">
              <template #icon><CopyOutlined /></template>复制（带标记）
            </a-button>
            <a-button size="small" style="margin-left: 6px" @click="copyText(c.text)">复制纯文字</a-button>
          </template>
          <div class="cand-text">
            <template v-for="(sg, i) in segments(c.text, c.term_hits, c.layer)" :key="i">
              <mark v-if="sg.layer" class="mk" :style="{ backgroundColor: LAYER_BG[sg.layer] }" :title="sg.layer">{{ sg.t }}</mark>
              <template v-else>{{ sg.t }}</template>
            </template>
            <template v-if="!c.text">（空）</template>
          </div>
          <div v-if="c.term_stats" class="stats">
            <span class="stats-title">词条分层：计入 {{ c.term_stats["计入词条数"] }}</span>
            <a-tag v-for="r in statsRows(c.term_stats)" :key="r.layer" :color="layerColor(r.layer)">
              {{ r.layer }} {{ r.count }}（{{ r.ratio }}%）
            </a-tag>
            <a-collapse ghost size="small">
              <a-collapse-panel key="d" header="计入的词条与单字词条">
                <div class="term-title">计入的词条</div>
                <div v-for="row in groupTerms(c.term_stats['计入的词条'])" :key="'c' + row.layer" class="term-row">
                  <a-tag :color="layerColor(row.layer)">{{ row.layer }} {{ row.words.length }}</a-tag>
                  <span class="term-words">{{ row.words.join("、") || "（无）" }}</span>
                </div>
                <div class="term-title">单字词条（未计入，需人工核对）</div>
                <div v-for="row in groupTerms(c.term_stats['单字词条（未计入，需人工核对）'])" :key="'s' + row.layer" class="term-row">
                  <a-tag :color="layerColor(row.layer)">{{ row.layer }} {{ row.words.length }}</a-tag>
                  <span class="term-words">{{ row.words.join("、") || "（无）" }}</span>
                </div>
              </a-collapse-panel>
            </a-collapse>
          </div>
        </a-card>
      </template>

      <!-- 情境 A -->
      <a-card v-else-if="result.scenario === 'A'" size="small" class="block">
        <template #title>负担说明 <a-tag>{{ result.result_chars }} 字</a-tag></template>
        <template #extra>
          <a-button size="small" type="primary" @click="copyRich(result.result, result.term_hits_result, result.outline_nature)">
            <template #icon><CopyOutlined /></template>复制（带标记）
          </a-button>
          <a-button size="small" style="margin-left: 6px" @click="copyText(result.result)">复制纯文字</a-button>
        </template>
        <div class="cand-text">
          <template v-for="(sg, i) in segments(result.result, result.term_hits_result, result.outline_nature)" :key="i">
            <mark v-if="sg.layer" class="mk" :style="{ backgroundColor: LAYER_BG[sg.layer] }" :title="sg.layer">{{ sg.t }}</mark>
            <template v-else>{{ sg.t }}</template>
          </template>
        </div>
        <div v-if="result.term_stats_result" class="stats">
          <span class="stats-title">词条分层：计入 {{ result.term_stats_result["计入词条数"] }}</span>
          <a-tag v-for="r in statsRows(result.term_stats_result)" :key="r.layer" :color="layerColor(r.layer)">
            {{ r.layer }} {{ r.count }}（{{ r.ratio }}%）
          </a-tag>
        </div>
      </a-card>

      <a-collapse class="block">
        <a-collapse-panel key="raw" header="模型原始输出（切分前的全文）">
          <pre class="pre">{{ result.raw_output }}</pre>
        </a-collapse-panel>
        <a-collapse-panel key="prompt" header="实际送出的完整 prompt">
          <pre class="pre">{{ result.prompt }}</pre>
          <div class="small">system：{{ result.system_prompt }}</div>
        </a-collapse-panel>
      </a-collapse>
    </template>

    <a-card size="small" class="block">
      <template #title>
        历史记录 <a-tag>{{ history.length }} 条</a-tag>
        <span class="small muted">每次生成后端自动保存（back_mic/backend/data/v40_burden/）</span>
      </template>
      <template #extra>
        <a-button size="small" :loading="historyLoading" @click="loadHistory">刷新</a-button>
      </template>
      <a-input
        v-model:value="historyFilter"
        allow-clear
        placeholder="按篇题、篇题编号、记录编号或纲目性质筛选"
        style="margin-bottom: 8px"
      />
      <a-table
        :columns="historyColumns"
        :data-source="historyRows"
        row-key="record_id"
        size="small"
        :pagination="{ pageSize: 10, showSizeChanger: false }"
        :scroll="{ x: 1150 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'time'">{{ fmtTime(record.time) }}</template>
          <template v-else-if="column.key === 'query'">
            <a-tag v-if="record.topic_no && record.topic_no !== 'NA'">{{ record.topic_no }}</a-tag>{{ record.query }}
          </template>
          <template v-else-if="column.key === 'nature'">
            <a-tag :color="layerColor(record.outline_nature)">{{ record.outline_nature }}</a-tag>
          </template>
          <template v-else-if="column.key === 'parts'">
            <span class="small">情境 {{ record.scenario || "—" }}：</span>
            <a-tag v-for="(p, i) in record.parts" :key="i" :color="layerColor(p.layer)">
              {{ p.layer || "无" }}·{{ p.chars ?? "—" }}字
            </a-tag>
            <a-tag v-if="record.warnings" color="red">警示 {{ record.warnings }}</a-tag>
          </template>
          <template v-else-if="column.key === 'ops'">
            <a-button type="link" size="small" @click="openRecord(record.record_id)">查看</a-button>
            <a-button type="link" size="small" @click="loadParams(record.record_id)">载入参数</a-button>
            <a-button type="link" size="small" @click="exportTopic(record.topic_no)">导出该编号</a-button>
          </template>
        </template>
      </a-table>
    </a-card>

    <a-card size="small" title="词条分层统计（贴入任意文字，如 3.5 的输出或真实纲目）" class="block">
      <a-textarea v-model:value="statsText" :auto-size="{ minRows: 3, maxRows: 10 }" placeholder="贴入文字" />
      <div class="actions" style="margin-top: 8px">
        <a-button :loading="statsLoading" @click="runTermStats">统计</a-button>
        <a-checkbox v-model:checked="statsIncludeSingle">单字词条也计入比例</a-checkbox>
      </div>
      <div v-if="statsResult" class="stats">
        <span class="stats-title">计入 {{ statsResult["计入词条数"] }}</span>
        <a-tag v-for="r in statsRows(statsResult)" :key="r.layer" :color="layerColor(r.layer)">
          {{ r.layer }} {{ r.count }}（{{ r.ratio }}%）
        </a-tag>
        <div class="term-title">计入的词条</div>
        <div v-for="row in groupTerms(statsResult['计入的词条'])" :key="'c' + row.layer" class="term-row">
          <a-tag :color="layerColor(row.layer)">{{ row.layer }} {{ row.words.length }}</a-tag>
          <span class="term-words">{{ row.words.join("、") || "（无）" }}</span>
        </div>
        <div class="term-title">单字词条（未计入，需人工核对）</div>
        <div v-for="row in groupTerms(statsResult['单字词条（未计入，需人工核对）'])" :key="'s' + row.layer" class="term-row">
          <a-tag :color="layerColor(row.layer)">{{ row.layer }} {{ row.words.length }}</a-tag>
          <span class="term-words">{{ row.words.join("、") || "（无）" }}</span>
        </div>
        <div class="small muted">这只是初筛：最大匹配会切错（例如「生命的光照」会切成「生命的光」+「照」），结果要人工核对。</div>
      </div>
    </a-card>
  </div>
</template>

<style scoped lang="less">
.v40-header {
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
  .header-right {
    width: 16px;
  }
}
.v40-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 0 16px 32px;
}
.block {
  margin-bottom: 16px;
}
.param-label {
  font-size: 13px;
  color: rgba(0, 0, 0, 0.65);
  margin-bottom: 4px;
}
.actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.push-right {
  margin-left: auto;
}
.hint {
  color: #d46b08;
  font-size: 13px;
}
.loading-box {
  text-align: center;
  padding: 24px;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 0;
  margin-bottom: 8px;
}
.warn {
  margin-top: 8px;
}
.cand-text {
  line-height: 1.9;
  font-size: 15px;
  white-space: pre-wrap;
}
.stats {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed #e5e5e5;
  .stats-title {
    margin-right: 8px;
    font-size: 13px;
    color: rgba(0, 0, 0, 0.65);
  }
}
.small {
  font-size: 12px;
  line-height: 1.7;
  word-break: break-all;
}
.mark-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-top: 4px;
  .legend {
    display: inline-flex;
    gap: 4px;
  }
}
.mk {
  font-weight: 600;
  padding: 0 1px;
  border-radius: 2px;
  color: inherit;
}
.term-title {
  font-size: 12px;
  font-weight: 600;
  color: rgba(0, 0, 0, 0.65);
  margin: 6px 0 2px;
}
.term-row {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  font-size: 12px;
  line-height: 1.8;
  :deep(.ant-tag) {
    flex: none;
    margin-right: 0;
  }
  .term-words {
    word-break: break-all;
  }
}
.muted {
  color: rgba(0, 0, 0, 0.45);
  margin-top: 4px;
}
.pre {
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
  max-height: 520px;
  overflow: auto;
  margin: 0;
}
</style>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import axios from "axios";
import { message } from "ant-design-vue";

const props = defineProps({
  api: { type: String, required: true },
  getAuthHeaders: { type: Function, required: true },
});

const meta = ref(null);
const loadingMeta = ref(false);
const topic = ref("");
const selectPrompt = ref("");
const plainPrompt = ref("");
const refPrompt = ref("");
const selecting = ref(false);
const generating = ref(false);
const selected = ref([]); // {name, tier, reason, has_3a, in_list, tier_mismatch}
const rawSelect = ref("");
const selectUsage = ref(null);
const selectCost = ref(null);
const selectRunId = ref(null);
const search = ref("");
const genResult = ref(null);
const history = ref([]);
const historyCostSum = ref("—");
const historyCostCount = ref(0);
const detail = ref(null);

const detailCitation = ref(null);
const exportWarn = ref("");

const TIER_ORDER = ["最内在", "内在", "外在"];
const STATUS_LABEL = {
  in_outline: "入脉络",
  defs_only: "仅界定",
  uncited: "未引用",
  listed: "已列出",
  in_text: "文中出现",
  both: "两者都有",
  unused: "未使用",
};

function isDirectCitation(stats) {
  return stats?.format === "direct";
}

function citationSummaryLine(stats, tier) {
  if (!stats?.by_tier?.[tier]) return "";
  const b = stats.by_tier[tier];
  const t = b.total || 0;
  if (!t) return `${tier} 0/0`;
  if (isDirectCitation(stats)) {
    const listed = (b.listed || 0) + (b.both || 0);
    return `${tier} 已列出 ${listed} · 仅文中出现 ${b.in_text || 0} · 未使用 ${b.unused || 0}`;
  }
  return `${tier} ${b.in_outline || 0}/${t} 入脉络 · ${b.defs_only || 0}/${t} 仅界定 · ${b.uncited || 0}/${t} 未引用`;
}

function citationTotalLine(stats) {
  if (!stats?.by_tier) return "";
  let total = 0;
  if (isDirectCitation(stats)) {
    let listed = 0;
    let inText = 0;
    let unc = 0;
    TIER_ORDER.forEach((tier) => {
      const b = stats.by_tier[tier] || {};
      total += b.total || 0;
      listed += (b.listed || 0) + (b.both || 0);
      inText += b.in_text || 0;
      unc += b.unused || 0;
    });
    if (!total) return `合计 0/0`;
    return `合计 已列出 ${listed} · 仅文中出现 ${inText} · 未使用 ${unc}`;
  }
  let inO = 0;
  let defs = 0;
  let unc = 0;
  TIER_ORDER.forEach((tier) => {
    const b = stats.by_tier[tier] || {};
    total += b.total || 0;
    inO += b.in_outline || 0;
    defs += b.defs_only || 0;
    unc += b.uncited || 0;
  });
  if (!total) return `合计 0/0`;
  return `合计 ${inO}/${total} 入脉络 · ${defs}/${total} 仅界定 · ${unc}/${total} 未引用`;
}

function itemsJoin(arr) {
  if (!arr || !arr.length) return "—";
  return arr.join("、");
}

function citationTermExtra(stats, term) {
  if (isDirectCitation(stats)) return "";
  return ` · 界定 ${itemsJoin(term.def_items)} · 脉络 ${itemsJoin(term.outline_items)}`;
}

function citationUnknownLine(stats, u) {
  if (isDirectCitation(stats)) return u.name;
  return `${u.name} · 界定 ${itemsJoin(u.def_items)} · 脉络 ${itemsJoin(u.outline_items)}`;
}

function detailMessage(error, fallback) {
  const d = error.response?.data?.detail;
  if (typeof d === "string") return d;
  return fallback;
}

function hasText(t) {
  return !!(t && String(t).trim());
}

const canExportSelect = computed(() => hasText(rawSelect.value));
const canExportPlain = computed(() => hasText(genResult.value?.plain?.text));
const canExportRef = computed(() => hasText(genResult.value?.ref?.text));
const canExportDetailSelect = computed(() => hasText(detail.value?.select_raw_output));
const canExportDetailPlain = computed(() => hasText(detail.value?.plain_result));
const canExportDetailRef = computed(() => hasText(detail.value?.ref_result));

const selectedNames = computed(() => new Set(selected.value.map((x) => x.name)));

const byTier = computed(() => {
  const out = { 最内在: [], 内在: [], 外在: [] };
  selected.value.forEach((item) => {
    const t = item.tier || item.tier_actual || "外在";
    if (out[t]) out[t].push(item);
    else out["外在"].push(item);
  });
  return out;
});

const selectedCount = computed(() => selected.value.length);
const innerShare = computed(() => {
  if (!selectedCount.value) return 0;
  const n = selected.value.filter((x) => x.tier === "内在" || x.tier === "最内在").length;
  return Math.round((1000 * n) / selectedCount.value) / 10;
});

const searchHits = computed(() => {
  const q = search.value.trim();
  if (!q || !meta.value?.terms) return [];
  return meta.value.terms.filter((t) => t.name.includes(q) && !selectedNames.value.has(t.name)).slice(0, 20);
});

const placeholdersOk = computed(() => {
  const c = meta.value?.placeholder_checks || {};
  return {
    select: checkLocal("select", selectPrompt.value),
    plain: checkLocal("plain", plainPrompt.value),
    ref: checkLocal("ref", refPrompt.value),
    server: c,
  };
});

function cacheTokensLine(usage) {
  if (!usage) return "";
  const parts = [];
  if (usage.cache_creation_input_tokens != null) parts.push(`cache_creation ${usage.cache_creation_input_tokens}`);
  if (usage.cache_read_input_tokens != null) parts.push(`cache_read ${usage.cache_read_input_tokens}`);
  if (usage.cache_creation_5m_tokens != null) parts.push(`cache_5m ${usage.cache_creation_5m_tokens}`);
  return parts.length ? `；缓存 tokens：${parts.join("／")}（不计费）` : "";
}

function checkLocal(kind, text) {
  const need = {
    select: ["{query}", "{LIST_ZUINEI}", "{LIST_NEI}", "{LIST_WAI}"],
    plain: ["{query}"],
    ref: ["{TERM_DEFS}", "{query}"],
  }[kind];
  const problems = [];
  need.forEach((token) => {
    const n = (text.match(new RegExp(token.replace(/[{}]/g, "\\$&"), "g")) || []).length;
    if (n === 0) problems.push(`缺少 ${token}`);
    if (n > 1) problems.push(`${token} 出现 ${n} 次`);
  });
  return { ok: problems.length === 0, problems };
}

async function loadMeta() {
  const headers = props.getAuthHeaders();
  if (!headers) return;
  loadingMeta.value = true;
  try {
    const res = await axios.get(`${props.api}/sc/meta`, { headers });
    meta.value = res.data;
    if (res.data.defaults) {
      selectPrompt.value = res.data.defaults.select_prompt || "";
      plainPrompt.value = res.data.defaults.plain_prompt || "";
      refPrompt.value = res.data.defaults.ref_prompt || "";
    }
    if (res.data.error) message.error(res.data.error);
  } catch (error) {
    message.error(detailMessage(error, "加载 SC meta 失败"));
  } finally {
    loadingMeta.value = false;
  }
}

async function loadHistory() {
  const headers = props.getAuthHeaders();
  if (!headers) return;
  try {
    const res = await axios.get(`${props.api}/sc/runs`, { headers });
    history.value = res.data.runs || [];
    historyCostSum.value = res.data.cost_sum_display || "—";
    historyCostCount.value = res.data.cost_counted_runs || 0;
  } catch (error) {
    message.error(detailMessage(error, "加载历史失败"));
  }
}

async function doSelect() {
  if (!topic.value.trim()) return message.warning("请填写篇题");
  if (!placeholdersOk.value.select.ok) return message.error(placeholdersOk.value.select.problems.join("；"));
  const headers = props.getAuthHeaders();
  if (!headers) return;
  selecting.value = true;
  try {
    const res = await axios.post(
      `${props.api}/sc/select`,
      { topic: topic.value.trim(), select_prompt: selectPrompt.value },
      { headers, timeout: 600000 }
    );
    selectRunId.value = res.data.run_id;
    rawSelect.value = res.data.raw_output || "";
    selectUsage.value = res.data.usage;
    selectCost.value = res.data.cost || null;
    selected.value = (res.data.items || []).map((it) => ({
      name: it.name,
      tier: it.tier_actual || it.tier_by_model,
      reason: it.reason || "",
      has_3a: !!it.has_3a,
      in_list: !!it.in_list,
      tier_mismatch: !!it.tier_mismatch,
    }));
    message.success(`选词完成：${selected.value.length} 个`);
  } catch (error) {
    message.error(detailMessage(error, "选词失败"));
  } finally {
    selecting.value = false;
  }
}

function removeTerm(name) {
  selected.value = selected.value.filter((x) => x.name !== name);
}

function addTerm(term) {
  if (selectedNames.value.has(term.name)) return;
  selected.value.push({
    name: term.name,
    tier: term.tier,
    reason: "",
    has_3a: !!term.has_3a,
    in_list: true,
    tier_mismatch: false,
  });
  search.value = "";
}

async function doGenerate(mode, forcePlain = false) {
  if (!topic.value.trim()) return message.warning("请填写篇题");
  if (!selected.value.length) return message.warning("请先确认选词名单");
  if (!placeholdersOk.value.ref.ok) return message.error("加词条定义版：" + placeholdersOk.value.ref.problems.join("；"));
  if (!placeholdersOk.value.plain.ok) return message.error("普通版：" + placeholdersOk.value.plain.problems.join("；"));
  const headers = props.getAuthHeaders();
  if (!headers) return;
  generating.value = true;
  try {
    const res = await axios.post(
      `${props.api}/sc/generate`,
      {
        topic: topic.value.trim(),
        final_terms: selected.value.map((x) => x.name),
        ref_prompt: refPrompt.value,
        plain_prompt: plainPrompt.value,
        mode,
        force_plain: forcePlain,
        select_run_id: selectRunId.value,
      },
      { headers, timeout: 600000 }
    );
    genResult.value = res.data;
    await loadHistory();
    if (res.data.plain?.status === "no_cache") message.info("普通版尚无存档");
    else message.success("生成完成");
  } catch (error) {
    message.error(detailMessage(error, "生成失败"));
  } finally {
    generating.value = false;
  }
}

async function openRun(id) {
  const headers = props.getAuthHeaders();
  if (!headers) return;
  try {
    const res = await axios.get(`${props.api}/sc/runs/${id}`, { headers });
    detail.value = res.data;
    detailCitation.value = null;
    try {
      const cite = await axios.get(`${props.api}/sc/runs/${id}/citation_stats`, { headers });
      detailCitation.value = cite.data;
    } catch (_) {
      detailCitation.value = { note: "引用统计加载失败" };
    }
  } catch (error) {
    message.error(detailMessage(error, "读取详情失败"));
  }
}

async function exportRun(id) {
  const headers = props.getAuthHeaders();
  if (!headers) return;
  try {
    const res = await axios.post(`${props.api}/sc/runs/${id}/export`, {}, { headers, responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = `SC_${id}.docx`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (error) {
    message.error(detailMessage(error, "导出失败"));
  }
}

function filenameFromDisposition(header, fallback) {
  if (!header) return fallback;
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (star) {
    try {
      return decodeURIComponent(star[1]);
    } catch (_) {
      /* ignore */
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain ? plain[1] : fallback;
}

async function exportKind(kind, topic, text) {
  if (!hasText(text)) return message.warning("没有可导出的文本");
  if (!hasText(topic)) return message.warning("请填写篇题");
  const headers = props.getAuthHeaders();
  if (!headers) return;
  exportWarn.value = "";
  try {
    const res = await axios.post(
      `${props.api}/sc/export_docx`,
      { kind, topic: topic.trim(), text },
      { headers, responseType: "blob", timeout: 120000 }
    );
    const warnRaw = res.headers["x-sc-export-warning"];
    if (warnRaw) {
      try {
        exportWarn.value = decodeURIComponent(warnRaw);
      } catch (_) {
        exportWarn.value = warnRaw;
      }
      message.warning(exportWarn.value);
    }
    const name = filenameFromDisposition(
      res.headers["content-disposition"],
      `${kind}.docx`
    );
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  } catch (error) {
    message.error(detailMessage(error, "导出失败"));
  }
}

onMounted(async () => {
  await loadMeta();
  await loadHistory();
});
</script>

<template>
  <div class="sc-page">
    <div v-if="meta?.warning" class="warn">{{ meta.warning }}</div>
    <div v-if="meta?.error" class="warn">{{ meta.error }}</div>
    <div v-if="exportWarn" class="warn">{{ exportWarn }}</div>
    <div v-if="meta?.mismatch && meta.mismatch.equal === false" class="warn">
      名单与 3a 名字集合不一致：仅名单 {{ meta.mismatch.only_tiers?.length || 0 }}，仅 3a {{ meta.mismatch.only_3a?.length || 0 }}。
      <details v-if="(meta.mismatch.only_tiers?.length || 0) + (meta.mismatch.only_3a?.length || 0) <= 40">
        <summary>差异</summary>
        <div>仅名单：{{ (meta.mismatch.only_tiers || []).join("、") || "无" }}</div>
        <div>仅 3a：{{ (meta.mismatch.only_3a || []).join("、") || "无" }}</div>
      </details>
    </div>

    <section class="block">
      <h3>1. 输入与选词</h3>
      <div v-if="meta?.tiers" class="stats">
        <span v-for="t in TIER_ORDER" :key="t">
          {{ t }} {{ meta.tiers[t]?.count }}（有 3a {{ meta.tiers[t]?.has_3a }} / {{ meta.tiers[t]?.has_pct }}%；无 {{ meta.tiers[t]?.null_3a }}）
        </span>
        <span>合计 {{ meta.total }}</span>
      </div>
      <label class="lbl">篇题</label>
      <input v-model="topic" class="inp" placeholder="输入篇题/主题" />
      <label class="lbl">选词提示词</label>
      <textarea v-model="selectPrompt" class="ta" rows="10" />
      <div class="meta-line" :class="{ bad: !placeholdersOk.select.ok }">
        占位符：{{ placeholdersOk.select.ok ? "通过" : placeholdersOk.select.problems.join("；") }}
      </div>
      <button type="button" class="btn btn-primary" :disabled="selecting || loadingMeta" @click="doSelect">
        {{ selecting ? "选词中…" : "选词" }}
      </button>
    </section>

    <section class="block">
      <h3>2. 选词结果（人工确认）</h3>
      <div class="meta-line">
        已选 {{ selectedCount }}；内在+最内在约占已选 {{ innerShare }}%（只提示）
      </div>
      <div v-if="selectCost" class="meta-line cost-line">
        本次选词费用 {{ selectCost.cost_display }}（输入 {{ selectCost.input_tokens ?? "—" }} tokens／输出 {{ selectCost.output_tokens ?? "—" }} tokens）{{ cacheTokensLine(selectUsage) }}
      </div>
      <div class="search-row">
        <input v-model="search" class="inp" placeholder="从 2381 词条中搜索添加" />
        <div v-if="searchHits.length" class="hits">
          <button v-for="hit in searchHits" :key="hit.name" type="button" class="hit" @click="addTerm(hit)">
            〔{{ hit.tier }}〕{{ hit.name }} {{ hit.has_3a ? "有3a" : "无3a" }}
          </button>
        </div>
      </div>
      <div class="tiers">
        <div v-for="t in TIER_ORDER" :key="t" class="tier-col">
          <h4>{{ t }}（{{ byTier[t].length }}）</h4>
          <div v-for="item in byTier[t]" :key="item.name" class="term" :class="{ bad: !item.in_list }">
            <div class="term-top">
              <strong>{{ item.name }}</strong>
              <span class="tag" :class="item.has_3a ? 'ok' : 'miss'">{{ item.has_3a ? "有3a" : "无3a" }}</span>
              <span v-if="item.tier_mismatch" class="tag miss">档次已按名单校正</span>
              <button type="button" class="link" @click="removeTerm(item.name)">删除</button>
            </div>
            <div class="reason">{{ item.reason || "（无依据）" }}</div>
          </div>
        </div>
      </div>
      <details v-if="rawSelect">
        <summary>模型原始输出</summary>
        <pre class="pre">{{ rawSelect }}</pre>
      </details>
      <div class="btns">
        <button
          type="button"
          class="btn"
          :disabled="!canExportSelect"
          @click="exportKind('select', topic, rawSelect)"
        >
          导出选词结果 docx
        </button>
      </div>
    </section>

    <section class="block">
      <h3>3. 生成</h3>
      <label class="lbl">普通版提示词</label>
      <div class="meta-line">默认：直写普通版（v3）</div>
      <textarea v-model="plainPrompt" class="ta" rows="8" />
      <div class="meta-line" :class="{ bad: !placeholdersOk.plain.ok }">
        占位符：{{ placeholdersOk.plain.ok ? "通过" : placeholdersOk.plain.problems.join("；") }}
      </div>
      <label class="lbl">加词条定义版提示词</label>
      <div class="meta-line">默认：直写版（v3）</div>
      <textarea v-model="refPrompt" class="ta" rows="8" />
      <div class="meta-line" :class="{ bad: !placeholdersOk.ref.ok }">
        占位符：{{ placeholdersOk.ref.ok ? "通过" : placeholdersOk.ref.problems.join("；") }}
      </div>
      <div class="btns">
        <button type="button" class="btn btn-primary" :disabled="generating" @click="doGenerate('ref')">
          确认并生成
        </button>
        <button type="button" class="btn" :disabled="generating" @click="doGenerate('ref_and_plain_parallel')">
          并行对比
        </button>
        <button type="button" class="btn" :disabled="generating" @click="doGenerate('plain_only', true)">
          重跑普通版
        </button>
        <button
          v-if="genResult?.plain?.status === 'no_cache'"
          type="button"
          class="btn"
          :disabled="generating"
          @click="doGenerate('plain_only', false)"
        >
          先跑普通版
        </button>
      </div>

      <div v-if="genResult" class="results">
        <div class="meta-line">
          送入 {{ genResult.defs_sent_count ?? "—" }} 个 3a 鸟瞰；
          定义字数 {{ genResult.defs_chars }}；
          跳过：{{ (genResult.skipped || []).join("、") || "无" }}；
          合并：{{ (genResult.merged || []).join("、") || "无" }}
        </div>
        <div v-if="genResult.cost" class="meta-line cost-line">
          本次合计 {{ genResult.cost.total_display }}
        </div>
        <div class="cols">
          <div class="col">
            <h4>
              普通版
              <span v-if="genResult.plain?.from_cache" class="tag ok">存档于 {{ genResult.plain.cache_created_at }}</span>
              <span v-else-if="genResult.plain?.status === 'no_cache'" class="tag miss">尚无存档</span>
            </h4>
            <div class="meta-line">
              token：{{ genResult.plain?.usage?.input_tokens ?? "—" }} / {{ genResult.plain?.usage?.output_tokens ?? "—" }}
              <template v-if="genResult.plain?.from_cache">
                ；费用 $0.000（{{ genResult.plain.cost_note || "存档，未产生费用" }}）
              </template>
              <template v-else-if="genResult.plain?.cost">
                ；费用 {{ genResult.plain.cost.cost_display }}
              </template>
              <template v-else>；费用 —</template>
              {{ cacheTokensLine(genResult.plain?.usage) }}
            </div>
            <button
              type="button"
              class="btn"
              :disabled="!canExportPlain"
              @click="exportKind('plain', topic, genResult.plain?.text || '')"
            >
              导出普通版-负担说明 docx
            </button>
            <pre class="pre">{{ genResult.plain?.text || "（无）" }}</pre>
          </div>
          <div class="col">
            <h4>加词条定义版</h4>
            <div class="meta-line">
              token：{{ genResult.ref?.usage?.input_tokens ?? "—" }} / {{ genResult.ref?.usage?.output_tokens ?? "—" }}
              <template v-if="genResult.ref?.cost">；费用 {{ genResult.ref.cost.cost_display }}</template>
              <template v-else>；费用 —</template>
              {{ cacheTokensLine(genResult.ref?.usage) }}
            </div>
            <button
              type="button"
              class="btn"
              :disabled="!canExportRef"
              @click="exportKind('ref', topic, genResult.ref?.text || '')"
            >
              导出加词条定义版-负担说明 docx
            </button>
            <div v-if="genResult.citation_stats" class="cite-box">
              <div class="cite-title">引用统计</div>
              <div v-if="genResult.citation_stats.format_note" class="meta-line">{{ genResult.citation_stats.format_note }}</div>
              <div v-if="genResult.citation_stats.note" class="meta-line">{{ genResult.citation_stats.note }}</div>
              <template v-if="!genResult.citation_stats.note">
                <div v-for="t in TIER_ORDER" :key="'g-' + t" class="meta-line">
                  {{ citationSummaryLine(genResult.citation_stats, t) }}
                </div>
                <div class="meta-line cost-line">{{ citationTotalLine(genResult.citation_stats) }}</div>
                <details>
                  <summary>逐词清单</summary>
                  <div
                    v-for="term in genResult.citation_stats.terms || []"
                    :key="'gt-' + term.name"
                    class="cite-term"
                  >
                    〔{{ term.tier }}〕{{ term.name }} · {{ term.status_label || STATUS_LABEL[term.status] || term.status }}{{ citationTermExtra(genResult.citation_stats, term) }}
                  </div>
                </details>
                <div v-if="(genResult.citation_stats.unknown_cited || []).length" class="cite-unknown">
                  <div class="cite-title">引用了未选词条</div>
                  <div v-for="u in genResult.citation_stats.unknown_cited" :key="'gu-' + u.name" class="cite-term">
                    {{ citationUnknownLine(genResult.citation_stats, u) }}
                  </div>
                </div>
              </template>
            </div>
            <pre class="pre">{{ genResult.ref?.text || "（无）" }}</pre>
          </div>
        </div>
      </div>
    </section>

    <section class="block">
      <h3>4. 历史与导出</h3>
      <div class="meta-line cost-line">累计 {{ historyCostSum }}（共 {{ historyCostCount }} 次运行）</div>
      <ul class="hist">
        <li v-for="run in history" :key="run.id">
          <button type="button" class="link" @click="openRun(run.id)">
            #{{ run.id }} · {{ run.created_at }} · {{ run.topic }} · {{ run.final_term_count }} 词 · 费用 {{ run.cost_total_display || "—" }}
          </button>
          <button type="button" class="btn" @click="exportRun(run.id)">导出 docx</button>
        </li>
      </ul>
      <div v-if="detail" class="detail">
        <h4>详情 #{{ detail.id }}</h4>
        <div class="btns">
          <button
            type="button"
            class="btn"
            :disabled="!canExportDetailSelect"
            @click="exportKind('select', detail.topic, detail.select_raw_output || '')"
          >
            导出选词结果 docx
          </button>
          <button
            type="button"
            class="btn"
            :disabled="!canExportDetailPlain"
            @click="exportKind('plain', detail.topic, detail.plain_result || '')"
          >
            导出普通版-负担说明 docx
          </button>
          <button
            type="button"
            class="btn"
            :disabled="!canExportDetailRef"
            @click="exportKind('ref', detail.topic, detail.ref_result || '')"
          >
            导出加词条定义版-负担说明 docx
          </button>
        </div>
        <div v-if="detailCitation" class="cite-box">
          <div class="cite-title">引用统计</div>
          <div v-if="detailCitation.format_note" class="meta-line">{{ detailCitation.format_note }}</div>
          <div v-if="detailCitation.note" class="meta-line">{{ detailCitation.note }}</div>
          <template v-if="!detailCitation.note">
            <div v-for="t in TIER_ORDER" :key="'d-' + t" class="meta-line">
              {{ citationSummaryLine(detailCitation, t) }}
            </div>
            <div class="meta-line cost-line">{{ citationTotalLine(detailCitation) }}</div>
            <details>
              <summary>逐词清单</summary>
              <div v-for="term in detailCitation.terms || []" :key="'dt-' + term.name" class="cite-term">
                〔{{ term.tier }}〕{{ term.name }} · {{ term.status_label || STATUS_LABEL[term.status] || term.status }}{{ citationTermExtra(detailCitation, term) }}
              </div>
            </details>
            <div v-if="(detailCitation.unknown_cited || []).length" class="cite-unknown">
              <div class="cite-title">引用了未选词条</div>
              <div v-for="u in detailCitation.unknown_cited" :key="'du-' + u.name" class="cite-term">
                {{ citationUnknownLine(detailCitation, u) }}
              </div>
            </div>
          </template>
        </div>
        <pre class="pre">{{ JSON.stringify(detail, null, 2) }}</pre>
      </div>
    </section>
  </div>
</template>

<style scoped>
.sc-page { display: flex; flex-direction: column; gap: 16px; }
.block { background: #fff; border: 1px solid #e5e5e5; border-radius: 8px; padding: 14px 16px; }
.warn { background: #fff7e6; border: 1px solid #ffd591; color: #ad6800; padding: 10px 12px; border-radius: 6px; }
.stats { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 10px; color: #555; font-size: 13px; }
.lbl { display: block; margin: 8px 0 4px; font-weight: 600; }
.inp, .ta { width: 100%; border: 1px solid #d9d9d9; border-radius: 6px; padding: 8px 10px; font: inherit; }
.ta { font-family: ui-monospace, Consolas, monospace; font-size: 12px; }
.meta-line { margin: 6px 0; font-size: 13px; color: #666; }
.meta-line.bad { color: #cf1322; }
.cost-line { color: #0958d9; }
.btn { border: 1px solid #d9d9d9; background: #fff; border-radius: 6px; padding: 6px 12px; cursor: pointer; }
.btn-primary { background: #1677ff; color: #fff; border-color: #1677ff; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btns { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.tiers { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.tier-col { border: 1px solid #eee; border-radius: 6px; padding: 8px; min-height: 80px; }
.term { border-bottom: 1px solid #f0f0f0; padding: 6px 0; }
.term.bad { background: #fff1f0; }
.term-top { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.reason { color: #666; font-size: 12px; margin-top: 2px; }
.tag { font-size: 12px; padding: 1px 6px; border-radius: 4px; background: #f5f5f5; }
.tag.ok { background: #f6ffed; color: #389e0d; }
.tag.miss { background: #fff1f0; color: #cf1322; }
.link { border: none; background: none; color: #1677ff; cursor: pointer; padding: 0; }
.hits { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.hit { border: 1px solid #d9d9d9; background: #fafafa; border-radius: 4px; padding: 2px 8px; cursor: pointer; font-size: 12px; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.pre { white-space: pre-wrap; background: #fafafa; border: 1px solid #eee; border-radius: 6px; padding: 8px; max-height: 420px; overflow: auto; font-size: 12px; }
.hist { list-style: none; padding: 0; margin: 0; }
.hist li { display: flex; gap: 10px; align-items: center; padding: 6px 0; border-bottom: 1px solid #f0f0f0; }
.cite-box { margin: 8px 0; padding: 8px 10px; background: #fafafa; border: 1px solid #eee; border-radius: 6px; font-size: 13px; }
.cite-title { font-weight: 600; margin-bottom: 4px; }
.cite-term { padding: 2px 0; color: #444; }
.cite-unknown { margin-top: 8px; padding: 8px; background: #fffbe6; border: 1px solid #ffe58f; border-radius: 4px; }
@media (max-width: 900px) {
  .tiers, .cols { grid-template-columns: 1fr; }
}
</style>

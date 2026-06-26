<script setup>
import { ref, computed, nextTick } from "vue";
import axios from "axios";
import { message } from "ant-design-vue";
import { LoadingOutlined } from "@ant-design/icons-vue";
import ToolsHeader from "@/components/toolbox/ToolsHeader.vue";
import { toastWarning } from "@/components/utils/Dialog.js";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";

const NATURE_OPTIONS = [
  { label: "一般性", value: "一般性" },
  { label: "真理启示", value: "真理启示" },
  { label: "生命经历", value: "生命经历" },
  { label: "实行应用", value: "实行应用" },
];

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

const outlineTopic = ref("");
const outlineNature = ref("一般性");
const burdenDescription = ref("");
const outlineText = ref("");

const evalLoading = ref(false);
const evalResult = ref(null);
const editableAnswer = ref("");
const outlineEditing = ref(false);
const outlineEditVisible = ref(false);
const outlineEditReadonly = ref(false);
const scriptureReplacementItems = ref([]);
const hadBurdenOnEval = ref(false);

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
  const dims = ["F2", "F4", "T1", "T2", "T3", "T4"];
  return dims
    .map((dim) => {
      let block = evalResult.value?.[dim];
      if (!block && dim.startsWith("F")) block = evalPansaiLayer.value?.[dim];
      if (!block && dim.startsWith("T")) block = evalTheologyLayer.value?.[dim];
      return { dim, note: block?.improvement_note };
    })
    .filter((x) => x.note != null && String(x.note).trim());
});

function tip(msg) {
  toastWarning(msg);
}

function formatSubScore(score) {
  if (score == null || score === "" || Number.isNaN(Number(score))) return "—/10";
  const n = Number(score);
  const rounded = Math.round(n * 10) / 10;
  const display = Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
  return `${display}/10`;
}

function formatScore10(value, divisor = 1) {
  if (value == null || value === "" || Number.isNaN(Number(value))) return "—/10";
  const n = Number(value) / divisor;
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

function evalFScore10(key) {
  const block = evalPansaiLayer.value?.[key] ?? evalResult.value?.[key];
  if (!block || block.error || block.score == null) return "—/10";
  return formatScore10(block.score, 0.5);
}

function evalHasBlock(key) {
  const block = key.startsWith("T")
    ? evalTheologyLayer.value?.[key]
    : evalPansaiLayer.value?.[key] ?? evalResult.value?.[key];
  return block && !block.error;
}

function extractVerseRef(text) {
  const s = String(text || "").trim();
  if (!s) return "";
  const m = s.match(/[\u4e00-\u9fff]{1,8}[\d一二三四五六七八九十百千两〇零]+[\d:：\-—]*\d*/);
  if (m) return m[0];
  return s.split(/[「『《"\s(（]/)[0] || s;
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
  const base = editableAnswer.value || outlineText.value || "";
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
  outlineText.value = next;
  item.decided = true;
  item.accepted = true;
}

function rejectScriptureReplacement(index) {
  const item = scriptureReplacementItems.value[index];
  if (!item || item.decided) return;
  item.decided = true;
  item.accepted = false;
}

function buildEvalPayload(overrides = {}) {
  return {
    answer: editableAnswer.value || outlineText.value,
    query: outlineTopic.value.trim(),
    outline_nature: outlineNature.value,
    burden_description: burdenDescription.value.trim(),
    revelation: [],
    experience: [],
    practice: [],
    skeleton: [],
    ...overrides,
  };
}

async function runOutlineEval() {
  const answerText = outlineText.value;
  if (!outlineTopic.value.trim()) {
    tip("请填写主题");
    return;
  }
  if (!outlineNature.value) {
    tip("请选择纲目性质");
    return;
  }
  if (!answerText?.trim()) {
    tip("请填写纲目正文");
    return;
  }

  evalLoading.value = true;
  try {
    const token = localStorage.getItem("token");
    if (token) axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;
    const payload = buildEvalPayload({ answer: outlineText.value.trim() });
    const res = await axios.post("/api/eval/outline", payload, { timeout: 600000 });
    evalResult.value = res.data;
    editableAnswer.value = outlineText.value.trim();
    scriptureReplacementItems.value = [];
    hadBurdenOnEval.value = !!burdenDescription.value.trim();

    const suggestions = res.data?.scripture_suggestions || [];
    if (suggestions.length > 0) {
      scriptureReplacementItems.value = formatScriptureReplacementItems(suggestions);
    }

    message.success("纲目评估完成");
  } catch (e) {
    const detail = e?.response?.data?.detail || e?.message || "评估失败";
    tip(typeof detail === "string" ? detail : JSON.stringify(detail));
  } finally {
    evalLoading.value = false;
  }
}

function toggleOutlineEdit() {
  if (outlineEditing.value) {
    outlineEditing.value = false;
    outlineEditReadonly.value = true;
    outlineText.value = editableAnswer.value;
    return;
  }
  outlineEditVisible.value = true;
  outlineEditing.value = true;
  outlineEditReadonly.value = false;
  editableAnswer.value = editableAnswer.value || outlineText.value;
  nextTick(() => {
    document.getElementById("toolbox-outline-edit-textarea")?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
  });
}

function doDownload(data) {
  if (!data.docx_base64) return;
  const bin = Uint8Array.from(atob(data.docx_base64), (c) => c.charCodeAt(0));
  const blob = new Blob([bin], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = data.filename || "outline_zh.docx";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function downloadEvalDocx() {
  const text = editableAnswer.value;
  if (!text?.trim()) {
    tip("请先完成纲目评估");
    return;
  }
  const title = outlineTopic.value.trim();
  const fullText = title ? `${title}\n\n${text}` : text;
  const token = localStorage.getItem("token");
  if (!token) {
    window.location.hash = "/login";
    return;
  }
  try {
    const res = await fetch(`${apiBase}/api/ai_search/format_outline_only`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ direction: "en2zh", translated_text: fullText, output_format: "docx" }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      tip((data.detail || data.error) || "格式化失败");
      return;
    }
    doDownload(data);
    message.success("下载完成");
  } catch (e) {
    tip(e?.message || "下载失败");
  }
}
</script>

<template>
  <ToolsHeader title="纲目品质评估" />

  <div class="page-wrap">
    <div class="form-card">
      <div class="form-row">
        <label class="form-label required">主题</label>
        <a-input v-model:value="outlineTopic" placeholder="纲目主题" />
      </div>
      <div class="form-row">
        <label class="form-label required">纲目性质</label>
        <a-select v-model:value="outlineNature" style="width: 100%">
          <a-select-option v-for="opt in NATURE_OPTIONS" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </a-select-option>
        </a-select>
      </div>
      <div class="form-row">
        <label class="form-label">负担说明</label>
        <a-input
          v-model:value="burdenDescription"
          placeholder="若有负担说明可填入，将提升 F2 评估准确度"
        />
        <span class="form-hint">选填，有则更准确</span>
      </div>
      <div class="form-row">
        <label class="form-label required">纲目正文</label>
        <a-textarea
          v-model:value="outlineText"
          placeholder="请粘贴纲目正文"
          :auto-size="{ minRows: 10, maxRows: 24 }"
        />
      </div>
      <div class="form-actions">
        <a-button type="primary" :loading="evalLoading" :disabled="evalLoading" @click="() => runOutlineEval()">
          <LoadingOutlined v-if="evalLoading" spin />
          {{ evalLoading ? "评估中…" : "评估纲目" }}
        </a-button>
        <span class="eval-hint-text">评估约需 25-35 秒</span>
        <span v-if="evalResult && !evalLoading" class="eval-stats">
          耗时 {{ (evalResult.elapsed_ms / 1000).toFixed(1) }}s · 费用 ${{ Number(evalResult.cost_usd).toFixed(4) }}
        </span>
      </div>
    </div>

    <div v-if="evalResult" class="eval-report">
      <div v-if="evalImprovementEntries.length" class="eval-improvement-banner">
        <div class="eval-improvement-title">相较上轮改善说明</div>
        <div v-for="entry in evalImprovementEntries" :key="entry.dim" class="eval-improvement-item">
          <strong>{{ entry.dim }}</strong>：{{ entry.note }}
        </div>
      </div>
      <div v-if="scriptureReplacementItems.length" class="eval-scripture-auto-banner">
        发现 {{ scriptureReplacementItems.length }} 处经文建议，请在下方逐条确认
      </div>

      <div class="eval-total-score-card">
        <div class="eval-total-score-label">综合得分</div>
        <div class="eval-total-score-value">
          {{ evalResult.total_score ?? "—" }}<span class="eval-total-score-unit"> / 100</span>
        </div>
      </div>

      <div v-if="evalHasBlock('F4')" class="eval-section-block">
        <div class="eval-section-title-row">
          <div class="eval-section-title">逻辑连贯性参考</div>
          <span class="eval-section-hint">不计入综合分</span>
        </div>
        <div class="eval-dim-card">
          <div class="eval-dim-header">
            <strong>F4 逻辑连贯性</strong>
            <span class="eval-dim-score">{{ evalFScore10("F4") }}</span>
          </div>
          <div class="eval-comment">{{ evalPansaiLayer.F4.comment }}</div>
          <div v-if="evalPansaiLayer.F4.prescription" class="eval-prescription">
            ⚠ {{ evalPansaiLayer.F4.prescription }}
          </div>
          <div v-if="evalPansaiLayer.F4?.improvement_note" class="eval-improvement-note">
            改善：{{ evalPansaiLayer.F4.improvement_note }}
          </div>
        </div>
      </div>

      <div v-if="hadBurdenOnEval && evalHasBlock('F2')" class="eval-section-block">
        <div class="eval-section-title-row">
          <div class="eval-section-title">负担吻合度参考</div>
          <span class="eval-section-hint">不计入综合分</span>
        </div>
        <div class="eval-dim-card">
          <div class="eval-dim-header">
            <strong>F2 负担吻合度</strong>
            <span class="eval-dim-score">{{ evalFScore10("F2") }}</span>
          </div>
          <div class="eval-comment">{{ evalPansaiLayer.F2.comment }}</div>
          <div v-if="evalPansaiLayer.F2.prescription" class="eval-prescription">
            ⚠ {{ evalPansaiLayer.F2.prescription }}
          </div>
          <div v-if="evalPansaiLayer.F2?.improvement_note" class="eval-improvement-note">
            改善：{{ evalPansaiLayer.F2.improvement_note }}
          </div>
        </div>
      </div>

      <div class="eval-section-block">
        <div class="eval-section-title">神学深度层</div>

        <div class="eval-dim-card">
          <div class="eval-dim-header"><strong>T1 经文校对</strong><span>{{ evalT1Score10 }}/10</span></div>
          <div v-if="evalT1?.error" class="eval-error">{{ evalT1.error }}</div>
          <template v-if="evalHasBlock('T1')">
            <div class="eval-meta-tags">
              <a-tag v-if="evalT1.apex_level">{{ evalT1.apex_level }}</a-tag>
            </div>
            <div v-for="layer in T1_L_META" :key="layer.key" class="eval-sub-dim-block">
              <div class="eval-sub-dim-header">
                <span class="eval-sub-dim-label">{{ layer.label }}</span>
                <span class="eval-sub-dim-score">{{ formatSubScore(evalT1[layer.key]?.score) }}</span>
              </div>
              <div v-if="evalT1[layer.key]?.comment" class="eval-sub-dim-comment">
                「{{ evalT1[layer.key].comment }}」
              </div>
              <div v-if="evalGapText(evalT1[layer.key]?.gap)" class="eval-sub-dim-gap">
                ⚠ {{ evalGapText(evalT1[layer.key].gap) }}
              </div>
            </div>
            <div
              v-if="evalT1.progression != null || evalT1.density != null"
              class="eval-extra-metrics"
            >
              <span v-if="evalT1.progression != null">层次递进性 {{ formatSubScore(evalT1.progression) }}</span>
              <span v-if="evalT1.progression != null && evalT1.density != null"> · </span>
              <span v-if="evalT1.density != null">经文密度 {{ formatSubScore(evalT1.density) }}</span>
            </div>
            <div
              v-if="evalT1.nature_fit"
              class="nature-fit"
              :class="evalT1.nature_fit?.fit ? 'fit-ok' : 'fit-warn'"
            >
              经文风格与纲目性质：
              {{ evalT1.nature_fit?.fit ? "✓ 吻合" : "⚠ 偏差" }}
              <span v-if="evalT1.nature_fit?.note">— {{ evalT1.nature_fit.note }}</span>
            </div>
            <div v-if="evalT1.summary" class="eval-comment eval-summary-line">
              总结：{{ evalT1.summary }}
            </div>
          </template>
        </div>

        <div class="eval-dim-card">
          <div class="eval-dim-header"><strong>T2 黄金路径</strong><span>{{ evalT2Score10 }}/10</span></div>
          <div v-if="evalT2?.error" class="eval-error">{{ evalT2.error }}</div>
          <template v-if="evalHasBlock('T2')">
            <div v-for="item in T2_S_META" :key="item.key" class="eval-sub-item">
              <span class="sub-label">{{ item.label }}</span>
              <span class="sub-score">{{ evalT2[item.key]?.score ?? "-" }}/10</span>
              <p class="sub-comment">{{ evalT2[item.key]?.comment }}</p>
              <p v-if="evalT2[item.key]?.gap" class="sub-gap">⚠ {{ evalT2[item.key].gap }}</p>
            </div>
            <div class="eval-extra-metrics">
              加权总分：{{ evalT2.weighted_score ?? "-" }} / 100
            </div>
            <div v-if="evalT2.summary" class="eval-comment eval-summary-line">
              总结：{{ evalT2.summary }}
            </div>
          </template>
        </div>

        <div class="eval-dim-card">
          <div class="eval-dim-header"><strong>T3 四维分析</strong><span>{{ evalT3Score10 }}/10</span></div>
          <div v-if="evalT3?.error" class="eval-error">{{ evalT3.error }}</div>
          <template v-if="evalHasBlock('T3')">
            <div class="eval-meta-tags">
              <span class="framework-badge">{{ frameworkTypeLabel }}</span>
            </div>
            <div v-for="item in evalT3Meta" :key="item.key" class="eval-sub-item">
              <span class="sub-label">{{ item.label }}</span>
              <span class="sub-score">{{ evalT3[item.key]?.score ?? "-" }}/10</span>
              <p class="sub-comment">{{ evalT3[item.key]?.comment }}</p>
              <p v-if="evalT3[item.key]?.gap" class="sub-gap">⚠ {{ evalT3[item.key].gap }}</p>
            </div>
            <div class="eval-extra-metrics">
              <span>有机连贯度：{{ evalT3.coherence ?? "-" }}/10</span>
              <span> · </span>
              <span>结构张力度：{{ evalT3.structural_tension ?? "-" }}/10</span>
            </div>
            <div v-if="evalT3.summary" class="eval-comment eval-summary-line">
              总结：{{ evalT3.summary }}
            </div>
          </template>
        </div>

        <div class="eval-card" id="eval-t4">
          <div class="card-header">
            <span class="card-title">T4 纲目冲击力</span>
            <span class="card-score">{{ evalT4Score10 }}/10</span>
          </div>
          <template v-if="evalHasBlock('T4')">
            <div class="sharpness-type">
              {{ evalT4.sharpness_type ?? "" }}
            </div>
            <p class="t4-comment">{{ evalT4.comment }}</p>
            <div v-if="evalT4.supply_paragraph" class="t4-supply">
              {{ evalT4.supply_paragraph }}
            </div>
          </template>
          <div v-else-if="evalT4?.error" class="eval-error">{{ evalT4.error }}</div>
        </div>
      </div>

      <div v-if="scriptureReplacementItems.length" class="scripture-review-section">
        <div class="section-title">经文修改建议</div>
        <div
          v-for="(item, index) in scriptureReplacementItems"
          :key="index"
          class="scripture-card"
          :class="{ decided: item.decided }"
        >
          <div class="scripture-location">{{ item.location }}</div>
          <div v-if="item.original_text" class="scripture-original">
            <span class="original-label">原文</span>
            <p class="original-content">
              {{ item.original_text }}
            </p>
          </div>
          <div class="scripture-row">
            <span class="label">原经文</span>
            <span class="verse">{{ item.current_verse }}</span>
          </div>
          <div class="scripture-row">
            <span class="label">建议替换</span>
            <span class="verse suggest">{{ item.ai_suggestion }}</span>
          </div>
          <div class="scripture-reason">{{ item.reason }}</div>
          <div v-if="!item.decided" class="scripture-actions">
            <button
              class="btn-accept"
              @click="acceptScriptureReplacement(index)"
            >替换</button>
            <button
              class="btn-reject"
              @click="rejectScriptureReplacement(index)"
            >保留</button>
          </div>
          <div v-else class="scripture-decided">
            {{ item.accepted ? "✓ 已替换" : "— 已保留" }}
          </div>
        </div>
      </div>

      <div v-if="evalSynthesis.overall_note" class="synthesis-section">
        <div class="synthesis-header">
          <span class="synthesis-title">纲目修改建议</span>
          <span class="synthesis-note">{{ evalSynthesis.overall_note }}</span>
        </div>

        <div v-if="evalSynthesis.high_priority?.length" class="priority-group">
          <div class="priority-label high">需要修改</div>
          <div
            v-for="(item, i) in evalSynthesis.high_priority"
            :key="'h' + i"
            class="suggestion-card high"
          >
            <div class="suggestion-problem">{{ item.problem }}</div>
            <div class="suggestion-body">{{ item.suggestion }}</div>
            <div class="suggestion-source">来源：{{ item.source }}</div>
          </div>
        </div>

        <div v-if="evalSynthesis.low_priority?.length" class="priority-group">
          <div class="priority-label low">可以改善</div>
          <div
            v-for="(item, i) in evalSynthesis.low_priority"
            :key="'l' + i"
            class="suggestion-card low"
          >
            <div class="suggestion-problem">{{ item.problem }}</div>
            <div class="suggestion-body">{{ item.suggestion }}</div>
            <div class="suggestion-source">来源：{{ item.source }}</div>
          </div>
        </div>
      </div>

      <div class="eval-bottom-actions">
        <a-button @click="toggleOutlineEdit">{{ outlineEditing ? "修改完成" : "修改纲目" }}</a-button>
        <button
          class="btn-download-docx"
          :disabled="!editableAnswer"
          @click="downloadEvalDocx"
        >刷格式下载</button>
      </div>
      <div v-if="outlineEditVisible" class="outline-edit-wrap">
        <a-textarea
          id="toolbox-outline-edit-textarea"
          v-model:value="editableAnswer"
          :readonly="outlineEditReadonly"
          :auto-size="{ minRows: 12, maxRows: 28 }"
          class="outline-edit-textarea"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-wrap {
  max-width: 900px;
  margin: 0 auto;
  padding: 0 16px 48px;
}
.form-card {
  background: #fff;
  border: 1px solid #e8ecf7;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 24px;
}
.form-row {
  margin-bottom: 16px;
}
.form-label {
  display: block;
  font-weight: 600;
  margin-bottom: 6px;
  color: #333;
}
.form-label.required::after {
  content: " *";
  color: #c41e3a;
}
.form-hint {
  display: block;
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}
.form-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 8px;
}
.eval-hint-text {
  font-size: 13px;
  color: #888;
}
.eval-stats {
  color: #666;
  font-size: 13px;
}
.eval-report {
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
.eval-section-title-row {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.eval-section-title {
  font-size: 15px;
  font-weight: 700;
  color: #4c5fd7;
  margin-bottom: 12px;
}
.eval-section-title-row .eval-section-title {
  margin-bottom: 0;
}
.eval-section-hint {
  font-size: 12px;
  font-weight: 400;
  color: #999;
}
.eval-total-score-card {
  background: linear-gradient(135deg, #667eea12 0%, #764ba212 100%);
  border: 2px solid #667eea;
  border-radius: 12px;
  padding: 16px 20px;
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
  line-height: 1.6;
}
.eval-improvement-banner {
  background: #fffbe6;
  border: 1px solid #ffe58f;
  border-radius: 8px;
  padding: 12px;
  font-size: 13px;
}
.eval-improvement-title {
  font-weight: 600;
  margin-bottom: 6px;
}
.eval-improvement-item {
  margin-top: 4px;
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
.eval-prescription {
  font-size: 14px;
  line-height: 1.7;
  color: #444;
  margin-top: 6px;
}
.eval-prescription {
  color: #c05621;
  font-weight: 500;
}
.eval-improvement-note {
  margin-top: 6px;
  font-size: 13px;
  color: #ad6800;
  background: #fffbe6;
  padding: 6px 8px;
  border-radius: 4px;
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
}
.eval-extra-metrics {
  font-size: 13px;
  color: #666;
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid #eef1f8;
}
.nature-fit {
  font-size: 13px;
  margin-top: 10px;
  padding: 8px 10px;
  border-radius: 6px;
}
.nature-fit.fit-ok {
  background: #f6ffed;
  color: #237804;
  border: 1px solid #b7eb8f;
}
.nature-fit.fit-warn {
  background: #fff7e6;
  color: #ad6800;
  border: 1px solid #ffd591;
}
.eval-sub-item {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed #eef1f8;
}
.eval-sub-item:first-of-type {
  border-top: none;
  padding-top: 0;
}
.sub-label {
  font-size: 13px;
  font-weight: 600;
  color: #333;
  margin-right: 8px;
}
.sub-score {
  font-size: 13px;
  color: #667eea;
  font-weight: 600;
}
.sub-comment,
.sub-gap {
  font-size: 13px;
  line-height: 1.7;
  color: #555;
  margin: 4px 0 0;
}
.sub-gap {
  color: #c05621;
}
.framework-badge {
  display: inline-block;
  font-size: 12px;
  font-weight: 600;
  color: #4c5fd7;
  background: #eef1ff;
  border: 1px solid #c7d0f7;
  border-radius: 4px;
  padding: 2px 8px;
}
.eval-card {
  background: #fff;
  border: 1px solid #eef1f8;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 10px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.card-title {
  font-weight: 700;
  color: #333;
}
.card-score {
  color: #667eea;
  font-weight: 600;
}
.sharpness-type {
  font-size: 13px;
  font-weight: 600;
  color: #4c5fd7;
  margin-bottom: 6px;
}
.t4-comment {
  font-size: 13px;
  line-height: 1.7;
  color: #666;
  margin: 6px 0 0;
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
.eval-summary-line {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid #eef1f8;
  font-weight: 500;
}
.eval-error {
  color: #c41e3a;
  font-size: 13px;
}
.eval-meta-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.eval-bottom-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
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
.outline-edit-wrap {
  margin-top: 12px;
}
.outline-edit-textarea {
  font-family: inherit;
  line-height: 24px;
}
.synthesis-section {
  background: #fafbff;
  border: 1px solid #e8ecf7;
  border-radius: 10px;
  padding: 14px 16px;
}
.synthesis-header {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
}
.synthesis-title {
  font-size: 15px;
  font-weight: 700;
  color: #4c5fd7;
}
.synthesis-note {
  font-size: 13px;
  color: #666;
}
.priority-group {
  margin-top: 10px;
}
.priority-label {
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 8px;
}
.priority-label.high {
  color: #c41e3a;
}
.priority-label.low {
  color: #ad6800;
}
.suggestion-card {
  background: #fff;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
  border-left: 3px solid #ccc;
}
.suggestion-card.high {
  border-left-color: #c41e3a;
}
.suggestion-card.low {
  border-left-color: #faad14;
}
.suggestion-problem {
  font-weight: 600;
  font-size: 14px;
  color: #333;
  margin-bottom: 4px;
}
.suggestion-body {
  font-size: 13px;
  line-height: 1.7;
  color: #444;
}
.suggestion-source {
  font-size: 12px;
  color: #999;
  margin-top: 6px;
}
.scripture-review-section {
  background: #fafbff;
  border: 1px solid #e8ecf7;
  border-radius: 10px;
  padding: 14px 16px;
}
.scripture-review-section .section-title {
  font-size: 15px;
  font-weight: 700;
  color: #4c5fd7;
  margin-bottom: 12px;
}
.scripture-card {
  background: #fff;
  border: 1px solid #eef1f8;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 10px;
}
.scripture-card.decided {
  opacity: 0.75;
}
.scripture-location {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 8px;
  color: #333;
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
.scripture-row {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 13px;
  line-height: 1.6;
}
.scripture-row .label {
  flex-shrink: 0;
  color: #888;
  min-width: 56px;
}
.scripture-row .verse {
  color: #333;
}
.scripture-row .verse.suggest {
  color: #237804;
  font-weight: 500;
}
.scripture-reason {
  font-size: 12px;
  color: #666;
  margin: 6px 0 10px;
}
.scripture-actions {
  display: flex;
  gap: 8px;
}
.btn-accept,
.btn-reject {
  font-size: 13px;
  padding: 4px 14px;
  border-radius: 4px;
  cursor: pointer;
  border: 1px solid #d9d9d9;
  background: #fff;
}
.btn-accept {
  color: #237804;
  border-color: #b7eb8f;
  background: #f6ffed;
}
.btn-reject {
  color: #666;
}
.scripture-decided {
  font-size: 13px;
  color: #888;
}
</style>

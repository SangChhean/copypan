<script setup>
import ToolsHeader from "@/components/toolbox/ToolsHeader.vue";
import { ref, computed, watch } from "vue";
import { LoadingOutlined, CopyOutlined, DownloadOutlined } from "@ant-design/icons-vue";
import axios from "axios";
import { toastSuccess, toastWarning, toastError } from "@/components/utils/Dialog.js";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";
const MAX_CONTENT_CHARS = 100_000;

const sourceLang = ref("zh"); // zh | en
const content = ref("");
const inputError = ref(null);

const TARGET_ORDER = ["zh_cn", "zh_tw", "es"];
const TARGET_META = {
  zh_cn: {
    label: "中文简体",
    formatDirection: "en2zh",
    usesEnglishTemplate: false,
    hasErrorCheck: false,
  },
  zh_tw: {
    label: "中文繁体",
    formatDirection: "zh_cn2tw",
    usesEnglishTemplate: false,
    hasErrorCheck: true,
  },
  es: {
    label: "西班牙语",
    formatDirection: "zh2en",
    usesEnglishTemplate: true,
    hasErrorCheck: false,
  },
};

const targetLanguages = ref([]);
const activeTargets = ref([]);

watch(targetLanguages, (newVal, oldVal) => {
  const justCheckedTw = newVal.includes("zh_tw") && !oldVal.includes("zh_tw");
  if (justCheckedTw && !newVal.includes("zh_cn")) {
    targetLanguages.value = [...newVal, "zh_cn"];
  }
});

function emptyPanelState() {
  return {
    loading: false,
    error: null,
    result: null,
    durationMs: null,
    downloadFormats: [],
    downloading: false,
    isOutline: true,
    errorHits: [],
    checkingErrors: false,
    checkErrorMsg: null,
  };
}

const zhEnPanel = ref(emptyPanelState());
const enPanels = ref({
  zh_cn: emptyPanelState(),
  zh_tw: emptyPanelState(),
  es: emptyPanelState(),
});

const isSourceChinese = computed(() => sourceLang.value === "zh");
const isSourceEnglish = computed(() => sourceLang.value === "en");

const inputPlaceholder = computed(() =>
  isSourceChinese.value ? "请粘贴简体中文纲目全文…" : "请粘贴英文纲目全文…"
);

const canTranslate = computed(() => {
  if (!(content.value || "").trim()) return false;
  if (isSourceEnglish.value && targetLanguages.value.length === 0) return false;
  return true;
});

const translating = computed(() => {
  if (isSourceChinese.value) return zhEnPanel.value.loading;
  return TARGET_ORDER.some((k) => enPanels.value[k].loading);
});

function formatDuration(ms) {
  if (ms == null) return "";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function normalizeErrorHits(hits) {
  return hits.map((h, i) => ({
    ...h,
    id: `${h.start}-${h.end}-${i}`,
    replaceInput: h.suggestion != null && h.suggestion !== "" ? h.suggestion : "",
  }));
}

function getHitContextHtml(hit, text) {
  const start = hit.start ?? 0;
  const end = hit.end ?? start;
  const beforeStart = Math.max(0, start - 3);
  const afterEnd = Math.min(text.length, end + 3);
  const prefixEllipsis = beforeStart > 0 ? "..." : "";
  const suffixEllipsis = afterEnd < text.length ? "..." : "";
  const before = escapeHtml(text.slice(beforeStart, start));
  const word = escapeHtml(text.slice(start, end) || hit.word);
  const after = escapeHtml(text.slice(end, afterEnd));
  return `${prefixEllipsis}${before}<span class="hit-word-mark">${word}</span>${after}${suffixEllipsis}`;
}

function hitsWithAcceptInput(panel) {
  return panel.errorHits.filter((h) => (h.replaceInput || "").trim());
}

function applyReplacementAt(text, hit, replaceValue) {
  if (!text || !replaceValue) return null;
  const slice = text.slice(hit.start, hit.end);
  if (slice === hit.word) {
    return text.slice(0, hit.start) + replaceValue + text.slice(hit.end);
  }
  const idx = text.indexOf(hit.word);
  if (idx === -1) return null;
  return text.slice(0, idx) + replaceValue + text.slice(idx + hit.word.length);
}

function rejectHit(panel, hit) {
  panel.errorHits = panel.errorHits.filter((h) => h.id !== hit.id);
}

function acceptHit(panel, hit, onRecheck) {
  const val = (hit.replaceInput || "").trim();
  if (!val || !panel.result) return;
  const next = applyReplacementAt(panel.result, hit, val);
  if (next != null) {
    panel.result = next;
    onRecheck();
  }
}

function acceptAllHits(panel, onRecheck) {
  if (!panel.result) return;
  const hits = hitsWithAcceptInput(panel);
  if (!hits.length) return;
  let text = panel.result;
  const sorted = [...hits].sort((a, b) => b.start - a.start);
  for (const h of sorted) {
    const val = (h.replaceInput || "").trim();
    if (!val) continue;
    const slice = text.slice(h.start, h.end);
    if (slice === h.word) {
      text = text.slice(0, h.start) + val + text.slice(h.end);
    }
  }
  panel.result = text;
  onRecheck();
}

async function checkErrorCharsForPanel(panel) {
  const text = (panel.result || "").trim();
  if (!text) {
    panel.errorHits = [];
    panel.checkErrorMsg = null;
    return;
  }
  const authToken = localStorage.getItem("token") || null;
  if (!authToken) {
    window.location.hash = "/login";
    return;
  }
  panel.checkingErrors = true;
  panel.checkErrorMsg = null;
  try {
    const res = await axios.post(
      `${apiBase}/api/ai_search/check_error_chars`,
      { content: panel.result },
      {
        headers: { Authorization: `Bearer ${authToken}` },
        timeout: 30000,
      }
    );
    panel.errorHits = normalizeErrorHits(res.data?.hits || []);
  } catch (err) {
    panel.errorHits = [];
    panel.checkErrorMsg =
      err.response?.data?.detail || err.message || "易错字检查失败";
  } finally {
    panel.checkingErrors = false;
  }
}

function copyText(text) {
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    try {
      toastSuccess("已复制到剪贴板");
    } catch (_) {}
  });
}

function parseApiError(res, errorData) {
  let detail = errorData.detail;
  if (Array.isArray(detail)) {
    detail = detail.map((x) => x?.msg || x?.message || JSON.stringify(x)).join("；");
  }
  return detail || errorData.error || errorData.message || `请求失败（${res.status}）`;
}

async function callOutlineTranslate(apiDirection, text, authToken) {
  const res = await fetch(`${apiBase}/api/ai_search/outline_translate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify({
      direction: apiDirection,
      content: text,
      outline_topic: null,
    }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(parseApiError(res, data));
  }
  if (data.error && !data.result) {
    throw new Error(data.error);
  }
  if (!data.result) {
    throw new Error("翻译失败，请稍后重试");
  }
  return data;
}

async function callOutlineToTraditional(simplified, authToken) {
  const res = await fetch(`${apiBase}/api/ai_search/outline_to_traditional`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify({ content: simplified }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(parseApiError(res, data));
  }
  if (data.error && !data.answer_zh_tw) {
    throw new Error(data.error);
  }
  if (!data.answer_zh_tw) {
    throw new Error("转繁体失败，请稍后重试");
  }
  return data.answer_zh_tw;
}

async function translateZhCn(text, authToken) {
  const start = Date.now();
  const data = await callOutlineTranslate("en2zh", text, authToken);
  return { result: data.result, durationMs: Date.now() - start };
}

async function translateZhTw(text, authToken) {
  const start = Date.now();
  const data = await callOutlineTranslate("en2zh", text, authToken);
  const traditional = await callOutlineToTraditional(data.result, authToken);
  return { result: traditional, durationMs: Date.now() - start };
}

async function translateEs(text, authToken) {
  const start = Date.now();
  const data = await callOutlineTranslate("en2es", text, authToken);
  return { result: data.result, durationMs: Date.now() - start };
}

const TARGET_TRANSLATORS = {
  zh_cn: translateZhCn,
  zh_tw: translateZhTw,
  es: translateEs,
};

async function translateChineseSource(text, authToken) {
  Object.assign(zhEnPanel.value, emptyPanelState(), { loading: true });
  const start = Date.now();
  try {
    const data = await callOutlineTranslate("zh2en", text, authToken);
    zhEnPanel.value.result = data.result;
    zhEnPanel.value.durationMs = Date.now() - start;
    try {
      toastSuccess("翻译完成！");
    } catch (_) {}
  } catch (err) {
    zhEnPanel.value.error =
      (err && err.message) || (typeof err === "string" ? err : "") || "网络错误，请稍后重试";
  } finally {
    zhEnPanel.value.loading = false;
  }
}

async function translateEnglishSource(text, authToken) {
  const selected = TARGET_ORDER.filter((k) => targetLanguages.value.includes(k));
  activeTargets.value = [...selected];

  for (const key of selected) {
    enPanels.value[key] = { ...emptyPanelState(), loading: true };
  }

  const tasks = selected.map((key) => ({
    key,
    promise: TARGET_TRANSLATORS[key](text, authToken),
  }));

  const settled = await Promise.allSettled(tasks.map((t) => t.promise));

  let successCount = 0;
  settled.forEach((outcome, i) => {
    const key = tasks[i].key;
    const panel = enPanels.value[key];
    panel.loading = false;
    if (outcome.status === "fulfilled") {
      panel.result = outcome.value.result;
      panel.durationMs = outcome.value.durationMs;
      successCount += 1;
      if (TARGET_META[key].hasErrorCheck) {
        checkErrorCharsForPanel(panel);
      }
    } else {
      panel.error =
        outcome.reason?.message ||
        (typeof outcome.reason === "string" ? outcome.reason : "") ||
        "翻译失败，请稍后重试";
    }
  });

  if (successCount > 0) {
    try {
      toastSuccess(`翻译完成（${successCount}/${selected.length}）`);
    } catch (_) {}
  }
}

async function translate() {
  const text = (content.value || "").trim();
  inputError.value = null;

  if (!text) {
    inputError.value = isSourceChinese.value
      ? "请先粘贴简体中文纲目"
      : "请先粘贴英文纲目";
    return;
  }
  if (text.length > MAX_CONTENT_CHARS) {
    inputError.value = `正文过长：最多 ${MAX_CONTENT_CHARS.toLocaleString()} 字（与后端一致），请分段翻译`;
    return;
  }
  if (isSourceEnglish.value && targetLanguages.value.length === 0) {
    inputError.value = "请至少选择一个目标语言";
    return;
  }

  const authToken = localStorage.getItem("token") || null;
  if (!authToken) {
    window.location.hash = "/login";
    return;
  }

  if (isSourceChinese.value) {
    await translateChineseSource(text, authToken);
  } else {
    await translateEnglishSource(text, authToken);
  }
}

async function downloadFormatted(panel, meta) {
  if (!panel.result) {
    try {
      toastWarning("请先完成翻译");
    } catch (_) {}
    return;
  }
  if (panel.downloadFormats.length === 0) {
    try {
      toastWarning("请至少选择一个下载格式");
    } catch (_) {}
    return;
  }

  panel.downloading = true;
  const authToken = localStorage.getItem("token") || null;
  if (!authToken) {
    panel.downloading = false;
    window.location.hash = "/login";
    return;
  }

  try {
    const orderedFormats = ["docx", "pdf"].filter((f) =>
      panel.downloadFormats.includes(f)
    );
    for (const format of orderedFormats) {
      const res = await fetch(`${apiBase}/api/ai_search/format_outline_only`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({
          direction: meta.formatDirection,
          translated_text: panel.result,
          output_format: format,
          is_outline: panel.isOutline,
        }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        try {
          toastError(
            `${format.toUpperCase()} 格式化失败: ${errorData.detail || errorData.error || "未知错误"}`
          );
        } catch (_) {}
        continue;
      }

      const data = await res.json();
      const defaultExt = meta.usesEnglishTemplate ? "outline_en" : "outline_zh";

      if (format === "docx" && data.docx_base64) {
        try {
          const bin = Uint8Array.from(atob(data.docx_base64), (c) => c.charCodeAt(0));
          const blob = new Blob([bin], {
            type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = data.filename || `${defaultExt}.docx`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (downloadErr) {
          console.error(`下载${format.toUpperCase()}失败:`, downloadErr);
          try {
            toastError(`下载 ${format.toUpperCase()} 失败`);
          } catch (_) {}
        }
      } else if (format === "pdf") {
        if (data.pdf_base64) {
          try {
            const bin = Uint8Array.from(atob(data.pdf_base64), (c) => c.charCodeAt(0));
            const blob = new Blob([bin], { type: "application/pdf" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = data.filename || `${defaultExt}.pdf`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          } catch (downloadErr) {
            console.error(`下载${format.toUpperCase()}失败:`, downloadErr);
            try {
              toastError(`下载 ${format.toUpperCase()} 失败`);
            } catch (_) {}
          }
        } else if (data.docx_base64) {
          try {
            const bin = Uint8Array.from(atob(data.docx_base64), (c) => c.charCodeAt(0));
            const blob = new Blob([bin], {
              type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = data.filename || `${defaultExt}.docx`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            setTimeout(() => URL.revokeObjectURL(url), 1000);
            try {
              toastWarning(
                "PDF 转换失败（可能未安装 Microsoft Word 或 LibreOffice），已下载 DOCX 文件"
              );
            } catch (_) {}
          } catch (downloadErr) {
            console.error("下载DOCX失败:", downloadErr);
            try {
              toastError("下载文件失败");
            } catch (_) {}
          }
        } else if (data.error) {
          try {
            toastWarning(`PDF 格式化失败: ${data.error}`);
          } catch (_) {}
        } else {
          try {
            toastWarning("PDF 转换失败，请检查是否安装了 Microsoft Word 或 LibreOffice");
          } catch (_) {}
        }
      } else if (data.error) {
        try {
          toastWarning(`${format.toUpperCase()} 格式化失败: ${data.error}`);
        } catch (_) {}
      }
    }

    try {
      toastSuccess("下载完成！");
    } catch (_) {}
  } catch (err) {
    try {
      toastError(err.message || "下载失败，请稍后重试");
    } catch (_) {}
  } finally {
    panel.downloading = false;
  }
}
</script>

<template>
  <ToolsHeader title="纲目翻译" />
  <div class="box">
    <a-card>
      <p class="hint">
        选择源语言后粘贴纲目并翻译，再在各结果栏「刷格式并下载」。
        <strong>输入上限 {{ MAX_CONTENT_CHARS.toLocaleString() }} 字</strong>（下方字数统计）；
        计费按 Gemini token。译文最长受服务端单次输出 token 限制（默认 32768，环境变量
        <code>GEMINI_TRANSLATION_MAX_OUTPUT_TOKENS</code>，约 1024～65536）；过长请分段翻译。
      </p>
      <a-divider :style="{ margin: '12px 0' }" />

      <div class="source-lang-row">
        <button
          type="button"
          class="source-lang-btn"
          :class="{ active: sourceLang === 'zh' }"
          :disabled="translating"
          @click="sourceLang = 'zh'"
        >
          中文
        </button>
        <button
          type="button"
          class="source-lang-btn"
          :class="{ active: sourceLang === 'en' }"
          :disabled="translating"
          @click="sourceLang = 'en'"
        >
          英文
        </button>
      </div>

      <a-divider :style="{ margin: '12px 0' }" />

      <template v-if="isSourceChinese">
        <p class="direction-fixed">翻译方向：简体中文 → 英文</p>
      </template>
      <template v-else>
        <div class="direction-row">
          <span class="label">目标语言：</span>
          <a-checkbox-group v-model:value="targetLanguages" :disabled="translating">
            <a-checkbox value="zh_cn">中文简体</a-checkbox>
            <a-checkbox value="zh_tw">中文繁体</a-checkbox>
            <a-checkbox value="es">西班牙语</a-checkbox>
          </a-checkbox-group>
        </div>
      </template>

      <a-divider :style="{ margin: '12px 0' }" />

      <div class="textarea-wrap">
        <a-textarea
          v-model:value="content"
          :placeholder="inputPlaceholder"
          :rows="12"
          class="content-area"
          :disabled="translating"
          :maxlength="MAX_CONTENT_CHARS"
          show-count
          allow-clear
        />
        <button
          type="button"
          class="clear-btn"
          :disabled="!content || translating"
          @click="content = ''"
        >
          清空
        </button>
      </div>
      <div class="action-row">
        <button
          type="button"
          class="action-btn"
          :disabled="translating || !canTranslate"
          @click="translate"
        >
          <LoadingOutlined v-if="translating" class="btn-icon btn-spin" />
          <span v-if="translating">翻译中…</span>
          <span v-else>翻译</span>
        </button>
      </div>
      <p v-if="translating" class="loading-hint">请耐心等待 1～2 分钟</p>
    </a-card>

    <div v-if="inputError" class="error">{{ inputError }}</div>

    <!-- 中文源：英文结果单栏 -->
    <a-card
      v-if="isSourceChinese && (zhEnPanel.loading || zhEnPanel.result || zhEnPanel.error)"
      class="result-card"
    >
      <template #title>
        <span class="result-title-row">
          <span>英文</span>
          <span v-if="zhEnPanel.durationMs != null" class="duration-badge">
            {{ formatDuration(zhEnPanel.durationMs) }}
          </span>
        </span>
        <button
          v-if="zhEnPanel.result"
          type="button"
          class="copy-btn"
          @click="copyText(zhEnPanel.result)"
        >
          <CopyOutlined /> 复制
        </button>
      </template>

      <div v-if="zhEnPanel.loading" class="panel-loading">
        <LoadingOutlined class="btn-icon btn-spin" /> 翻译中…
      </div>
      <div v-else-if="zhEnPanel.error" class="panel-error">{{ zhEnPanel.error }}</div>
      <template v-else-if="zhEnPanel.result">
        <a-textarea
          v-model:value="zhEnPanel.result"
          :rows="14"
          class="result-textarea"
          placeholder="翻译结果（可编辑）"
        />
        <div class="download-section">
          <div class="direction-row">
            <span class="label">文本类型：</span>
            <a-segmented
              v-model:value="zhEnPanel.isOutline"
              class="direction-segmented"
              :options="[
                { label: '纲目', value: true },
                { label: '非纲目', value: false },
              ]"
            />
          </div>
          <a-divider :style="{ margin: '12px 0' }" />
          <div class="direction-row">
            <span class="label">下载格式：</span>
            <a-checkbox-group v-model:value="zhEnPanel.downloadFormats">
              <a-checkbox value="docx">DOCX</a-checkbox>
              <a-checkbox value="pdf">PDF</a-checkbox>
            </a-checkbox-group>
          </div>
          <div class="action-row" style="margin-top: 12px;">
            <button
              type="button"
              class="action-btn"
              :disabled="zhEnPanel.downloading || zhEnPanel.downloadFormats.length === 0"
              @click="downloadFormatted(zhEnPanel, { formatDirection: 'zh2en', usesEnglishTemplate: true })"
            >
              <LoadingOutlined v-if="zhEnPanel.downloading" class="btn-icon btn-spin" />
              <DownloadOutlined v-else class="btn-icon" />
              <span v-if="zhEnPanel.downloading">格式化并下载中…</span>
              <span v-else>刷格式并下载</span>
            </button>
          </div>
          <p v-if="zhEnPanel.downloading" class="loading-hint">请耐心等待 1～2 分钟</p>
        </div>
      </template>
    </a-card>

    <!-- 英文源：多目标结果栏 -->
    <template v-if="isSourceEnglish">
      <a-card
        v-for="key in activeTargets"
        :key="key"
        class="result-card"
      >
        <template #title>
          <span class="result-title-row">
            <span>{{ TARGET_META[key].label }}</span>
            <span
              v-if="enPanels[key].durationMs != null && !enPanels[key].loading"
              class="duration-badge"
            >
              {{ formatDuration(enPanels[key].durationMs) }}
            </span>
          </span>
          <button
            v-if="enPanels[key].result"
            type="button"
            class="copy-btn"
            @click="copyText(enPanels[key].result)"
          >
            <CopyOutlined /> 复制
          </button>
        </template>

        <div v-if="enPanels[key].loading" class="panel-loading">
          <LoadingOutlined class="btn-icon btn-spin" /> 翻译中…
        </div>
        <div v-else-if="enPanels[key].error" class="panel-error">
          {{ enPanels[key].error }}
        </div>
        <template v-else-if="enPanels[key].result">
          <a-textarea
            v-model:value="enPanels[key].result"
            :rows="14"
            class="result-textarea"
            placeholder="翻译结果（可编辑）"
          />

          <template v-if="TARGET_META[key].hasErrorCheck">
            <div class="error-check-toolbar">
              <button
                type="button"
                class="check-err-btn"
                :disabled="enPanels[key].checkingErrors || !enPanels[key].result"
                @click="checkErrorCharsForPanel(enPanels[key])"
              >
                <LoadingOutlined
                  v-if="enPanels[key].checkingErrors"
                  class="btn-icon btn-spin"
                />
                <span v-if="enPanels[key].checkingErrors">检查中…</span>
                <span v-else>检查易错字</span>
              </button>
              <button
                v-if="enPanels[key].errorHits.length"
                type="button"
                class="accept-all-btn"
                :disabled="
                  enPanels[key].checkingErrors ||
                  !hitsWithAcceptInput(enPanels[key]).length
                "
                @click="
                  acceptAllHits(enPanels[key], () =>
                    checkErrorCharsForPanel(enPanels[key])
                  )
                "
              >
                全部接受
              </button>
            </div>
            <p v-if="enPanels[key].checkErrorMsg" class="check-err-msg">
              {{ enPanels[key].checkErrorMsg }}
            </p>
            <p
              v-else-if="
                !enPanels[key].checkingErrors &&
                enPanels[key].result &&
                enPanels[key].errorHits.length === 0
              "
              class="check-ok"
            >
              ✓ 未发现易错字
            </p>
            <ul v-if="enPanels[key].errorHits.length" class="hit-list">
              <li
                v-for="hit in enPanels[key].errorHits"
                :key="hit.id"
                class="hit-item"
              >
                <div
                  class="hit-context"
                  v-html="getHitContextHtml(hit, enPanels[key].result)"
                />
                <div class="hit-row">
                  <a-input
                    v-model:value="hit.replaceInput"
                    class="hit-input"
                    size="small"
                    :placeholder="hit.suggestion ? undefined : '输入替换值'"
                    :disabled="enPanels[key].checkingErrors"
                  />
                  <div class="hit-actions">
                    <button
                      type="button"
                      class="accept-btn"
                      :disabled="
                        enPanels[key].checkingErrors ||
                        !(hit.replaceInput || '').trim()
                      "
                      @click="
                        acceptHit(enPanels[key], hit, () =>
                          checkErrorCharsForPanel(enPanels[key])
                        )
                      "
                    >
                      接受
                    </button>
                    <button
                      type="button"
                      class="reject-btn"
                      :disabled="enPanels[key].checkingErrors"
                      @click="rejectHit(enPanels[key], hit)"
                    >
                      拒绝
                    </button>
                  </div>
                </div>
              </li>
            </ul>
          </template>

          <div class="download-section">
            <div class="direction-row">
              <span class="label">下载格式：</span>
              <a-checkbox-group v-model:value="enPanels[key].downloadFormats">
                <a-checkbox value="docx">DOCX</a-checkbox>
                <a-checkbox value="pdf">PDF</a-checkbox>
              </a-checkbox-group>
            </div>
            <div class="action-row" style="margin-top: 12px;">
              <button
                type="button"
                class="action-btn"
                :disabled="
                  enPanels[key].downloading ||
                  enPanels[key].downloadFormats.length === 0
                "
                @click="downloadFormatted(enPanels[key], TARGET_META[key])"
              >
                <LoadingOutlined
                  v-if="enPanels[key].downloading"
                  class="btn-icon btn-spin"
                />
                <DownloadOutlined v-else class="btn-icon" />
                <span v-if="enPanels[key].downloading">格式化并下载中…</span>
                <span v-else>刷格式并下载</span>
              </button>
            </div>
            <p v-if="enPanels[key].downloading" class="loading-hint">
              请耐心等待 1～2 分钟
            </p>
          </div>
        </template>
      </a-card>
    </template>
  </div>
</template>

<style scoped>
.box {
  padding: 1em;
  max-width: 720px;
  margin: 0 auto;
}

.box :deep(.ant-card) {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.06);
}

.hint {
  color: #555;
  margin: 0;
  font-size: 0.95em;
  line-height: 1.5;
}

.hint code {
  font-size: 0.88em;
  padding: 0 4px;
  background: #f5f5f5;
  border-radius: 4px;
}

.source-lang-row {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.source-lang-btn {
  flex: 1;
  max-width: 200px;
  padding: 14px 24px;
  font-size: 18px;
  font-weight: 600;
  border-radius: 8px;
  border: 2px solid #d9d9d9;
  background: #fafafa;
  color: #333;
  cursor: pointer;
  transition: all 0.2s;
}

.source-lang-btn:hover:not(:disabled) {
  border-color: #1890ff;
  color: #1890ff;
}

.source-lang-btn.active {
  background: #1890ff;
  border-color: #1890ff;
  color: #fff;
}

.source-lang-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.direction-fixed {
  margin: 0;
  font-weight: 600;
  color: #333;
  font-size: 1em;
}

.direction-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.direction-row .label {
  font-weight: 600;
  color: #333;
  font-size: 1em;
}

.direction-segmented :deep(.ant-segmented-group) {
  gap: 4px;
}
.direction-segmented :deep(.ant-segmented-item) {
  padding: 8px 20px;
  font-weight: 500;
  font-size: 15px;
  border: 2px solid #d9d9d9;
  border-radius: 6px;
  background: #fafafa;
}
.direction-segmented :deep(.ant-segmented-item:hover) {
  border-color: #52c41a;
  color: #389e0d;
}
.direction-segmented :deep(.ant-segmented-item-selected) {
  background: #52c41a !important;
  border-color: #52c41a !important;
  color: #fff !important;
}
.direction-segmented :deep(.ant-segmented-thumb) {
  background: #52c41a !important;
  border-radius: 4px;
}

.textarea-wrap {
  margin-top: 8px;
  position: relative;
}

.content-area {
  display: block;
}

.content-area :deep(.ant-input) {
  border-radius: 8px;
  font-family: inherit;
}

.clear-btn {
  margin-top: 10px;
  padding: 6px 16px;
  font-size: 14px;
  font-weight: 500;
  color: #666;
  background: #fff;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  cursor: pointer;
}
.clear-btn:hover:not(:disabled) {
  color: #ff4d4f;
  border-color: #ff4d4f;
  background: #fff1f0;
}
.clear-btn:disabled {
  color: #bbb;
  cursor: not-allowed;
  background: #fafafa;
}

.action-row {
  margin-top: 16px;
  padding: 12px 0;
  border-top: 1px solid #f0f0f0;
  display: flex;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}

.loading-hint {
  margin: 8px 0 0;
  color: #8c8c8c;
  font-size: 0.9em;
  text-align: center;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 24px;
  font-size: 16px;
  border-radius: 6px;
  border: none;
  background: #1890ff;
  color: #fff;
  cursor: pointer;
}

.action-btn .btn-icon {
  font-size: 18px;
}

.action-btn .btn-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.action-btn:hover:not(:disabled) {
  background: #40a9ff;
}

.action-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.error {
  margin-top: 12px;
  color: #cf1322;
  font-size: 0.95em;
}

.result-card {
  margin-top: 20px;
}

.result-card :deep(.ant-card-head) {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}

.result-title-row {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.duration-badge {
  display: inline-block;
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 500;
  color: #595959;
  background: #f0f0f0;
  border-radius: 10px;
}

.copy-btn {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: 13px;
  border-radius: 4px;
  border: 1px solid #d9d9d9;
  background: #fff;
  cursor: pointer;
  color: #555;
}

.copy-btn:hover {
  color: #1890ff;
  border-color: #1890ff;
}

.panel-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #8c8c8c;
  padding: 16px 0;
}

.panel-error {
  color: #cf1322;
  padding: 8px 0;
  font-size: 0.95em;
}

.result-textarea {
  display: block;
}

.result-textarea :deep(.ant-input) {
  font-family: inherit;
  font-size: 0.95em;
  line-height: 1.6;
  border-radius: 8px;
}

.download-section {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
}

.error-check-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
}

.check-err-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  font-size: 14px;
  border-radius: 6px;
  border: 1px solid #d9d9d9;
  background: #fff;
  color: #333;
  cursor: pointer;
}

.check-err-btn:hover:not(:disabled) {
  color: #1890ff;
  border-color: #1890ff;
}

.check-err-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.accept-all-btn {
  padding: 6px 16px;
  font-size: 14px;
  border-radius: 6px;
  border: none;
  background: #52c41a;
  color: #fff;
  cursor: pointer;
}

.accept-all-btn:hover:not(:disabled) {
  background: #73d13d;
}

.accept-all-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.check-ok {
  margin: 10px 0 0;
  color: #389e0d;
  font-size: 0.95em;
}

.check-err-msg {
  margin: 10px 0 0;
  color: #cf1322;
  font-size: 0.9em;
}

.hit-list {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.hit-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 12px;
  background: #fff7e6;
  border: 1px solid #ffd591;
  border-radius: 6px;
  font-size: 0.9em;
}

.hit-context {
  width: 100%;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
  color: #333;
  font-size: 0.95em;
}

.hit-context :deep(.hit-word-mark) {
  background: #ffbb96;
  padding: 0 2px;
  border-radius: 2px;
  font-weight: 500;
}

.hit-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
  width: 100%;
}

.hit-input {
  flex: 1;
  min-width: 120px;
  max-width: 280px;
}

.hit-actions {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
}

.accept-btn {
  flex-shrink: 0;
  padding: 4px 12px;
  font-size: 13px;
  border-radius: 4px;
  border: 1px solid #52c41a;
  background: #fff;
  color: #389e0d;
  cursor: pointer;
}

.accept-btn:hover:not(:disabled) {
  background: #f6ffed;
}

.accept-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.reject-btn {
  flex-shrink: 0;
  padding: 4px 12px;
  font-size: 13px;
  border-radius: 4px;
  border: 1px solid #d9d9d9;
  background: #fff;
  color: #666;
  cursor: pointer;
}

.reject-btn:hover:not(:disabled) {
  color: #ff4d4f;
  border-color: #ff4d4f;
  background: #fff1f0;
}

.reject-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}
</style>

<template>
  <div class="feast-maker-wrap">
    <ToolsHeader title="节期-数据制作" />

    <div class="feast-maker-body">
      <aside class="side-nav">
        <a-card size="small" class="info-block" title="特会信息">
          <div class="field-row">
            <span class="field-label">年份</span>
            <a-input-number v-model:value="year" :min="1900" :max="2100" class="field-control" />
          </div>
          <div class="field-row">
            <span class="field-label">特会类型</span>
            <a-select v-model:value="feastType" :options="feastTypeOptions" class="field-control" />
          </div>
          <div class="field-row">
            <span class="field-label">总题</span>
            <a-input v-model:value="topic" placeholder="总题" class="field-control" />
          </div>
          <div class="field-row">
            <span class="field-label">bsn（当前最大）</span>
            <a-input-number v-model:value="bsn" :min="0" class="field-control" />
            <span class="field-hint">下载时将从 bsn+1 开始编号</span>
          </div>
          <div class="field-row">
            <span class="field-label">csn（当前最大）</span>
            <a-input-number v-model:value="csn" :min="0" class="field-control" />
            <span class="field-hint">下载时将从 csn+1 开始编号</span>
          </div>
        </a-card>

        <a-card size="small" class="chapter-list" title="篇目列表">
          <div class="chapter-items">
            <div
              v-for="(ch, idx) in chapters"
              :key="idx"
              class="chapter-item"
              :class="{ active: currentIndex === idx }"
              @click="currentIndex = idx"
            >
              <span
                class="chapter-dot"
                :style="{ background: ch.confirmed ? '#52c41a' : '#ff4d4f' }"
              />
              <span class="chapter-label">{{ chapterListLabel(ch, idx) }}</span>
              <a-button
                type="text"
                size="small"
                class="chapter-del"
                :disabled="chapters.length <= 1"
                @click.stop="removeChapter(idx)"
              >
                <DeleteOutlined />
              </a-button>
            </div>
          </div>
          <a-button type="dashed" block class="add-chapter-btn" @click="addChapter">
            ＋ 添加篇
          </a-button>
        </a-card>

        <a-card size="small" class="download-block" title="下载">
          <div class="download-options">
            <a-checkbox v-model:checked="downloadFeasts">feasts.json</a-checkbox>
            <a-checkbox v-model:checked="downloadMapBookname">map_feasts_bookname.json</a-checkbox>
            <a-checkbox v-model:checked="downloadMapTitle">map_feasts_title.json</a-checkbox>
          </div>
          <a-button
            type="primary"
            block
            :disabled="!canDownload || downloading"
            :loading="downloading"
            @click="onDownload"
          >
            下载 JSON 文件
          </a-button>
        </a-card>
      </aside>

      <main class="edit-area">
        <a-card size="small" v-if="currentChapter">
          <template v-if="currentChapter.phase === 1">
            <div class="phase-title">第 {{ currentIndex + 1 }} 篇</div>
            <a-row :gutter="16">
              <a-col :span="12">
                <div class="col-label">中文原文</div>
                <a-textarea
                  v-model:value="currentChapter.raw_zh"
                  :auto-size="{ minRows: 20 }"
                  placeholder="粘贴中文纲目原文，每行一条"
                />
              </a-col>
              <a-col :span="12">
                <div class="col-label">英文原文</div>
                <a-textarea
                  v-model:value="currentChapter.raw_en"
                  :auto-size="{ minRows: 20 }"
                  placeholder="Paste English outline, one line per item"
                />
              </a-col>
            </a-row>
            <div class="phase-actions">
              <a-button type="primary" @click="parseAlign">解析对齐</a-button>
            </div>
          </template>

          <template v-else>
            <div class="phase-title">第 {{ currentIndex + 1 }} 篇 · 逐行编辑</div>

            <div
              class="stats-bar"
              :class="lineStats.unequal ? 'stats-bar-warn' : 'stats-bar-ok'"
            >
              中文 {{ lineStats.zhCount }} 行 / 英文 {{ lineStats.enCount }} 行
            </div>

            <a-row :gutter="16" class="lines-split">
              <a-col :span="12">
                <div class="col-label">中文</div>
                <div class="line-list-col">
                  <div
                    v-for="(line, lineIdx) in currentChapter.lines_zh"
                    :key="'zh-' + lineIdx"
                    class="line-row"
                  >
                    <span class="line-num">{{ lineIdx + 1 }}</span>
                    <a-textarea
                      v-model:value="line.text"
                      class="line-textarea"
                      :auto-size="{ minRows: 1, maxRows: 6 }"
                    />
                    <div class="line-actions">
                      <a-button size="small" type="text" @click="insertLineZh(lineIdx)">＋</a-button>
                      <a-button
                        size="small"
                        type="text"
                        danger
                        :disabled="currentChapter.lines_zh.length <= 1"
                        @click="removeLineZh(lineIdx)"
                      >
                        －
                      </a-button>
                    </div>
                  </div>
                  <a-button
                    v-if="!currentChapter.lines_zh.length"
                    type="dashed"
                    block
                    size="small"
                    @click="currentChapter.lines_zh.push({ text: '' })"
                  >
                    ＋ 添加行
                  </a-button>
                </div>
              </a-col>
              <a-col :span="12">
                <div class="col-label">英文</div>
                <div class="line-list-col">
                  <div
                    v-for="(line, lineIdx) in currentChapter.lines_en"
                    :key="'en-' + lineIdx"
                    class="line-row"
                  >
                    <span class="line-num">{{ lineIdx + 1 }}</span>
                    <a-textarea
                      v-model:value="line.text"
                      class="line-textarea"
                      :auto-size="{ minRows: 1, maxRows: 6 }"
                    />
                    <div class="line-actions">
                      <a-button size="small" type="text" @click="insertLineEn(lineIdx)">＋</a-button>
                      <a-button
                        size="small"
                        type="text"
                        danger
                        :disabled="currentChapter.lines_en.length <= 1"
                        @click="removeLineEn(lineIdx)"
                      >
                        －
                      </a-button>
                    </div>
                  </div>
                  <a-button
                    v-if="!currentChapter.lines_en.length"
                    type="dashed"
                    block
                    size="small"
                    @click="currentChapter.lines_en.push({ text: '' })"
                  >
                    ＋ 添加行
                  </a-button>
                </div>
              </a-col>
            </a-row>

            <div class="phase-actions phase-actions-split">
              <a-button @click="backToRaw">返回编辑原文</a-button>
              <a-button type="primary" @click="confirmChapter">确认本篇</a-button>
            </div>
          </template>
        </a-card>
      </main>
    </div>

    <a-modal
      v-model:open="confirmModalOpen"
      :title="confirmModalTitle"
      ok-text="确认继续"
      cancel-text="取消"
      @ok="onConfirmModalOk"
    >
      <p>{{ confirmModalText }}</p>
    </a-modal>

    <a-modal
      v-model:open="sequenceConfirmOpen"
      title="确认序号"
      ok-text="确认下载"
      cancel-text="取消"
      @ok="onSequenceConfirmOk"
    >
      <p>{{ sequenceConfirmText }}</p>
    </a-modal>

    <a-modal
      v-model:open="precheckModalOpen"
      title="格式预检"
      ok-text="仍然下载"
      cancel-text="取消"
      width="560px"
      @ok="onPrecheckConfirmOk"
      @cancel="onPrecheckCancel"
    >
      <div v-if="precheckIssues.emptyEn.length" class="precheck-group">
        <div class="precheck-group-title">以下条目英文为空</div>
        <ul class="precheck-list">
          <li v-for="(item, idx) in precheckIssues.emptyEn" :key="'en-' + idx">{{ item }}</li>
        </ul>
      </div>
      <div v-if="precheckIssues.invalidTypes.length" class="precheck-group">
        <div class="precheck-group-title">type 不合法</div>
        <ul class="precheck-list">
          <li v-for="(item, idx) in precheckIssues.invalidTypes" :key="'type-' + idx">{{ item }}</li>
        </ul>
      </div>
      <div v-if="precheckIssues.duplicateIds.length" class="precheck-group">
        <div class="precheck-group-title">id 重复</div>
        <ul class="precheck-list">
          <li v-for="(item, idx) in precheckIssues.duplicateIds" :key="'id-' + idx">{{ item }}</li>
        </ul>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import axios from "axios";
import { message } from "ant-design-vue";
import { DeleteOutlined } from "@ant-design/icons-vue";
import ToolsHeader from "./ToolsHeader.vue";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";

const CONFERENCE_MAP = {
  ic: { zh: "年国际华语特会", en: "ICSC" },
  is: { zh: "年春季长老训练", en: "ITERO-Spring" },
  mdc: { zh: "年国殇节特会", en: "MDC" },
  st: { zh: "年夏训", en: "ST" },
  if: { zh: "年秋季长老训练", en: "ITERO-Fall" },
  tgc: { zh: "年感恩节特会", en: "TGC" },
  wt: { zh: "年冬训", en: "WT" },
  ftta: { zh: "年安那翰全时间训练", en: "FTTA" },
  ftta_s: { zh: "年安那翰春季全时间训练", en: "FTTA-Spring" },
  ftta_f: { zh: "年安那翰秋季全时间训练", en: "FTTA-Fall" },
};

const VALID_FEAST_TYPES = [
  "bookname",
  "title",
  "bible_reading",
  "ot1",
  "ot2",
  "ot3",
  "ot4",
  "ot5",
];

const feastTypeOptions = [
  { value: "ic", label: "国际华语特会" },
  { value: "is", label: "春季长老训练" },
  { value: "mdc", label: "国殇节特会" },
  { value: "st", label: "夏训" },
  { value: "if", label: "秋季长老训练" },
  { value: "tgc", label: "感恩节特会" },
  { value: "wt", label: "冬训" },
  { value: "ftta", label: "安那翰全时间训练" },
  { value: "ftta_s", label: "安那翰春季全时间训练" },
  { value: "ftta_f", label: "安那翰秋季全时间训练" },
];

function createEmptyChapter() {
  return {
    title_zh: "",
    title_en: "",
    raw_zh: "",
    raw_en: "",
    lines_zh: [],
    lines_en: [],
    lines: [],
    confirmed: false,
    phase: 1,
  };
}

function getAuthHeaders() {
  const token = localStorage.getItem("token");
  if (!token) {
    message.error("请先登录");
    return null;
  }
  return { Authorization: `Bearer ${token}` };
}

function getType(zh) {
  const s = (zh || "").trim();
  if (/^第[一二三四五六七八九十百零]+[篇章题课][\t　]/.test(s)) return "title";
  if (/^读经：/.test(s)) return "bible_reading";
  if (/^[壹贰叁肆伍陆柒捌玖拾]+[\t　]/.test(s)) return "ot1";
  if (/^[一二三四五六七八九十]+[\t　]/.test(s)) return "ot2";
  if (/^\d+[\t　]/.test(s)) return "ot3";
  if (/^[a-z]+[\t　]/.test(s)) return "ot4";
  if (/^\([一二三四五六七八九十]+\)[\t　]/.test(s)) return "ot5";
  if (/^\(\d+\)[\t　]/.test(s)) return "ot5";
  return "ot2";
}

function getIndex(type) {
  if (type === "bookname") return ["feasts", "feasts_booknames"];
  if (type === "title") return ["feasts", "feasts_titles"];
  if (type === "ot1") return ["feasts", "feasts_ot1"];
  return ["feasts"];
}

function toChineseNum(n) {
  const digits = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九"];
  if (n < 10) return digits[n];
  if (n < 20) return "十" + digits[n % 10];
  const tens = Math.floor(n / 10);
  const ones = n % 10;
  return digits[tens] + "十" + (ones ? digits[ones] : "");
}

function downloadJson(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const year = ref(new Date().getFullYear());
const feastType = ref("wt");
const topic = ref("");
const bsn = ref(0);
const csn = ref(0);
const chapters = ref([createEmptyChapter()]);
const currentIndex = ref(0);
const downloading = ref(false);
const confirmModalOpen = ref(false);
const confirmModalTitle = ref("");
const confirmModalText = ref("");
const confirmModalKind = ref("");
const sequenceConfirmOpen = ref(false);
const sequenceConfirmText = ref("");
const precheckModalOpen = ref(false);
const precheckIssues = ref({ emptyEn: [], invalidTypes: [], duplicateIds: [] });
const pendingDownloadPayload = ref(null);
const downloadFeasts = ref(true);
const downloadMapBookname = ref(true);
const downloadMapTitle = ref(true);

const currentChapter = computed(() => chapters.value[currentIndex.value] ?? null);

const hasDownloadSelection = computed(
  () => downloadFeasts.value || downloadMapBookname.value || downloadMapTitle.value
);

const needsSequenceUpdate = computed(
  () => downloadMapBookname.value || downloadMapTitle.value
);

const canDownload = computed(
  () => chapters.value.some((ch) => ch.confirmed) && hasDownloadSelection.value
);

const lineStats = computed(() => {
  const ch = currentChapter.value;
  if (!ch) {
    return { zhCount: 0, enCount: 0, unequal: false };
  }
  const zhCount = (ch.lines_zh || []).length;
  const enCount = (ch.lines_en || []).length;
  return { zhCount, enCount, unequal: zhCount !== enCount };
});

function getBookMeta() {
  const type = feastType.value;
  const conf = CONFERENCE_MAP[type] || { zh: "", en: "" };
  const typeCode = type.replace(/_/g, "-");
  const y = year.value;
  const subject = (topic.value || "").trim();
  const book_name_zh = `${y}${conf.zh}`;
  const book_name_en = `${y} ${conf.en}`;
  const bookTagId = `feasts_${y}-${typeCode}`;
  const mapBookId = `feasts_${y}_${type}`;
  return { type, typeCode, y, subject, book_name_zh, book_name_en, bookTagId, mapBookId };
}

function chapterListLabel(ch, idx) {
  const num = idx + 1;
  const t = (ch.title_zh || "").trim();
  if (!t) return `第${num}篇`;
  const short = t.length > 10 ? `${t.slice(0, 10)}…` : t;
  return `${num}. ${short}`;
}

function addChapter() {
  chapters.value.push(createEmptyChapter());
  currentIndex.value = chapters.value.length - 1;
}

function removeChapter(idx) {
  if (chapters.value.length <= 1) return;
  chapters.value.splice(idx, 1);
  if (currentIndex.value === idx) {
    currentIndex.value = Math.max(0, idx - 1);
  } else if (currentIndex.value > idx) {
    currentIndex.value -= 1;
  }
}

function splitNonEmptyLines(raw) {
  return (raw || "")
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function validateYear() {
  if (year.value == null || year.value === "") {
    message.warning("请填写年份");
    return false;
  }
  return true;
}

function validateFeastType() {
  if (!feastType.value) {
    message.warning("请选择特会类型");
    return false;
  }
  return true;
}

function validateTopic() {
  if (!(topic.value || "").trim()) {
    message.warning("请填写总题");
    return false;
  }
  return true;
}

function validateParseAlignInputs() {
  if (!validateYear()) return false;
  if (!validateFeastType()) return false;
  if (!validateTopic()) return false;
  const ch = currentChapter.value;
  if (!ch) return false;
  if (!(ch.raw_zh || "").trim()) {
    message.warning("请填写中文原文");
    return false;
  }
  if (!(ch.raw_en || "").trim()) {
    message.warning("请填写英文原文");
    return false;
  }
  return true;
}

function validateDownloadInputs() {
  if (!validateYear()) return false;
  if (!validateFeastType()) return false;
  if (!validateTopic()) return false;
  if (!hasDownloadSelection.value) {
    message.warning("请至少选择一个文件");
    return false;
  }
  if (needsSequenceUpdate.value) {
    if (!Number.isInteger(bsn.value) || bsn.value <= 0) {
      message.warning("bsn 必须为正整数");
      return false;
    }
    if (!Number.isInteger(csn.value) || csn.value <= 0) {
      message.warning("csn 必须为正整数");
      return false;
    }
  }
  if (!chapters.value.some((ch) => ch.confirmed)) {
    message.warning("请至少确认一篇");
    return false;
  }
  return true;
}

function parseAlign() {
  if (!validateParseAlignInputs()) return;
  const ch = currentChapter.value;
  if (!ch) return;
  const zhArr = splitNonEmptyLines(ch.raw_zh);
  const enArr = splitNonEmptyLines(ch.raw_en);
  ch.lines_zh = zhArr.map((text) => ({ text }));
  ch.lines_en = enArr.map((text) => ({ text }));
  ch.phase = 2;
  message.success(`已解析：中文 ${ch.lines_zh.length} 行，英文 ${ch.lines_en.length} 行`);
}

function insertLineZh(lineIdx) {
  const ch = currentChapter.value;
  if (!ch) return;
  ch.lines_zh.splice(lineIdx + 1, 0, { text: "" });
}

function removeLineZh(lineIdx) {
  const ch = currentChapter.value;
  if (!ch || ch.lines_zh.length <= 1) return;
  ch.lines_zh.splice(lineIdx, 1);
}

function insertLineEn(lineIdx) {
  const ch = currentChapter.value;
  if (!ch) return;
  ch.lines_en.splice(lineIdx + 1, 0, { text: "" });
}

function removeLineEn(lineIdx) {
  const ch = currentChapter.value;
  if (!ch || ch.lines_en.length <= 1) return;
  ch.lines_en.splice(lineIdx, 1);
}

function zipChapterLines(ch) {
  const maxLen = Math.max(ch.lines_zh.length, ch.lines_en.length);
  ch.lines = Array.from({ length: maxLen }, (_, i) => ({
    zh: (ch.lines_zh[i]?.text || "").trim(),
    en: (ch.lines_en[i]?.text || "").trim(),
  }));
}

function hasOt1InChapter(ch) {
  return (ch.lines_zh || []).some((line) => getType(line.text) === "ot1");
}

function doConfirmChapter() {
  const ch = currentChapter.value;
  if (!ch) return;
  if (!ch.lines_zh.length && !ch.lines_en.length) {
    message.warning("请先解析对齐或至少保留一行");
    return;
  }
  zipChapterLines(ch);
  ch.title_zh = (ch.lines_zh[0]?.text || "").trim();
  ch.title_en = (ch.lines_en[0]?.text || "").trim();
  ch.confirmed = true;
  confirmModalOpen.value = false;
  confirmModalKind.value = "";
  message.success("本篇已确认");
  if (currentIndex.value < chapters.value.length - 1) {
    currentIndex.value += 1;
  }
}

function checkOt1AndConfirm() {
  const ch = currentChapter.value;
  if (!ch) return;
  if (!hasOt1InChapter(ch)) {
    confirmModalTitle.value = "格式警告";
    confirmModalText.value =
      "本篇未检测到一级大纲（壹贰叁…），可能存在格式问题，确认继续？";
    confirmModalKind.value = "ot1";
    confirmModalOpen.value = true;
    return;
  }
  doConfirmChapter();
}

function onConfirmModalOk() {
  if (confirmModalKind.value === "unequal") {
    checkOt1AndConfirm();
    return;
  }
  doConfirmChapter();
}

function confirmChapter() {
  const ch = currentChapter.value;
  if (!ch) return;
  if (!ch.lines_zh.length && !ch.lines_en.length) {
    message.warning("请先解析对齐或至少保留一行");
    return;
  }
  const { zhCount, enCount, unequal } = lineStats.value;
  if (unequal) {
    confirmModalTitle.value = "行数不一致";
    confirmModalText.value = `中英行数不一致（中文${zhCount}行/英文${enCount}行），确认继续？`;
    confirmModalKind.value = "unequal";
    confirmModalOpen.value = true;
    return;
  }
  checkOt1AndConfirm();
}

function backToRaw() {
  const ch = currentChapter.value;
  if (!ch) return;
  ch.phase = 1;
}

function buildFeastsArray() {
  const { typeCode, subject, book_name_zh, book_name_en, bookTagId } = getBookMeta();
  const records = [];

  const bookText = `${book_name_zh}，${subject}`;
  records.push({
    index: getIndex("bookname"),
    id: bookTagId,
    text: bookText,
    zh: bookText,
    en: book_name_en,
    title: bookText,
    type: "bookname",
    tags: [["查看目录", bookTagId]],
    source: [bookText, book_name_en],
  });

  chapters.value.forEach((ch, idx) => {
    if (!ch.confirmed) return;
    const msgNum = idx + 1;
    const msgPrefix = `${bookTagId}_${msgNum}`;
    const title_zh = (ch.title_zh || "").trim();
    let paraCount = 0;

    ch.lines.forEach((line, lineIdx) => {
      const zh = (line.zh || "").trim();
      const en = (line.en || "").trim();
      if (!zh && !en) return;

      const type = getType(zh);
      const lineId = `${msgPrefix}-${lineIdx + 1}`;

      let source;
      if (type === "title") {
        source = [
          `（${book_name_zh}，第${toChineseNum(msgNum)}篇，篇题）`,
          `(${book_name_en}, msg. ${msgNum})`,
        ];
      } else if (type === "bible_reading") {
        source = [
          `（${book_name_zh}，第${toChineseNum(msgNum)}篇，读经）`,
          `(${book_name_en}, msg. ${msgNum})`,
        ];
      } else {
        paraCount += 1;
        source = [
          `（${book_name_zh}，第${toChineseNum(msgNum)}篇，第${toChineseNum(paraCount)}段）`,
          `(${book_name_en}, msg. ${msgNum})`,
        ];
      }

      records.push({
        index: getIndex(type),
        id: lineId,
        text: zh,
        zh,
        en,
        title: type === "title" ? `${book_name_zh}，${zh}` : `${book_name_zh}，${title_zh}`,
        type,
        tags: [
          ["查看整篇", `${bookTagId}_${msgNum}`],
          ["只看大纲", `${bookTagId}_${msgNum}-heading`],
        ],
        source,
      });
    });
  });

  return records;
}

function buildMapBookname() {
  const { subject, book_name_zh, mapBookId } = getBookMeta();
  const msg = [
    { text: book_name_zh, type: "bookname" },
    { text: `总题：${subject}`, type: "bookname" },
  ];

  chapters.value.forEach((ch) => {
    if (!ch.confirmed) return;
    const title_zh = (ch.title_zh || "").trim();
    if (title_zh) {
      msg.push({ text: title_zh, type: "map_title" });
    }
    ch.lines.forEach((line) => {
      const zh = (line.zh || "").trim();
      if (zh && getType(zh) === "ot1") {
        msg.push({ text: zh, type: "map_heading" });
      }
    });
  });

  return {
    index: ["map_feasts_bookname"],
    sn: bsn.value + 1,
    id: mapBookId,
    source: book_name_zh,
    text: subject,
    msg,
  };
}

function buildMapTitles() {
  const { subject, book_name_zh } = getBookMeta();
  const list = [];
  let msgIndex = 0;

  chapters.value.forEach((ch) => {
    if (!ch.confirmed) return;
    msgIndex += 1;
    const title_zh = (ch.title_zh || "").trim();
    const msg = [
      { text: book_name_zh, type: "bookname" },
      { text: `总题：${subject}`, type: "bookname" },
      { text: title_zh, type: "title" },
    ];
    ch.lines.forEach((line) => {
      const zh = (line.zh || "").trim();
      if (zh && getType(zh) === "ot1") {
        msg.push({ text: zh, type: "map_heading" });
      }
    });

    list.push({
      index: ["map_feasts_title"],
      sn: csn.value + msgIndex,
      id: `map_feasts_title-${csn.value + msgIndex}`,
      source: `${book_name_zh}，${subject}`,
      text: title_zh,
      msg,
    });
  });

  return list;
}

function precheckFeasts(feastsData) {
  const emptyEn = [];
  const invalidTypes = [];
  const idCounts = new Map();

  feastsData.forEach((record) => {
    if (record.en === "") {
      const zh = (record.zh || record.text || "").trim();
      emptyEn.push(zh.slice(0, 20));
    }
    if (!VALID_FEAST_TYPES.includes(record.type)) {
      invalidTypes.push(`id=${record.id}，type=${record.type}`);
    }
    idCounts.set(record.id, (idCounts.get(record.id) || 0) + 1);
  });

  const duplicateIds = [...idCounts.entries()]
    .filter(([, count]) => count > 1)
    .map(([id]) => id);

  return {
    emptyEn,
    invalidTypes,
    duplicateIds,
    hasIssues: emptyEn.length > 0 || invalidTypes.length > 0 || duplicateIds.length > 0,
  };
}

function buildDownloadPayload() {
  return {
    feastsData: buildFeastsArray(),
    mapBook: buildMapBookname(),
    mapTitles: buildMapTitles(),
    confirmedCount: chapters.value.filter((ch) => ch.confirmed).length,
  };
}

function buildSequenceConfirmText(confirmedCount) {
  const parts = [];
  if (downloadMapBookname.value) {
    parts.push(`bsn = ${bsn.value + 1}`);
  }
  if (downloadMapTitle.value) {
    parts.push(`csn = ${csn.value + 1} 至 ${csn.value + confirmedCount}（共 ${confirmedCount} 篇）`);
  }
  return `本次将写入：${parts.join("，")}`;
}

async function executeDownload(payload) {
  const { feastsData, mapBook, mapTitles, confirmedCount } = payload;
  const downloadedFiles = [];

  if (downloadFeasts.value) {
    downloadJson("feasts.json", feastsData);
    downloadedFiles.push("feasts.json");
    await sleep(300);
  }

  if (downloadMapBookname.value) {
    downloadJson("map_feasts_bookname.json", [mapBook]);
    downloadedFiles.push("map_feasts_bookname.json");
    await sleep(300);
  }

  if (downloadMapTitle.value) {
    downloadJson("map_feasts_title.json", mapTitles);
    downloadedFiles.push("map_feasts_title.json");
    await sleep(300);
  }

  const fileLabel = `${downloadedFiles.length} 个 JSON 文件`;

  if (needsSequenceUpdate.value) {
    const newBsn = downloadMapBookname.value ? bsn.value + 1 : bsn.value;
    const newCsn = downloadMapTitle.value ? csn.value + confirmedCount : csn.value;
    const ok = await saveSequence(newBsn, newCsn);
    if (ok) {
      message.success(`已下载 ${fileLabel}，序号已更新（bsn=${newBsn}, csn=${newCsn}）`);
    } else {
      message.success(`已下载 ${fileLabel}`);
    }
  } else {
    message.success(`已下载 ${fileLabel}`);
  }
}

async function proceedDownload() {
  downloading.value = true;
  try {
    const payload = buildDownloadPayload();
    const issues = precheckFeasts(payload.feastsData);

    if (issues.hasIssues) {
      precheckIssues.value = issues;
      pendingDownloadPayload.value = payload;
      precheckModalOpen.value = true;
      return;
    }

    await executeDownload(payload);
  } catch (e) {
    message.error(e.message || "生成或下载失败");
  } finally {
    downloading.value = false;
  }
}

async function onSequenceConfirmOk() {
  await proceedDownload();
}

async function onPrecheckConfirmOk() {
  const payload = pendingDownloadPayload.value;
  pendingDownloadPayload.value = null;
  if (!payload) return;

  downloading.value = true;
  try {
    await executeDownload(payload);
  } catch (e) {
    message.error(e.message || "下载失败");
  } finally {
    downloading.value = false;
  }
}

function onPrecheckCancel() {
  pendingDownloadPayload.value = null;
}

async function saveSequence(newBsn, newCsn) {
  const headers = getAuthHeaders();
  if (!headers) return false;
  try {
    await axios.post(
      `${apiBase}/api/feast/sequence`,
      { bsn: newBsn, csn: newCsn },
      { headers }
    );
    bsn.value = newBsn;
    csn.value = newCsn;
    return true;
  } catch (e) {
    message.error("序号更新失败，请手动调整 bsn/csn");
    return false;
  }
}

async function onDownload() {
  if (downloading.value) return;
  if (!validateDownloadInputs()) return;

  if (needsSequenceUpdate.value) {
    const confirmedCount = chapters.value.filter((ch) => ch.confirmed).length;
    sequenceConfirmText.value = buildSequenceConfirmText(confirmedCount);
    sequenceConfirmOpen.value = true;
    return;
  }

  await proceedDownload();
}

async function loadSequence() {
  const headers = getAuthHeaders();
  if (!headers) return;
  try {
    const res = await axios.get(`${apiBase}/api/feast/sequence`, { headers });
    const data = res.data || {};
    bsn.value = Number(data.bsn) || 0;
    csn.value = Number(data.csn) || 0;
  } catch (e) {
    message.warning("未能读取序号，已使用默认值 0");
  }
}

onMounted(() => {
  loadSequence();
});
</script>

<style scoped>
.feast-maker-wrap {
  min-height: 100vh;
  background: #f5f5f5;
}

.feast-maker-body {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 1em;
  max-width: 1400px;
  margin: 0 auto;
  box-sizing: border-box;
}

.side-nav {
  flex: 0 0 220px;
  width: 220px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.edit-area {
  flex: 1;
  min-width: 0;
}

.info-block,
.chapter-list,
.download-block {
  width: 100%;
}

.chapter-list {
  flex: 1;
  min-height: 200px;
}

.chapter-list :deep(.ant-card-body) {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-bottom: 12px;
}

.field-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
}

.field-row:last-child {
  margin-bottom: 0;
}

.field-label {
  font-size: 12px;
  color: #555;
  font-weight: 500;
}

.field-control {
  width: 100%;
}

.field-hint {
  font-size: 11px;
  color: #8c8c8c;
  margin-top: 2px;
}

.chapter-items {
  max-height: 280px;
  overflow-y: auto;
}

.chapter-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  line-height: 1.4;
  transition: background 0.15s;
}

.chapter-item:hover {
  background: #f0f0f0;
}

.chapter-item.active {
  background: #e6f4ff;
}

.chapter-dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.chapter-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chapter-del {
  flex-shrink: 0;
  opacity: 0;
  color: #ff4d4f !important;
  transition: opacity 0.15s;
  padding: 0 4px;
  height: 22px;
}

.chapter-item:hover .chapter-del {
  opacity: 1;
}

.chapter-del:disabled {
  opacity: 0 !important;
}

.add-chapter-btn {
  margin-top: 4px;
}

.download-options {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}

.download-options :deep(.ant-checkbox-wrapper) {
  font-size: 12px;
  margin-inline-start: 0;
}

.edit-area :deep(.ant-card) {
  min-height: 480px;
}

.phase-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin-bottom: 16px;
}

.col-label {
  font-size: 13px;
  color: #555;
  margin-bottom: 8px;
  font-weight: 500;
}

.stats-bar {
  padding: 8px 12px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 13px;
}

.stats-bar-ok {
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  color: #389e0d;
}

.stats-bar-warn {
  background: #fff2f0;
  border: 1px solid #ffccc7;
  color: #cf1322;
}

.precheck-group {
  margin-bottom: 16px;
}

.precheck-group:last-child {
  margin-bottom: 0;
}

.precheck-group-title {
  font-weight: 600;
  font-size: 13px;
  color: #333;
  margin-bottom: 8px;
}

.precheck-list {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  color: #555;
  max-height: 160px;
  overflow-y: auto;
}

.precheck-list li {
  margin-bottom: 4px;
  word-break: break-all;
}

.lines-split {
  margin-bottom: 16px;
}

.line-list-col {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 520px;
  overflow-y: auto;
}

.line-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.line-num {
  flex: 0 0 28px;
  width: 28px;
  text-align: right;
  color: #999;
  font-size: 12px;
  line-height: 32px;
}

.line-textarea {
  flex: 1;
  min-width: 0;
}

.line-actions {
  flex: 0 0 48px;
  display: flex;
  flex-direction: column;
  gap: 0;
  padding-top: 2px;
}

.line-actions :deep(.ant-btn) {
  padding: 0 4px;
  height: 24px;
  min-width: 24px;
}

.phase-actions {
  margin-top: 20px;
  text-align: center;
}

.phase-actions-split {
  display: flex;
  justify-content: center;
  gap: 12px;
}
</style>

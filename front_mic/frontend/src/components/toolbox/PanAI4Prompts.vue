<script setup>
import { computed, reactive, ref, watch } from "vue";
import axios from "axios";
import { Modal, message } from "ant-design-vue";

const props = defineProps({
  api: { type: String, required: true },
  getAuthHeaders: { type: Function, required: true },
  creator: { type: String, default: "" },
  prompts: { type: Array, default: () => [] },
  focus: { type: Object, default: null },
});
const emit = defineEmits(["reload"]);

const NEED_NAME = "请先填写你的名字";
const selected = reactive({ kind: "current", step: "burden", testId: null });
const detail = ref(null);
const loading = ref(false);
const diff = ref(null);
const diffLabel = ref("");
const showFull = ref(false);
const editing = ref(false);
const form = reactive({ step: "", parentKind: "current", parentTestId: null, parentVersion: "", template: "", note: "" });
const check = ref(null);
const editDiff = ref(null);
const saving = ref(false);
let checkTimer = null;

const promptOf = (step) => props.prompts.find((row) => row.step === step) || null;
const groupTitle = (row) => `${row.name}　${row.label}`;

function formatTime(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function detailMessage(error, fallback) {
  const detail = error.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail.message === "string") return detail.message;
  return fallback;
}

async function openCurrent(step) {
  if (editing.value && !(await confirmLeave())) return;
  editing.value = false;
  Object.assign(selected, { kind: "current", step, testId: null });
  diff.value = null;
  showFull.value = true;
  await loadDetail();
}

async function openTest(test) {
  if (editing.value && !(await confirmLeave())) return;
  editing.value = false;
  Object.assign(selected, { kind: "test", step: test.step, testId: test.id });
  showFull.value = false;
  await loadDetail();
  if (detail.value) await compare("current");
}

async function loadDetail() {
  const headers = props.getAuthHeaders();
  if (!headers) return;
  loading.value = true;
  detail.value = null;
  try {
    const url = selected.kind === "current"
      ? `${props.api}/prompts/${selected.step}/current`
      : `${props.api}/prompt_tests/${selected.testId}`;
    const res = await axios.get(url, { headers });
    detail.value = res.data;
  } catch (error) {
    message.error(detailMessage(error, "读取失败"));
  } finally {
    loading.value = false;
  }
}

async function diffRequest(step, template, against) {
  const headers = props.getAuthHeaders();
  if (!headers) return null;
  const res = await axios.post(`${props.api}/prompt_diff`, { step, template, ...against }, { headers });
  return res.data;
}

function againstFor(kind, source) {
  if (kind === "current") return { against_kind: "current", against_version: promptOf(source.step)?.current_version };
  if (source.parent_kind === "test" || source.parentKind === "test") {
    return { against_kind: "test", against_test_id: source.parent_test_id ?? source.parentTestId };
  }
  return { against_kind: "current", against_version: source.parent_version ?? source.parentVersion };
}

async function compare(kind) {
  if (!detail.value) return;
  try {
    const result = await diffRequest(detail.value.step, detail.value.template, againstFor(kind, detail.value));
    diff.value = result;
    diffLabel.value = kind === "current" ? "当前版" : "底稿";
    showFull.value = false;
  } catch (error) {
    message.error(detailMessage(error, "对比失败"));
  }
}

async function compareEdit(kind) {
  try {
    editDiff.value = await diffRequest(form.step, form.template, againstFor(kind, { ...form, step: form.step }));
    editDiff.value.title = kind === "current" ? "当前版" : "底稿";
  } catch (error) {
    message.error(detailMessage(error, "对比失败"));
  }
}

function startNew(source) {
  const step = source.step;
  const fromTest = source.kind === "test";
  Object.assign(form, {
    step,
    parentKind: fromTest ? "test" : "current",
    parentTestId: fromTest ? source.id : null,
    parentVersion: fromTest ? source.version_name : source.version,
    template: source.template || "",
    note: "",
  });
  editDiff.value = null;
  check.value = null;
  editing.value = true;
  runCheck();
}

function newFromDetail() {
  if (!detail.value) return;
  if (selected.kind === "current") startNew({ kind: "current", step: detail.value.step, version: detail.value.version, template: detail.value.template });
  else startNew({ kind: "test", ...detail.value });
}

function confirmLeave() {
  return new Promise((resolve) => {
    Modal.confirm({
      title: "放弃正在编辑的测试版？",
      content: "尚未保存的内容会丢失。",
      okText: "放弃",
      cancelText: "继续编辑",
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    });
  });
}

async function cancelEdit() {
  if (!(await confirmLeave())) return;
  editing.value = false;
}

async function runCheck() {
  const headers = props.getAuthHeaders();
  if (!headers || !editing.value) return;
  try {
    const res = await axios.post(
      `${props.api}/prompt_tests/check`,
      { step: form.step, template: form.template, parent_kind: form.parentKind, parent_test_id: form.parentTestId },
      { headers }
    );
    check.value = res.data;
  } catch (error) {
    check.value = null;
    message.error(detailMessage(error, "检查失败"));
  }
}

watch(
  () => [form.template, editing.value],
  () => {
    if (!editing.value) return;
    if (checkTimer) clearTimeout(checkTimer);
    checkTimer = setTimeout(runCheck, 300);
    editDiff.value = null;
  }
);

const canSave = computed(() => !!(check.value?.ok && form.note.trim() && !saving.value));

async function save() {
  const name = (props.creator || "").trim();
  if (!name) {
    message.warning(NEED_NAME);
    return;
  }
  if (!form.note.trim()) {
    message.warning("请填写修改说明");
    return;
  }
  const headers = props.getAuthHeaders();
  if (!headers) return;
  saving.value = true;
  try {
    const res = await axios.post(
      `${props.api}/prompt_tests`,
      {
        step: form.step,
        template: form.template,
        change_note: form.note.trim(),
        created_by: name,
        parent_kind: form.parentKind,
        parent_test_id: form.parentTestId,
      },
      { headers }
    );
    editing.value = false;
    message.success(`已保存为 ${res.data.version_name}`);
    emit("reload");
    Object.assign(selected, { kind: "test", step: res.data.step, testId: res.data.id });
    await loadDetail();
    if (detail.value) await compare("parent");
  } catch (error) {
    const detail = error.response?.data?.detail;
    if (detail && Array.isArray(detail.problems)) message.error(`不能保存：${detail.problems.join("；")}`);
    else message.error(detailMessage(error, "保存失败"));
  } finally {
    saving.value = false;
  }
}

async function askDelete() {
  const test = detail.value;
  if (!test || selected.kind !== "test") return;
  const headers = props.getAuthHeaders();
  if (!headers) return;
  let used = 0;
  try {
    const res = await axios.get(`${props.api}/prompt_tests/${test.id}/usage`, { headers });
    used = res.data.used_count || 0;
  } catch {
    used = test.used_count || 0;
  }
  const lines = [`建立人：${test.created_by}。`];
  if (used > 0) lines.push(`已有 ${used} 次运行使用过这个版本。`);
  lines.push("删除后，历史运行的结果与送出的 prompt 仍可查看。");
  Modal.confirm({
    title: `删除测试版 ${test.prompt_name} ${test.version_name}？`,
    content: lines.join(""),
    okText: "删除",
    okType: "danger",
    cancelText: "取消",
    onOk: () => removeTest(test),
  });
}

async function removeTest(test) {
  const headers = props.getAuthHeaders();
  if (!headers) return;
  try {
    await axios.delete(`${props.api}/prompt_tests/${test.id}`, {
      headers,
      params: { deleted_by: (props.creator || "").trim() || undefined },
    });
    message.success(`已删除 ${test.version_name}`);
    emit("reload");
    await openCurrent(test.step);
  } catch (error) {
    message.error(detailMessage(error, "删除失败"));
  }
}

function diffRange(block) {
  return block.from === block.to ? `第 ${block.from} 段` : `第 ${block.from}–${block.to} 段`;
}

function checkMark(name) {
  const count = check.value?.counts?.[name] ?? 0;
  return count === 1;
}

watch(
  () => props.focus,
  async (value) => {
    if (!value?.id) return;
    const test = props.prompts.flatMap((row) => row.tests).find((row) => row.id === value.id);
    if (test) await openTest(test);
  },
  { immediate: true }
);

watch(
  () => props.prompts.length,
  (length) => {
    if (length && !detail.value && !props.focus?.id && !editing.value) openCurrent(selected.step);
  },
  { immediate: true }
);

const title = computed(() => {
  const row = promptOf(editing.value ? form.step : selected.step);
  return row ? groupTitle(row) : "";
});
</script>

<template>
  <section class="section">
    <div class="pv">
      <nav class="pv-list" aria-label="Prompt 版本列表">
        <div v-for="row in prompts" :key="row.step">
          <div class="pv-group-title"><span>{{ groupTitle(row) }}</span><span class="meta">{{ row.tests.length + 1 }} 个版本</span></div>
          <button
            type="button"
            class="pv-item"
            :class="{ selected: !editing && selected.kind === 'current' && selected.step === row.step }"
            @click="openCurrent(row.step)"
          >
            <div class="pv-item-top">
              <span class="pv-name">{{ row.current_version }}</span>
              <span class="chip chip-cur">
                <svg class="icon icon-xs" viewBox="0 0 24 24"><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></svg>
                当前版
              </span>
            </div>
            <div class="pv-line">当前版 · 由代码更新</div>
          </button>
          <button
            v-for="test in row.tests"
            :key="test.id"
            type="button"
            class="pv-item"
            :class="{ selected: !editing && selected.kind === 'test' && selected.testId === test.id }"
            @click="openTest(test)"
          >
            <div class="pv-item-top"><span class="pv-name">{{ test.version_name }}</span><span class="chip chip-test">测试版</span></div>
            <div class="pv-line">{{ test.created_by }} · {{ formatTime(test.created_at) }} · 已用 {{ test.used_count }} 次</div>
            <div class="pv-note">{{ test.change_note }}</div>
          </button>
          <div v-if="editing && form.step === row.step" class="pv-item selected editing">
            <div class="pv-item-top"><span class="pv-name">{{ check?.version_name || "新测试版" }}</span><span class="chip chip-test">编辑中</span></div>
            <div class="pv-line">{{ creator || "（未填名字）" }} · 尚未保存</div>
          </div>
        </div>
        <p class="meta list-foot">当前版只能查看，由代码更新。测试版任何人可建、可删。</p>
      </nav>

      <div v-if="editing" class="pv-main">
        <div class="pv-toolbar">
          <div class="pv-title">
            {{ title }}
            <span class="chip chip-test">新建测试版 · 底稿 {{ form.parentVersion }}{{ form.parentKind === "current" ? "（当前版）" : "" }}</span>
          </div>
          <span class="grow"></span>
          <button type="button" class="btn btn-sm" @click="compareEdit('parent')">和底稿对比</button>
          <button type="button" class="btn btn-sm" @click="compareEdit('current')">和当前版对比</button>
        </div>
        <div class="pv-form">
          <div class="form-grid">
            <div>
              <label class="field-label" for="pv-name">版本名（自动）</label>
              <input id="pv-name" class="input readonly" :value="check?.version_name || ''" readonly />
            </div>
            <div>
              <label class="field-label" for="pv-note">修改说明（必填）</label>
              <input id="pv-note" v-model="form.note" class="input" placeholder="这次改了什么、想测什么" />
            </div>
          </div>
          <div class="editor-wrap">
            <label class="field-label" for="pv-editor">Prompt 全文</label>
            <textarea id="pv-editor" v-model="form.template" class="editor" spellcheck="false" />
          </div>
          <div class="checks">
            <span class="meta">填入位检查</span>
            <template v-if="check">
              <span v-for="name in check.required" :key="name" :class="checkMark(name) ? 'ck-ok' : 'ck-bad'">
                {{ checkMark(name) ? "✓" : "✗" }} {{ "{" + name + "}" }}
              </span>
              <span class="meta">（必须恰好这{{ check.required.length === 1 ? "一个" : check.required.length === 2 ? "两个" : "三个" }}，各一次）</span>
              <span v-for="problem in check.problems" :key="problem" class="ck-bad">{{ problem }}</span>
            </template>
          </div>
          <p v-for="warning in check?.warnings || []" :key="warning" class="warn-line">提醒：{{ warning }}</p>
          <div v-if="editDiff" class="diff-panel">
            <div class="diff-head">
              <span class="diff-title">和{{ editDiff.title }} {{ editDiff.against }} 对比：{{ editDiff.changes ? `改动 ${editDiff.changes} 处` : "没有改动" }}</span>
              <button type="button" class="btn-link" @click="editDiff = null">收起对比</button>
            </div>
            <div class="diff">
              <template v-for="(block, index) in editDiff.blocks" :key="index">
                <div v-if="block.type === 'same'" class="meta">…… {{ diffRange(block) }}未改动 ……</div>
                <div v-else class="diff-line" :class="block.type === 'del' ? 'diff-del' : 'diff-add'">{{ block.text }}</div>
              </template>
            </div>
          </div>
        </div>
        <div class="pv-foot">
          <span class="meta">{{ creator ? "保存后成为新的测试版，不会改动底稿。保存后不能修改。" : NEED_NAME }}</span>
          <div class="foot-actions">
            <button type="button" class="btn" @click="cancelEdit">取消</button>
            <button type="button" class="btn btn-primary" :disabled="!canSave || !creator" @click="save">保存为测试版</button>
          </div>
        </div>
      </div>

      <div v-else class="pv-main">
        <p v-if="loading" class="meta pad">读取中……</p>
        <template v-else-if="detail && selected.kind === 'current'">
          <div class="pv-toolbar">
            <div class="pv-title">{{ title }}　{{ detail.version }} <span class="chip chip-cur">当前版</span></div>
            <span class="grow"></span>
            <button type="button" class="btn btn-sm" @click="newFromDetail">以此为底稿新建</button>
          </div>
          <p class="meta pad-top">当前版只能查看，不能修改或删除。</p>
          <div class="fulltext">{{ detail.template }}</div>
        </template>
        <template v-else-if="detail">
          <div class="pv-toolbar">
            <div class="pv-title">{{ detail.prompt_name }}　{{ detail.version_name }} <span class="chip chip-test">测试版</span></div>
            <span class="meta">{{ detail.created_by }} · {{ formatTime(detail.created_at) }} · 已用 {{ detail.used_count }} 次 · 底稿 {{ detail.parent_version }} · {{ detail.change_note }}</span>
            <span class="grow"></span>
            <button type="button" class="btn btn-sm" @click="newFromDetail">以此为底稿新建</button>
            <button type="button" class="btn btn-sm" @click="compare('parent')">和底稿对比</button>
            <button type="button" class="btn btn-sm" @click="compare('current')">和当前版对比</button>
            <button type="button" class="btn btn-sm" @click="showFull = !showFull">{{ showFull ? "显示对比" : "显示全文" }}</button>
            <button type="button" class="btn btn-sm btn-danger" @click="askDelete">删除</button>
          </div>
          <div v-if="showFull || !diff" class="fulltext">{{ detail.template }}</div>
          <template v-else>
            <div class="diff-head bordered">
              <span class="diff-title">和{{ diffLabel }} {{ diff.against }} 对比：{{ diff.changes ? `改动 ${diff.changes} 处` : "没有改动" }}</span>
              <span class="legend">
                <span><span class="sw sw-del"></span>删去</span>
                <span><span class="sw sw-add"></span>新增</span>
                <span>未改动的段落收起</span>
              </span>
            </div>
            <div class="diff">
              <template v-for="(block, index) in diff.blocks" :key="index">
                <div v-if="block.type === 'same'" class="meta">…… {{ diffRange(block) }}未改动 ……</div>
                <div v-else class="diff-line" :class="block.type === 'del' ? 'diff-del' : 'diff-add'">{{ block.text }}</div>
              </template>
            </div>
          </template>
        </template>
      </div>
    </div>
  </section>
</template>

<style scoped>
.section { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden; }
.meta { font-size: 12px; color: var(--ink-3); }
.btn { height: 36px; padding: 0 14px; border: 1px solid var(--line-strong); background: var(--panel); border-radius: var(--radius-sm); cursor: pointer; display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; color: var(--ink); }
.btn:hover { background: var(--subtle); }
.btn-sm { height: 30px; padding: 0 10px; font-size: 13px; }
.btn.btn-primary { background: var(--primary); border-color: var(--primary); color: #ffffff; font-weight: 700; }
.btn.btn-primary:hover { background: #16304f; color: #ffffff; }
.btn.btn-primary:disabled { background: #e6e6e6; border-color: #d9d9d9; color: #595959; cursor: not-allowed; }
.btn.btn-danger { color: var(--err); border-color: #e3b9b3; }
.pv .btn-link { border: 0; background: none; padding: 0; color: #2f6fdb; cursor: pointer; font-size: 13px; }
.pv .btn-link:hover { color: #1a4fad; text-decoration: underline; }
.icon { width: 16px; height: 16px; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; flex-shrink: 0; }
.icon-xs { width: 12px; height: 12px; }
.chip { display: inline-flex; align-items: center; gap: 6px; height: 22px; padding: 0 9px; border-radius: 11px; font-size: 12px; font-weight: 600; white-space: nowrap; }
.chip-cur { background: var(--primary-soft); color: var(--primary); }
.chip-test { background: var(--test-soft); color: var(--test); }
.pv { display: grid; grid-template-columns: 320px minmax(0, 1fr); min-height: 760px; }
.pv-list { border-right: 1px solid var(--line); background: var(--subtle); padding: 12px; display: flex; flex-direction: column; gap: 14px; overflow: auto; max-height: 900px; }
.pv-group-title { font-size: 13px; font-weight: 700; color: var(--ink-2); padding: 0 4px 6px; display: flex; justify-content: space-between; align-items: center; }
.pv-item { display: block; width: 100%; text-align: left; padding: 10px 12px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--panel); cursor: pointer; margin-bottom: 6px; }
.pv-item:hover { background: #fff; }
.pv-item.selected { border-color: var(--test); box-shadow: 0 0 0 2px var(--test-soft); }
.pv-item.editing { cursor: default; }
.pv-item-top { display: flex; align-items: center; gap: 8px; }
.pv-name { font-weight: 700; font-size: 14px; }
.pv-line { font-size: 12px; color: var(--ink-3); }
.pv-note { font-size: 12px; color: var(--ink-2); }
.list-foot { margin: 0; padding: 0 4px; }
.pv-main { display: flex; flex-direction: column; min-width: 0; }
.pv-toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 14px 20px; border-bottom: 1px solid var(--line); }
.pv-toolbar .grow { flex-grow: 1; }
.pv-title { font-size: 16px; font-weight: 700; display: flex; align-items: center; gap: 10px; }
.pv-form { padding: 16px 20px; display: flex; flex-direction: column; gap: 12px; flex-grow: 1; }
.form-grid { display: grid; grid-template-columns: 200px minmax(0, 1fr); gap: 12px; }
.field-label { display: block; font-size: 12px; color: var(--ink-3); margin-bottom: 4px; }
.input { width: 100%; height: 38px; padding: 0 12px; border: 1px solid var(--line-strong); border-radius: var(--radius-sm); background: var(--panel); }
.input.readonly { background: var(--sunken); }
.editor-wrap { display: flex; flex-direction: column; flex-grow: 1; }
.editor { width: 100%; flex-grow: 1; min-height: 440px; padding: 14px 16px; border: 1px solid var(--line-strong); border-radius: var(--radius-sm); background: var(--panel); line-height: 1.9; font-size: 13.5px; resize: vertical; }
.checks { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; font-size: 13px; }
.ck-ok { color: var(--ok); font-weight: 600; }
.ck-bad { color: var(--err); font-weight: 600; }
.warn-line { margin: 0; font-size: 13px; color: var(--run); }
.pv-foot { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 20px; background: var(--sunken); border-top: 1px solid var(--line); }
.foot-actions { display: flex; gap: 8px; }
.pad { padding: 20px; }
.pad-top { margin: 0; padding: 10px 20px 0; }
.fulltext { padding: 14px 20px; font-size: 13.5px; line-height: 1.95; white-space: pre-wrap; user-select: text; }
.diff-panel { border: 1px solid var(--line); border-radius: var(--radius-sm); overflow: hidden; }
.diff-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 10px 20px; }
.diff-head.bordered { border-bottom: 1px solid var(--line); }
.diff-title { font-size: 13px; font-weight: 700; }
.diff { padding: 14px 20px; font-size: 13.5px; line-height: 1.95; background: var(--subtle); display: flex; flex-direction: column; gap: 2px; }
.diff-line { padding: 1px 8px; border-radius: 4px; white-space: pre-wrap; }
.diff-del { background: #fbe3e0; text-decoration: line-through; color: #8a2a22; }
.diff-add { background: #e2f1df; color: #24542d; }
.legend { display: flex; gap: 14px; font-size: 12px; color: var(--ink-3); align-items: center; }
.sw { display: inline-block; width: 12px; height: 12px; border-radius: 3px; vertical-align: middle; margin-right: 4px; }
.sw-del { background: #fbe3e0; }
.sw-add { background: #e2f1df; }
</style>

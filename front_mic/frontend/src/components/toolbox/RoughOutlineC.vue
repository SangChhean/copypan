<template>
  <div class="container">
    <button class="btn btn-back" type="button" @click="goBack">← 返回</button>
    <h1 class="title">毛胚纲目制作练习</h1>

    <!-- 配置加载失败提示 -->
    <div v-if="configError" class="error-banner">配置加载失败，请刷新页面重试</div>

    <!-- 纲目类型多选 -->
    <div class="section">
      <label class="label">纲目类型</label>
      <div class="type-row">
        <button
          v-for="t in typeOptions"
          :key="t.value"
          type="button"
          class="btn btn-type"
          :class="{ active: selectedTypes.includes(t.value) }"
          :disabled="loading"
          @click="toggleType(t.value)"
        >{{ t.label }}</button>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="input-section">
      <div class="input-row">
        <label class="label">系列名称</label>
        <input v-model="seriesName" class="input" type="text" placeholder="如：二〇二六国殇节特会" :disabled="loading" />
      </div>
      <div class="input-row">
        <label class="label">总题</label>
        <input v-model="mainTitle" class="input" type="text" placeholder="如：极其需要新的复兴" :disabled="loading" />
      </div>
      <div class="input-row">
        <label class="label">篇题</label>
        <input v-model="chapterTitle" class="input" type="text" placeholder="如：第一篇　与主合作带进新的复兴，以结束这个世代" :disabled="loading" />
      </div>
      <div class="input-row">
        <label class="label">原始纲目</label>
        <textarea v-model="rawOutline" class="textarea" rows="12" placeholder="请粘贴原始纲目内容" :disabled="loading" />
      </div>
    </div>

    <!-- 生成按钮 -->
    <div class="btn-row">
      <button
        class="btn btn-primary"
        type="button"
        :disabled="loading || !canGenerate"
        @click="generateAll"
      >
        {{ loading ? `生成中… (已完成 ${completedCount} / 共 ${totalCount} 篇)` : '生成毛胚纲目' }}
      </button>
    </div>
    <p v-if="validateError" class="error-msg">{{ validateError }}</p>

    <!-- 结果区 -->
    <div v-if="results.length > 0" class="results-section">
      <h2 class="results-title">生成结果（{{ results.length }} 篇）</h2>
      <div v-for="(item, idx) in results" :key="idx" class="result-card">
        <div class="result-header">
          <span class="type-badge" :style="{ background: typeColor(item.type) }">
            {{ typeLabel(item.type) }}
          </span>
          <span class="ai-name">{{ item.ai_model }}</span>
          <button v-if="!item.error" class="btn btn-copy" type="button" @click="copyItem(item, idx)">
            {{ copiedIdx === idx ? '已复制' : '复制' }}
          </button>
        </div>
        <div v-if="item.error" class="result-error">{{ item.error }}</div>
        <pre v-else class="result-pre">{{ item.content }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";

const typeOptions = [
  { value: "polish",   label: "润色版" },
  { value: "beginner", label: "初信版（纲目的精粹）" },
  { value: "youth",    label: "青少年版" },
  { value: "truth",    label: "真理加强版" },
  { value: "sharing",  label: "三分钟分享" },
];

const typeColorMap = {
  polish:   "#2c5f8a",
  beginner: "#1e6e44",
  youth:    "#c47d0e",
  truth:    "#6b3fa0",
  sharing:  "#c0392b",
};

function typeColor(t) { return typeColorMap[t] || "#555"; }
function typeLabel(t) { return typeOptions.find(o => o.value === t)?.label || t; }

const seriesName   = ref("");
const mainTitle    = ref("");
const chapterTitle = ref("");
const rawOutline   = ref("");
const selectedTypes = ref([]);
const config       = ref({});
const configError  = ref(false);
const results      = ref([]);
const loading      = ref(false);
const completedCount = ref(0);
const totalCount   = ref(0);
const copiedIdx    = ref(-1);
const validateError = ref("");

const content = computed(() => {
  const parts = [];
  if (seriesName.value.trim())   parts.push(seriesName.value.trim());
  if (mainTitle.value.trim())    parts.push(mainTitle.value.trim());
  if (chapterTitle.value.trim()) parts.push(chapterTitle.value.trim());
  if (rawOutline.value.trim())   parts.push(rawOutline.value.trim());
  return parts.join("\n");
});

const canGenerate = computed(() =>
  content.value.trim().length > 0 && selectedTypes.value.length > 0
);

function toggleType(val) {
  const idx = selectedTypes.value.indexOf(val);
  if (idx === -1) selectedTypes.value.push(val);
  else selectedTypes.value.splice(idx, 1);
}

function buildTasks() {
  const tasks = [];
  for (const type of selectedTypes.value) {
    const count = config.value[type] || 1;
    for (let i = 0; i < count; i++) {
      tasks.push({ type, ai_index: i });
    }
  }
  return tasks;
}

function goBack() { window.location.hash = "/tools"; }

async function copyItem(item, idx) {
  try {
    await navigator.clipboard.writeText(item.content);
    copiedIdx.value = idx;
    setTimeout(() => { copiedIdx.value = -1; }, 2000);
  } catch (_) {}
}

async function generateAll() {
  validateError.value = "";
  if (!rawOutline.value.trim()) {
    validateError.value = "请先输入原始纲目内容";
    return;
  }
  if (selectedTypes.value.length === 0) {
    validateError.value = "请至少选择一种纲目类型";
    return;
  }
  const tasks = buildTasks();
  results.value = [];
  completedCount.value = 0;
  totalCount.value = tasks.length;
  loading.value = true;
  await Promise.allSettled(
    tasks.map(async (task) => {
      try {
        const res = await fetch("/api/testc/rough_outline/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            outline_type: task.type,
            content: content.value,
            ai_index: task.ai_index,
          }),
        });
        const data = await res.json();
        results.value.push({
          type:     data.type,
          ai_model: data.ai_model || "未知",
          ai_index: data.ai_index,
          content:  data.content || "",
          error:    data.error || null,
        });
      } catch (e) {
        results.value.push({
          type:     task.type,
          ai_model: "未知",
          ai_index: task.ai_index,
          content:  "",
          error:    e.message,
        });
      } finally {
        completedCount.value++;
      }
    })
  );
  loading.value = false;
}

onMounted(async () => {
  try {
    const res = await fetch("/api/testc/rough_outline/config");
    config.value = await res.json();
  } catch {
    configError.value = true;
  }
});
</script>

<style scoped>
:global(body) { background-color: #f7f5f0; }

.container {
  max-width: 960px;
  margin: 0 auto;
  padding: 28px 24px;
  background: #f7f5f0;
  color: #2d2d2d;
  font-family: sans-serif;
}
.title {
  font-size: 22px;
  font-weight: 700;
  text-align: center;
  margin-bottom: 24px;
  padding-bottom: 12px;
  border-bottom: 2px solid #dde3e9;
}
.error-banner {
  background: #fdecea;
  color: #c0392b;
  padding: 10px 16px;
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 14px;
}
.input-section { margin-bottom: 20px; }
.input-row { margin-bottom: 14px; }
.section { margin-bottom: 20px; }
.label {
  display: block;
  margin-bottom: 6px;
  font-weight: 600;
  font-size: 15px;
}
.input {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 14px;
  font-size: 15px;
  border: 1.5px solid #dde3e9;
  border-radius: 8px;
  background: #fdfcfb;
  outline: none;
  transition: border-color 0.2s;
}
.input:focus { border-color: #2c5f8a; box-shadow: 0 0 0 3px rgba(44,95,138,0.1); }
.input:disabled { opacity: 0.65; cursor: not-allowed; }
.textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 12px 14px;
  font-size: 15px;
  line-height: 1.8;
  border: 1.5px solid #dde3e9;
  border-radius: 8px;
  background: #fdfcfb;
  resize: vertical;
  outline: none;
  transition: border-color 0.2s;
}
.textarea:focus { border-color: #2c5f8a; box-shadow: 0 0 0 3px rgba(44,95,138,0.1); }
.textarea:disabled { opacity: 0.65; cursor: not-allowed; }
.type-row { display: flex; flex-wrap: wrap; gap: 8px; }
.btn-type {
  padding: 8px 18px;
  font-size: 14px;
  font-weight: 500;
  border: 1.5px solid #dde3e9;
  border-radius: 20px;
  background: #fff;
  color: #555;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-type:hover:not(.active):not(:disabled) { border-color: #2c5f8a; color: #2c5f8a; }
.btn-type.active { background: #2c5f8a; color: #fff; border-color: #2c5f8a; }
.btn-type:disabled { opacity: 0.65; cursor: not-allowed; }
.btn-row { margin-top: 8px; margin-bottom: 8px; }
.btn { cursor: pointer; transition: all 0.2s; }
.btn-primary {
  background: #2c5f8a; color: #fff;
  font-weight: 500; border-radius: 6px;
  padding: 10px 36px; font-size: 16px; border: none;
}
.btn-primary:hover:not(:disabled) { background: #1e4a6e; }
.btn-primary:disabled { opacity: 0.65; cursor: not-allowed; }
.btn-back {
  background: transparent; color: #6b6b6b;
  border: 1.5px solid #dde3e9; border-radius: 6px;
  padding: 6px 14px; font-size: 13px; margin-bottom: 20px;
}
.btn-back:hover { border-color: #2c5f8a; color: #2c5f8a; }
.btn-copy {
  border: 1.5px solid #2c5f8a; color: #2c5f8a;
  background: #fff; border-radius: 4px;
  padding: 4px 12px; font-size: 12px;
}
.btn-copy:hover { background: #e8f0f7; }
.error-msg { color: #c0392b; font-size: 13px; margin-top: 4px; }
.results-section { margin-top: 28px; }
.results-title {
  font-size: 16px; font-weight: 600;
  margin-bottom: 16px; color: #2c5f8a;
}
.result-card {
  background: #fff;
  border: 1px solid #dde3e9;
  border-radius: 10px;
  padding: 18px 20px;
  margin-bottom: 16px;
  box-shadow: 0 2px 8px rgba(44,95,138,0.06);
}
.result-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.type-badge {
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 12px;
}
.ai-name {
  font-size: 13px;
  color: #666;
  flex: 1;
}
.result-error {
  color: #c0392b;
  font-size: 13px;
  padding: 8px;
  background: #fdecea;
  border-radius: 6px;
}
.result-pre {
  white-space: pre-wrap;
  line-height: 1.8;
  font-size: 15px;
  color: #2d2d2d;
  margin: 0;
  font-family: inherit;
}
</style>

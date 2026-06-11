<script setup>
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { LeftOutlined, DownloadOutlined } from "@ant-design/icons-vue";

const router = useRouter();
const toast = ref("");
const config = ref({});
const configError = ref(false);
const selectedTypes = ref([]);
const inputContent = ref("");
const inputLine1 = ref("");
const inputLine2 = ref("");
const inputLine3 = ref("");
const results = ref([]);
const loading = ref(false);
const totalTasks = ref(0);
const completedTasks = ref(0);

const TYPE_LABELS = {
  polish:   "润色版",
  beginner: "初信版",
  youth:    "青少年版",
  truth:    "真理加强版",
  sharing:  "三分钟分享",
};

function showToast(msg) {
  toast.value = msg;
  setTimeout(() => { if (toast.value === msg) toast.value = ""; }, 2500);
}

onMounted(async () => {
  try {
    const res = await fetch("/api/testa/rough_outline/config");
    if (!res.ok) throw new Error("配置加载失败");
    config.value = await res.json();
  } catch (e) {
    configError.value = true;
  }
});

function toggleType(type) {
  const idx = selectedTypes.value.indexOf(type);
  if (idx >= 0) selectedTypes.value.splice(idx, 1);
  else selectedTypes.value.push(type);
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

function totalCount() {
  return selectedTypes.value.reduce((sum, t) => sum + (config.value[t] || 1), 0);
}

async function generateAll() {
  if (!inputContent.value.trim()) {
    showToast("请先输入原始纲目内容");
    return;
  }
  if (selectedTypes.value.length === 0) {
    showToast("请至少选择一种类型");
    return;
  }
  const tasks = buildTasks();
  totalTasks.value = tasks.length;
  completedTasks.value = 0;
  loading.value = true;
  results.value = tasks.map(t => ({
    type: t.type,
    ai_index: t.ai_index,
    ai_model: "",
    content: "",
    error: null,
    done: false,
  }));

  await Promise.allSettled(
    tasks.map(async (task, idx) => {
      try {
        const res = await fetch("/api/testa/rough_outline/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            outline_type: task.type,
            content: [
              inputLine1.value.trim(),
              inputLine2.value.trim(),
              inputLine3.value.trim(),
              inputContent.value.trim(),
            ].filter(Boolean).join("\n"),
            ai_index: task.ai_index,
          }),
        });
        const data = await res.json();
        results.value[idx].content = data.content || "";
        results.value[idx].ai_model = data.ai_model || "";
        results.value[idx].error = data.error || null;
      } catch (e) {
        results.value[idx].error = e.message || "请求失败";
      } finally {
        results.value[idx].done = true;
        completedTasks.value += 1;
      }
    })
  );

  loading.value = false;
  showToast("全部完成！");
}

function copyResult(idx) {
  const r = results.value[idx];
  const text = r.content || r.error || "";
  navigator.clipboard.writeText(text).then(() => showToast("已复制到剪贴板"));
}

function clearAll() {
  selectedTypes.value = [];
  inputLine1.value = "";
  inputLine2.value = "";
  inputLine3.value = "";
  inputContent.value = "";
  results.value = [];
  totalTasks.value = 0;
  completedTasks.value = 0;
  loading.value = false;
}

const TYPE_COLORS = {
  polish:   { tag: "tag-polish",   btn: "btn-polish"   },
  beginner: { tag: "tag-beginner", btn: "btn-beginner" },
  youth:    { tag: "tag-youth",    btn: "btn-youth"    },
  truth:    { tag: "tag-truth",    btn: "btn-truth"    },
  sharing:  { tag: "tag-sharing",  btn: "btn-sharing"  },
};
</script>

<template>
  <div class="page">
    <div v-if="toast" class="toast">{{ toast }}</div>

    <div class="header">
      <a-button type="text" class="back-btn" @click="router.back()">
        <template #icon><LeftOutlined /></template>
      </a-button>
      <span class="header-title">毛胚纲目生成</span>
    </div>

    <div v-if="configError" class="error-msg" style="margin: 12px 16px;">
      配置加载失败，请刷新页面重试
    </div>

    <div class="card">
      <div class="field">
        <label class="field-label">纲目类型 <span class="optional">（可多选）</span></label>
        <div class="type-grid">
          <div
            v-for="type in ['polish','beginner','youth','truth','sharing']"
            :key="type"
            class="type-btn"
            :class="[TYPE_COLORS[type].btn, { selected: selectedTypes.includes(type) }]"
            @click="toggleType(type)"
          >
            {{ TYPE_LABELS[type] }}
            <span class="count-badge">×{{ config[type] || '…' }}</span>
          </div>
        </div>
        <div v-if="selectedTypes.length > 0" class="task-hint">
          已选 {{ selectedTypes.length }} 种类型，将发出
          <span class="task-count">{{ totalCount() }}</span> 个请求
        </div>
      </div>

      <div class="field">
        <label class="field-label">第一行 <span class="optional">（可选）</span></label>
        <a-input v-model:value="inputLine1" placeholder="如：二○二五年夏季训练" :disabled="loading" />
      </div>
      <div class="field">
        <label class="field-label">第二行 <span class="optional">（可选）</span></label>
        <a-input v-model:value="inputLine2" placeholder="如：总题：新约中基督与召会的奥秘" :disabled="loading" />
      </div>
      <div class="field">
        <label class="field-label">第三行 <span class="optional">（可选）</span></label>
        <a-input v-model:value="inputLine3" placeholder="如：第一篇　基督是召会的头" :disabled="loading" />
      </div>
      <div class="divider" />

      <div class="field">
        <label class="field-label">原始纲目</label>
        <a-textarea
          v-model:value="inputContent"
          placeholder="请粘贴原始纲目全文…"
          :disabled="loading"
          :auto-size="{ minRows: 6, maxRows: 14 }"
        />
      </div>

      <div class="divider" />
      <div class="action-row">
        <a-button class="clear-btn" :disabled="loading" @click="clearAll">清空</a-button>
        <a-button type="primary" class="generate-btn" :loading="loading" @click="generateAll">
          {{ loading ? "生成中…" : "生成毛胚纲目" }}
        </a-button>
      </div>
    </div>

    <!-- 进度条 -->
    <div v-if="loading || (totalTasks > 0 && completedTasks === totalTasks)" class="card progress-card">
      <div class="progress-row">
        <span class="progress-text">
          已完成 <span class="progress-num">{{ completedTasks }}</span> / 共 {{ totalTasks }} 个
        </span>
        <span v-if="loading" class="progress-status">生成中…</span>
        <span v-else class="progress-done">全部完成</span>
      </div>
      <div class="progress-bar-wrap">
        <div class="progress-bar" :style="{ width: totalTasks ? (completedTasks / totalTasks * 100) + '%' : '0%' }"></div>
      </div>
    </div>

    <!-- 结果列表 -->
    <div v-for="(r, idx) in results" :key="idx" class="card result-card">
      <div class="result-head">
        <span class="type-tag" :class="TYPE_COLORS[r.type].tag">{{ TYPE_LABELS[r.type] }}</span>
        <span v-if="r.done && r.ai_model" class="ai-name">{{ r.ai_model }}</span>
        <span v-if="r.done && r.ai_model" class="ai-index">#{{ r.ai_index + 1 }}</span>
        <button v-if="r.done" class="copy-btn" @click="copyResult(idx)">
          复制
        </button>
      </div>
      <div class="divider" />

      <!-- 生成中 -->
      <div v-if="!r.done" class="loading-row">
        <div class="spinner"></div>
        <span class="loading-text">生成中…</span>
      </div>

      <!-- 错误 -->
      <div v-else-if="r.error" class="result-error">
        生成失败：{{ r.error }}
      </div>

      <!-- 成功 -->
      <pre v-else class="result-body">{{ r.content }}</pre>
    </div>
  </div>
</template>

<style scoped>
.toast {
  position: fixed;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: #52c41a;
  color: #fff;
  padding: 8px 24px;
  border-radius: 20px;
  font-size: 14px;
  z-index: 9999;
  pointer-events: none;
}
.page {
  min-height: 100vh;
  background: #f5f5f5;
  padding-bottom: 40px;
}
.header {
  background: #001529;
  padding: 0 20px;
  height: 52px;
  display: flex;
  align-items: center;
  position: relative;
}
.back-btn {
  color: #55bbff;
  font-size: 18px;
  position: absolute;
  left: 12px;
}
.header-title {
  color: #fff;
  font-size: 16px;
  font-weight: 500;
  flex: 1;
  text-align: center;
}
.card {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  margin: 12px 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.field { margin-bottom: 14px; }
.field:last-child { margin-bottom: 0; }
.field-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: #333;
  margin-bottom: 8px;
}
.optional { font-weight: 400; color: #8c8c8c; font-size: 12px; }
.type-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.type-btn {
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
  border: 1px solid #d9d9d9;
  background: #fafafa;
  color: #8c8c8c;
  cursor: pointer;
  user-select: none;
  transition: all 0.15s;
}
.count-badge {
  font-size: 11px;
  margin-left: 4px;
  opacity: 0.7;
}
.btn-polish.selected   { background: #f0f5ff; border-color: #adc6ff; color: #2f54eb; }
.btn-beginner.selected { background: #f6ffed; border-color: #b7eb8f; color: #389e0d; }
.btn-youth.selected    { background: #fff7e6; border-color: #ffd591; color: #d46b08; }
.btn-truth.selected    { background: #f9f0ff; border-color: #d3adf7; color: #722ed1; }
.btn-sharing.selected  { background: #fff0f6; border-color: #ffadd2; color: #c41d7f; }
.task-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #8c8c8c;
}
.task-count { color: #1890ff; font-weight: 500; }
.divider { height: 1px; background: #f0f0f0; margin: 12px 0; }
.action-row { display: flex; gap: 10px; justify-content: flex-end; }
.clear-btn { font-weight: 500; border-color: #d9d9d9; color: #666; }
.generate-btn { background: #1890ff; border-color: #1890ff; min-width: 120px; font-weight: 500; }
.error-msg {
  color: #cf1322;
  font-size: 13px;
  padding: 8px 12px;
  background: #fff2f0;
  border-radius: 6px;
  border: 1px solid #ffccc7;
}
.progress-card { padding: 12px 16px; }
.progress-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.progress-text { font-size: 13px; color: #555; }
.progress-num { color: #1890ff; font-weight: 500; }
.progress-status { font-size: 12px; color: #8c8c8c; }
.progress-done { font-size: 12px; color: #52c41a; font-weight: 500; }
.progress-bar-wrap {
  height: 4px;
  background: #f0f0f0;
  border-radius: 2px;
}
.progress-bar {
  height: 4px;
  background: #1890ff;
  border-radius: 2px;
  transition: width 0.3s ease;
}
.result-card { padding: 14px 16px; }
.result-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.type-tag {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 10px;
  border-radius: 20px;
}
.tag-polish   { background: #f0f5ff; border: 1px solid #adc6ff; color: #2f54eb; }
.tag-beginner { background: #f6ffed; border: 1px solid #b7eb8f; color: #389e0d; }
.tag-youth    { background: #fff7e6; border: 1px solid #ffd591; color: #d46b08; }
.tag-truth    { background: #f9f0ff; border: 1px solid #d3adf7; color: #722ed1; }
.tag-sharing  { background: #fff0f6; border: 1px solid #ffadd2; color: #c41d7f; }
.ai-name { font-size: 12px; color: #555; font-weight: 500; }
.ai-index { font-size: 11px; color: #aaa; }
.copy-btn {
  margin-left: auto;
  background: #fff;
  border: 1px solid #d9d9d9;
  color: #555;
  padding: 3px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
}
.copy-btn:hover { color: #1890ff; border-color: #1890ff; }
.loading-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
}
.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid #f0f0f0;
  border-top-color: #1890ff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}
@keyframes spin { to { transform: rotate(360deg); } }
.loading-text { font-size: 13px; color: #aaa; }
.result-error {
  font-size: 13px;
  color: #cf1322;
  padding: 8px 0;
  background: #fff2f0;
  border-radius: 4px;
  padding: 8px 10px;
}
.result-body {
  font-size: 13px;
  color: #333;
  line-height: 1.9;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
}
</style>

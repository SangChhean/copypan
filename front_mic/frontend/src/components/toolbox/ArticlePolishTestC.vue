<template>
  <ToolsHeader title="文章润色练习" />
  <div class="page">
    <div class="tab-bar">
      <button
        v-for="tab in TABS"
        :key="tab.key"
        type="button"
        class="tab-btn"
        :class="{ active: activeTab === tab.key }"
        @click="switchTab(tab.key)"
      >
        {{ tab.label }}
      </button>
    </div>

    <a-card class="main-card">
      <!-- Tab 1：通用类 -->
      <div v-if="activeTab === 'polish'" class="option-section">
        <div class="section-label">润色风格</div>
        <a-checkbox-group v-model:value="selectedStyles" class="style-checks" :disabled="loading">
          <a-checkbox v-for="(meta, key) in styles" :key="key" :value="key">
            {{ meta.label }}
          </a-checkbox>
        </a-checkbox-group>

        <div class="ministry-row">
          <a-checkbox v-model:checked="addMinistryColor" :disabled="loading">
            <span class="ministry-label">体现主恢复色彩</span>
          </a-checkbox>
          <span class="ministry-hint">（勾选后将在润色指令中附加：体现主恢复而非一般宗教色彩）</span>
        </div>
      </div>

      <!-- Tab 2：恩典陵园 -->
      <div v-else-if="activeTab === 'memorial'" class="option-section">
        <div class="section-label">润色角色</div>
        <div class="role-list">
          <button
            v-for="(meta, key) in roles"
            :key="key"
            type="button"
            class="role-card"
            :class="{ active: selectedRole === key }"
            :disabled="loading"
            @click="toggleRole(key)"
          >
            <div class="role-label">{{ meta.label }}</div>
            <div class="role-desc">{{ meta.desc }}</div>
          </button>
        </div>
      </div>

      <!-- Tab 3：召会通讯见证类 -->
      <div v-else class="option-section">
        <div class="section-label">文章类型</div>
        <div class="church-grid">
          <button
            v-for="(meta, key) in churchTypes"
            :key="key"
            type="button"
            class="church-btn"
            :class="{ active: selectedChurchType === key }"
            :disabled="loading"
            @click="toggleChurchType(key)"
          >
            {{ meta.label }}
          </button>
        </div>
      </div>

      <a-divider style="margin: 16px 0" />

      <a-textarea
        v-model:value="article"
        class="content-area"
        :rows="12"
        placeholder="请粘贴需要润色的文章..."
        :disabled="loading"
      />
      <div class="char-hint">已输入 {{ inputCharCount }} 字</div>

      <div class="action-row">
        <button
          type="button"
          class="action-btn"
          :disabled="loading"
          @click="runPolish"
        >
          <LoadingOutlined v-if="loading" class="btn-spin" />
          {{ loading ? "润色中…" : "润色" }}
        </button>
        <button type="button" class="clear-btn" :disabled="loading" @click="clearAll">
          清空
        </button>
      </div>
    </a-card>

    <div v-if="loading && !result && !results.length" class="loading-hint">
      <LoadingOutlined class="btn-spin" /> 润色中…
    </div>

    <div v-if="error && !result && !results.length" class="error-block">{{ error }}</div>

    <div v-if="result || results.length" class="results-section">
      <!-- Tab 1：多块结果 -->
      <template v-if="activeTab === 'polish'">
        <a-card
          v-for="item in results"
          :key="item.style"
          class="result-card result-fade"
        >
          <template #title>
            <div class="result-head">
              <span>{{ item.label }}</span>
              <button
                type="button"
                class="copy-btn"
                :disabled="!item.result"
                @click="copyText(item.result, item.style)"
              >
                {{ copiedKey === item.style ? "已复制 ✓" : "复制" }}
              </button>
            </div>
          </template>
          <div v-if="item.error" class="error">{{ item.error }}</div>
          <a-textarea
            v-else
            :value="item.result"
            class="result-textarea"
            :rows="10"
            readonly
          />
          <div v-if="item.result" class="char-hint">共 {{ item.result.length }} 字</div>
        </a-card>
      </template>

      <!-- Tab 2 / 3：单块结果 -->
      <a-card v-else class="result-card result-fade">
        <template #title>
          <div class="result-head">
            <span>润色结果</span>
            <button
              type="button"
              class="copy-btn"
              :disabled="!result"
              @click="copyText(result, 'single')"
            >
              {{ copiedKey === 'single' ? "已复制 ✓" : "复制" }}
            </button>
          </div>
        </template>
        <div v-if="error" class="error">{{ error }}</div>
        <a-textarea
          v-else
          v-model:value="result"
          class="result-textarea"
          :rows="14"
          readonly
        />
        <div v-if="result && !error" class="char-hint">共 {{ resultCharCount }} 字</div>
      </a-card>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from "vue";
import { LoadingOutlined } from "@ant-design/icons-vue";
import ToolsHeader from "./ToolsHeader.vue";

const TABS = [
  { key: "polish", label: "通用类" },
  { key: "memorial", label: "恩典陵园" },
  { key: "church", label: "召会通讯见证类" },
];

const activeTab = ref("polish");
const article = ref("");
const result = ref("");
const results = ref([]);
const loading = ref(false);
const error = ref("");
const copiedKey = ref("");
const selectedStyles = ref([]);
const addMinistryColor = ref(false);
const styles = ref({});
const selectedRole = ref("");
const roles = ref({});
const selectedChurchType = ref("");
const churchTypes = ref({});

const inputCharCount = computed(() => (article.value || "").length);
const resultCharCount = computed(() => (result.value || "").length);

async function apiFetch(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    let detail = data.detail;
    if (Array.isArray(detail)) {
      detail = detail.map((x) => x?.msg || JSON.stringify(x)).join("；");
    }
    throw new Error(detail || data.message || `请求失败（${res.status}）`);
  }
  return data;
}

async function loadStyles() {
  try {
    styles.value = await apiFetch("/api/testc/styles");
  } catch (e) {
    console.error("加载风格失败:", e);
  }
}

async function loadRoles() {
  try {
    roles.value = await apiFetch("/api/testc/roles");
  } catch (e) {
    console.error("加载角色失败:", e);
  }
}

async function loadChurchTypes() {
  try {
    churchTypes.value = await apiFetch("/api/mic/church-types");
  } catch (e) {
    console.error("加载召会类型失败:", e);
  }
}

onMounted(() => {
  loadStyles();
  loadRoles();
  loadChurchTypes();
});

watch(activeTab, () => {
  article.value = "";
  result.value = "";
  results.value = [];
  error.value = "";
  selectedStyles.value = [];
  selectedRole.value = "";
  selectedChurchType.value = "";
  copiedKey.value = "";
});

function switchTab(key) {
  activeTab.value = key;
}

function toggleRole(key) {
  selectedRole.value = selectedRole.value === key ? "" : key;
}

function toggleChurchType(key) {
  selectedChurchType.value = selectedChurchType.value === key ? "" : key;
}

function validateBeforePolish() {
  error.value = "";
  if (!(article.value || "").trim()) {
    error.value = "请输入文章内容";
    return false;
  }
  if (activeTab.value === "polish" && selectedStyles.value.length === 0) {
    error.value = "请至少选择一种风格";
    return false;
  }
  if (activeTab.value === "memorial" && !selectedRole.value) {
    error.value = "请先选择角色";
    return false;
  }
  if (activeTab.value === "church" && !selectedChurchType.value) {
    error.value = "请先选择类型";
    return false;
  }
  return true;
}

async function runPolishGeneral() {
  results.value = selectedStyles.value.map((style) => ({
    style,
    label: styles.value[style]?.label || style,
    result: "",
    error: null,
  }));

  const tasks = selectedStyles.value.map(async (style) => {
    try {
      const data = await apiFetch("/api/testc/polish", {
        method: "POST",
        body: JSON.stringify({
          article: article.value,
          style,
          add_ministry_color: addMinistryColor.value,
        }),
      });
      return { style, result: data.result || "", error: null };
    } catch (e) {
      return { style, result: "", error: e.message || "润色失败" };
    }
  });

  const settled = await Promise.all(tasks);
  results.value = selectedStyles.value.map((style) => {
    const hit = settled.find((s) => s.style === style);
    return {
      style,
      label: styles.value[style]?.label || style,
      result: hit?.result || "",
      error: hit?.error || null,
    };
  });
}

async function runPolish() {
  if (!validateBeforePolish()) return;
  loading.value = true;
  error.value = "";
  result.value = "";
  results.value = [];
  copiedKey.value = "";

  try {
    if (activeTab.value === "polish") {
      await runPolishGeneral();
    } else if (activeTab.value === "memorial") {
      const data = await apiFetch("/api/testc/memorial", {
        method: "POST",
        body: JSON.stringify({ article: article.value, role: selectedRole.value }),
      });
      result.value = data.result || "";
    } else {
      const data = await apiFetch("/api/mic/church-polish", {
        method: "POST",
        body: JSON.stringify({ article: article.value, type: selectedChurchType.value }),
      });
      result.value = data.result || "";
    }
  } catch (e) {
    error.value = e.message || "润色失败，请稍后重试";
  } finally {
    loading.value = false;
  }
}

function clearAll() {
  article.value = "";
  result.value = "";
  results.value = [];
  error.value = "";
  selectedStyles.value = [];
  addMinistryColor.value = false;
  selectedRole.value = "";
  selectedChurchType.value = "";
  copiedKey.value = "";
}

function copyText(text, key) {
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    copiedKey.value = key;
    setTimeout(() => {
      copiedKey.value = "";
    }, 2000);
  });
}
</script>

<style scoped>
.page {
  padding: 1em;
  max-width: 900px;
  width: 100%;
  margin: 0 auto;
}

.tab-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.tab-btn {
  padding: 8px 20px;
  font-size: 15px;
  font-weight: 500;
  border: 2px solid #d9d9d9;
  border-radius: 6px;
  background: #fafafa;
  cursor: pointer;
  transition: all 0.2s;
}
.tab-btn:hover {
  border-color: #1890ff;
  color: #1890ff;
}
.tab-btn.active {
  background: #1890ff;
  border-color: #1890ff;
  color: #fff;
}

.main-card,
.result-card {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.06);
}

.section-label {
  font-weight: 600;
  color: #333;
  margin-bottom: 10px;
  font-size: 0.95em;
}

.style-checks {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
}

.ministry-row {
  margin-top: 14px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.ministry-label {
  font-weight: 500;
  color: #333;
}
.ministry-hint {
  color: #8c8c8c;
  font-size: 0.88em;
}

.role-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.role-card {
  text-align: left;
  padding: 12px 14px;
  border: 2px solid #e8e8e8;
  border-radius: 8px;
  background: #fafafa;
  cursor: pointer;
  transition: all 0.2s;
}
.role-card:hover:not(:disabled) {
  border-color: #1890ff;
}
.role-card.active {
  border-color: #1890ff;
  background: #e6f4ff;
}
.role-card:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}
.role-label {
  font-weight: 600;
  color: #333;
  margin-bottom: 4px;
}
.role-desc {
  font-size: 0.88em;
  color: #666;
  line-height: 1.5;
}

.church-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.church-btn {
  padding: 12px 10px;
  font-size: 14px;
  font-weight: 500;
  border: 2px solid #d9d9d9;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  transition: all 0.2s;
}
.church-btn:hover:not(:disabled) {
  border-color: #1890ff;
  color: #1890ff;
}
.church-btn.active {
  background: #1890ff;
  border-color: #1890ff;
  color: #fff;
}
.church-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.content-area :deep(.ant-input),
.result-textarea :deep(.ant-input) {
  border-radius: 8px;
  font-family: inherit;
  font-size: 16px;
  line-height: 1.8;
  width: 100%;
}

.content-area :deep(textarea.ant-input) {
  min-height: 200px;
}

.char-hint {
  margin-top: 6px;
  font-size: 0.85em;
  color: #8c8c8c;
}

.action-row {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
  display: flex;
  gap: 12px;
  justify-content: center;
  flex-wrap: wrap;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: #1890ff;
  color: #fff;
  border: none;
  padding: 8px 24px;
  border-radius: 6px;
  font-size: 16px;
  cursor: pointer;
  transition: background 0.2s;
}
.action-btn:hover:not(:disabled) {
  background: #40a9ff;
}
.action-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.clear-btn {
  background: #fff;
  color: #666;
  border: 1px solid #d9d9d9;
  padding: 6px 16px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}
.clear-btn:hover:not(:disabled) {
  color: #ff4d4f;
  border-color: #ff4d4f;
  background: #fff1f0;
}
.clear-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.loading-hint {
  margin-top: 16px;
  color: #8c8c8c;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 20px 0;
}

.error-block {
  margin-top: 12px;
  color: #cf1322;
  font-size: 0.95em;
  text-align: center;
}

.results-section {
  margin-top: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.result-fade {
  animation: fadeIn 0.35s ease;
}
@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.result-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.copy-btn {
  background: #fff;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  padding: 4px 10px;
  font-size: 13px;
  color: #555;
  cursor: pointer;
  transition: all 0.2s;
}
.copy-btn:hover:not(:disabled) {
  color: #1890ff;
  border-color: #1890ff;
}
.copy-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error {
  color: #cf1322;
  font-size: 0.95em;
  line-height: 1.5;
  margin-bottom: 8px;
}

.btn-spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>

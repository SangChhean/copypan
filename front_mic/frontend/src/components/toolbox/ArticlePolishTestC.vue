<template>
  <ToolsHeader title="文章润色练习" />
  <div class="page">
    <p class="page-desc">支持通用风格润色、恩典陵园见证稿、召会通讯见证类文章</p>

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

    <a-card class="main-card" :bordered="false">
      <!-- Tab 1：通用类 -->
      <div v-if="activeTab === 'polish'" class="option-section">
        <div class="section-label">润色风格</div>
        <div class="style-tags">
          <label
            v-for="(meta, key) in styles"
            :key="key"
            class="style-tag"
            :class="{ active: selectedStyles.includes(key), disabled: loading }"
          >
            <input
              v-model="selectedStyles"
              type="checkbox"
              :value="key"
              :disabled="loading"
              class="tag-input"
            />
            {{ meta.label }}
          </label>
        </div>

        <div class="ministry-row">
          <label
            class="ministry-tag"
            :class="{ active: addMinistryColor, disabled: loading }"
          >
            <input
              v-model="addMinistryColor"
              type="checkbox"
              :disabled="loading"
              class="tag-input"
            />
            <span class="ministry-label">体现主恢复色彩</span>
          </label>
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

      <a-divider class="section-divider" />

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
          :bordered="false"
        >
          <template #title>
            <div class="result-head">
              <span class="result-title">{{ item.label }}</span>
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
      <a-card v-else class="result-card result-fade" :bordered="false">
        <template #title>
          <div class="result-head">
            <span class="result-title">润色结果</span>
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
:global(body) {
  background-color: #f7f5f0;
}

.page {
  --bg-page: #f7f5f0;
  --bg-card: #ffffff;
  --bg-input: #fdfcfb;
  --color-primary: #2c5f8a;
  --color-primary-light: #e8f0f7;
  --color-primary-hover: #1e4a6e;
  --color-text: #2d2d2d;
  --color-text-secondary: #6b6b6b;
  --color-border: #dde3e9;
  --color-border-active: #2c5f8a;
  --radius-card: 10px;
  --radius-btn: 6px;
  --shadow-card: 0 2px 12px rgba(44, 95, 138, 0.08), 0 1px 3px rgba(0, 0, 0, 0.05);

  background: var(--bg-page);
  background-color: #f7f5f0;
  max-width: 920px;
  margin: 0 auto;
  padding: 28px 24px;
  color: var(--color-text);
}

.page-desc {
  font-size: 14px;
  color: var(--color-text-secondary);
  margin: 0 0 20px;
  line-height: 1.6;
}

.tab-bar {
  display: flex;
  gap: 6px;
  margin-bottom: 20px;
  flex-wrap: wrap;
  background: var(--bg-card);
  border-radius: var(--radius-card);
  padding: 6px;
  box-shadow: var(--shadow-card);
  border: 1px solid var(--color-border);
}

.tab-btn {
  padding: 9px 24px;
  font-size: 15px;
  font-weight: 500;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.2s ease;
}
.tab-btn:hover:not(.active) {
  background: var(--color-primary-light);
  color: var(--color-primary);
}
.tab-btn.active {
  background: var(--color-primary);
  color: #fff;
  box-shadow: 0 2px 8px rgba(44, 95, 138, 0.25);
}

.main-card {
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
  border: 1px solid var(--color-border);
  overflow: hidden;
}
.main-card :deep(.ant-card-body) {
  padding: 24px;
}

.section-label {
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 12px;
  font-size: 15px;
}

.style-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.tag-input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
  pointer-events: none;
}

.style-tag {
  display: inline-flex;
  align-items: center;
  padding: 7px 16px;
  border-radius: 20px;
  font-size: 14px;
  cursor: pointer;
  user-select: none;
  transition: all 0.2s ease;
  background: #fff;
  border: 1.5px solid var(--color-border);
  color: #555;
}
.style-tag:hover:not(.disabled):not(.active) {
  border-color: var(--color-border-active);
  color: var(--color-primary);
}
.style-tag.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
}
.style-tag.disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.ministry-row {
  margin-top: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.ministry-tag {
  display: inline-flex;
  align-items: center;
  padding: 7px 16px;
  border-radius: 20px;
  font-size: 14px;
  cursor: pointer;
  user-select: none;
  transition: all 0.2s ease;
  background: #fff;
  border: 1.5px solid var(--color-border);
  color: #555;
}
.ministry-tag:hover:not(.disabled):not(.active) {
  border-color: #2e7d32;
  color: #2e7d32;
}
.ministry-tag.active {
  background: #2e7d32;
  border-color: #2e7d32;
  color: #fff;
}
.ministry-tag.disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.ministry-label {
  font-weight: 500;
}
.ministry-hint {
  color: #8c8c8c;
  font-size: 13px;
}

.role-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.role-card {
  text-align: left;
  padding: 14px 16px;
  border: 1.5px solid var(--color-border);
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  transition: all 0.2s ease;
}
.role-card:hover:not(:disabled):not(.active) {
  border-color: var(--color-border-active);
  box-shadow: 0 2px 8px rgba(44, 95, 138, 0.1);
}
.role-card.active {
  border: 1.5px solid #2c5f8a;
  border-left: 4px solid #2c5f8a;
  background: #e8f0f7;
  padding-left: 13px;
}
.role-card:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.role-label {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text);
}
.role-desc {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-top: 4px;
  line-height: 1.5;
}

.church-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.church-btn {
  padding: 14px;
  font-size: 14px;
  font-weight: 500;
  border: 1.5px solid var(--color-border);
  border-radius: 8px;
  background: #fff;
  color: var(--color-text);
  cursor: pointer;
  transition: all 0.2s ease;
}
.church-btn:hover:not(:disabled):not(.active) {
  border-color: var(--color-border-active);
  color: var(--color-primary);
}
.church-btn.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
}
.church-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.section-divider :deep(.ant-divider) {
  margin: 20px 0;
  border-color: #e8e8e0;
}

.content-area :deep(textarea.ant-input) {
  background: var(--bg-input);
  border: 1.5px solid var(--color-border);
  border-radius: 8px;
  font-family: inherit;
  font-size: 15px;
  line-height: 1.8;
  padding: 12px;
  min-height: 200px;
  width: 100%;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.content-area :deep(textarea.ant-input:focus) {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(44, 95, 138, 0.12);
}

.result-textarea :deep(textarea.ant-input) {
  background: var(--bg-input);
  border: none;
  border-radius: 0;
  font-size: 15px;
  line-height: 1.9;
  padding: 16px 20px;
  width: 100%;
  resize: none;
}

.char-hint {
  margin-top: 8px;
  font-size: 13px;
  color: #9e9e9e;
  text-align: right;
}

.action-row {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid #e8e8e0;
  display: flex;
  gap: 12px;
  justify-content: center;
  flex-wrap: wrap;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: var(--color-primary);
  color: #fff;
  border: none;
  padding: 10px 36px;
  border-radius: var(--radius-btn);
  font-size: 16px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s ease;
}
.action-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
}
.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.clear-btn {
  background: #fff;
  color: var(--color-text-secondary);
  border: 1.5px solid var(--color-border);
  padding: 10px 24px;
  border-radius: var(--radius-btn);
  font-size: 15px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.clear-btn:hover:not(:disabled) {
  color: #c62828;
  border-color: #c62828;
  background: #fff;
}
.clear-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.loading-hint {
  margin-top: 20px;
  color: #9e9e9e;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 20px 0;
  font-size: 14px;
}

.error-block {
  margin-top: 12px;
  color: #c62828;
  font-size: 14px;
  text-align: center;
}

.results-section {
  margin-top: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.result-card {
  border-radius: var(--radius-card);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}
.result-card :deep(.ant-card-head) {
  background: var(--bg-page);
  border-bottom: 1px solid var(--color-border);
  padding: 12px 20px;
  min-height: auto;
}
.result-card :deep(.ant-card-head-title) {
  padding: 0;
}
.result-card :deep(.ant-card-body) {
  padding: 0;
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

.result-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-primary);
}

.copy-btn {
  background: #fff;
  border: 1.5px solid var(--color-primary);
  border-radius: 4px;
  padding: 4px 12px;
  font-size: 13px;
  color: var(--color-primary);
  cursor: pointer;
  transition: all 0.2s ease;
}
.copy-btn:hover:not(:disabled) {
  background: var(--color-primary-light);
}
.copy-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.error {
  color: #c62828;
  font-size: 14px;
  line-height: 1.5;
  margin: 12px 20px;
}

.btn-spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>

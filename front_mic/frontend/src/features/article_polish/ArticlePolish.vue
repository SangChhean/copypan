<template>
  <ToolsHeader title="文章润色" />
  <div class="box">
    <a-tabs v-model:activeKey="activeTab" class="polish-tabs">

      <!-- ── Tab 一：通用润色 ── -->
      <a-tab-pane key="general" tab="通用润色">
        <a-card>
          <p class="hint">选择一种或多种风格，DeepSeek 将并发生成对应润色版本。</p>
          <a-divider style="margin: 12px 0" />

          <div class="direction-row">
            <span class="label">润色风格：</span>
            <a-checkbox-group v-model:value="selectedStyles">
              <a-checkbox v-for="(meta, key) in STYLE_META" :key="key" :value="key">
                {{ meta.label }}
              </a-checkbox>
            </a-checkbox-group>
          </div>

          <div class="recovery-row">
            <a-checkbox v-model:checked="recoveryAddon">
              <span class="recovery-label">体现主恢复色彩</span>
            </a-checkbox>
            <span class="recovery-hint">（勾选后将在润色指令中附加：体现主恢复而非一般宗教色彩）</span>
          </div>

          <a-divider style="margin: 12px 0" />
          <div class="textarea-wrap">
            <a-textarea
              v-model:value="generalArticle"
              class="content-area"
              :rows="10"
              placeholder="请粘贴需要润色的文章..."
              :disabled="polishingGeneral"
            />
          </div>
          <div class="action-row">
            <button
              type="button"
              class="action-btn"
              :disabled="!canPolishGeneral || polishingGeneral"
              @click="runGeneralPolish"
            >
              <span v-if="polishingGeneral" class="btn-spin">⟳</span>
              {{ polishingGeneral ? "润色中…" : "润色" }}
            </button>
            <button type="button" class="clear-btn" :disabled="polishingGeneral" @click="clearGeneral">清空</button>
          </div>
        </a-card>

        <div v-if="generalError" class="error">{{ generalError }}</div>

        <a-card
          v-for="item in generalResults"
          :key="item.style"
          class="result-card"
        >
          <template #title>
            <div class="result-title-row">
              <span>{{ item.label }}</span>
              <button type="button" class="copy-btn" @click="copyResult(item.result)">复制</button>
            </div>
          </template>
          <div v-if="item.loading" class="panel-loading">
            <LoadingOutlined class="btn-icon btn-spin" /> 润色中…
          </div>
          <div v-else-if="item.error" class="panel-error">{{ item.error }}</div>
          <a-textarea
            v-else
            v-model:value="item.result"
            class="result-textarea"
            :rows="10"
          />
        </a-card>
      </a-tab-pane>

      <!-- ── Tab 二：恩典陵园 ── -->
      <a-tab-pane key="memorial" tab="恩典陵园">
        <a-card>
          <p class="hint">针对已逝弟兄姊妹的见证稿润色，可同时选择多个角色视角对比效果。</p>
          <a-divider style="margin: 12px 0" />

          <div class="direction-row">
            <span class="label">润色角色：</span>
            <a-checkbox-group v-model:value="selectedRoles">
              <a-checkbox v-for="(meta, key) in ROLE_META" :key="key" :value="key">
                {{ meta.label }}
              </a-checkbox>
            </a-checkbox-group>
          </div>
          <div class="role-hints">
            <div class="role-hint-item">
              <span class="role-tag">同工角色</span>适合真理性强、要求精炼有力度的见证稿
            </div>
            <div class="role-hint-item">
              <span class="role-tag">亲友角色</span>适合情感深入、要求感染力强的见证稿
            </div>
            <div class="role-hint-item">
              <span class="role-tag">编辑者角色</span>适合专业严谨通用性强的见证稿
            </div>
          </div>

          <a-divider style="margin: 12px 0" />
          <div class="textarea-wrap">
            <a-textarea
              v-model:value="memorialArticle"
              class="content-area"
              :rows="10"
              placeholder="请粘贴需要润色的见证稿..."
              :disabled="polishingMemorial"
            />
          </div>
          <div class="action-row">
            <button
              type="button"
              class="action-btn"
              :disabled="!canPolishMemorial || polishingMemorial"
              @click="runMemorialPolish"
            >
              <span v-if="polishingMemorial" class="btn-spin">⟳</span>
              {{ polishingMemorial ? "润色中…" : "润色" }}
            </button>
            <button type="button" class="clear-btn" :disabled="polishingMemorial" @click="clearMemorial">清空</button>
          </div>
        </a-card>

        <div v-if="memorialError" class="error">{{ memorialError }}</div>

        <a-card
          v-for="item in memorialResults"
          :key="item.role"
          class="result-card"
        >
          <template #title>
            <div class="result-title-row">
              <span>{{ item.label }}</span>
              <button type="button" class="copy-btn" @click="copyResult(item.result)">复制</button>
            </div>
          </template>
          <div v-if="item.loading" class="panel-loading">
            <LoadingOutlined class="btn-icon btn-spin" /> 润色中…
          </div>
          <div v-else-if="item.error" class="panel-error">{{ item.error }}</div>
          <a-textarea
            v-else
            v-model:value="item.result"
            class="result-textarea"
            :rows="10"
          />
        </a-card>
      </a-tab-pane>

      <!-- ── Tab 三：召会通讯/见证稿 ── -->
      <a-tab-pane key="church" tab="召会/见证稿">
        <a-card>
          <p class="hint">使用 Claude Sonnet 4.6 润色召会通讯或见证类文章，每次生成一个结果。</p>
          <a-divider style="margin: 12px 0" />

          <div class="direction-row" style="margin-bottom: 12px;">
            <span class="label">语言：</span>
            <div class="lang-btn-group">
              <button
                type="button"
                class="lang-btn"
                :class="{ active: churchLang === 'zh' }"
                :disabled="polishingChurch"
                @click="churchLang = 'zh'"
              >中文</button>
              <button
                type="button"
                class="lang-btn"
                :class="{ active: churchLang === 'en' }"
                :disabled="polishingChurch"
                @click="churchLang = 'en'"
              >English</button>
            </div>
          </div>

          <div class="direction-row">
            <span class="label">文章类型：</span>
            <div class="lang-btn-group">
              <button
                type="button"
                class="lang-btn"
                :class="{ active: churchType === 'report' }"
                :disabled="polishingChurch"
                @click="churchType = 'report'"
              >{{ churchLang === 'zh' ? '召会通讯类' : 'Church Report' }}</button>
              <button
                type="button"
                class="lang-btn"
                :class="{ active: churchType === 'testimony' }"
                :disabled="polishingChurch"
                @click="churchType = 'testimony'"
              >{{ churchLang === 'zh' ? '见证类' : 'Testimony' }}</button>
            </div>
          </div>

          <a-divider style="margin: 12px 0" />
          <div class="textarea-wrap">
            <a-textarea
              v-model:value="churchArticle"
              class="content-area"
              :rows="10"
              :placeholder="churchLang === 'zh' ? '请粘贴需要润色的文章...' : 'Paste the article to polish here...'"
              :disabled="polishingChurch"
            />
          </div>
          <div class="action-row">
            <button
              type="button"
              class="action-btn"
              :disabled="!canPolishChurch || polishingChurch"
              @click="runChurchPolish"
            >
              <span v-if="polishingChurch" class="btn-spin">⟳</span>
              {{ polishingChurch ? (churchLang === 'zh' ? '润色中…' : 'Polishing...') : (churchLang === 'zh' ? '润色' : 'Polish') }}
            </button>
            <button type="button" class="clear-btn" :disabled="polishingChurch" @click="clearChurch">
              {{ churchLang === 'zh' ? '清空' : 'Clear' }}
            </button>
          </div>
        </a-card>

        <div v-if="churchError" class="error">{{ churchError }}</div>

        <a-card v-if="churchResult" class="result-card">
          <template #title>
            <div class="result-title-row">
              <span>{{ churchResult.label }}</span>
              <button type="button" class="copy-btn" @click="copyResult(churchResult.result)">
                {{ churchLang === 'zh' ? '复制' : 'Copy' }}
              </button>
            </div>
          </template>
          <div v-if="churchResult.loading" class="panel-loading">
            <LoadingOutlined class="btn-icon btn-spin" />
            {{ churchLang === 'zh' ? '润色中…' : 'Polishing...' }}
          </div>
          <a-textarea
            v-else
            v-model:value="churchResult.result"
            class="result-textarea"
            :rows="12"
          />
        </a-card>
      </a-tab-pane>

    </a-tabs>
  </div>
</template>

<script setup>
import { ref, computed } from "vue";
import axios from "axios";
import { message } from "ant-design-vue";
import { LoadingOutlined } from "@ant-design/icons-vue";
import ToolsHeader from "@/components/toolbox/ToolsHeader.vue";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";

function getAuthToken() {
  const token = localStorage.getItem("token") || null;
  if (!token) {
    window.location.hash = "/login";
  }
  return token;
}

const STYLE_META = {
  formal:         { label: "正式严谨" },
  academic:       { label: "专业学术" },
  concise:        { label: "简洁干练" },
  literary:       { label: "优雅文学" },
  social_media:   { label: "生动新媒体" },
  conversational: { label: "亲切口语" },
  persuasive:     { label: "说服性" },
};

const ROLE_META = {
  coworker: { label: "同工角色" },
  family:   { label: "亲友角色" },
  editor:   { label: "编辑者角色" },
};

// ── 通用润色 ──────────────────────────────────────────────────
const activeTab        = ref("general");
const selectedStyles   = ref([]);
const recoveryAddon    = ref(false);
const generalArticle   = ref("");
const polishingGeneral = ref(false);
const generalResults   = ref([]);
const generalError     = ref("");

const canPolishGeneral = computed(() =>
  selectedStyles.value.length > 0 && (generalArticle.value || "").trim().length > 0
);

async function runGeneralPolish() {
  if (!canPolishGeneral.value) return;
  const authToken = getAuthToken();
  if (!authToken) return;
  polishingGeneral.value = true;
  generalError.value = "";
  generalResults.value = selectedStyles.value.map((s) => ({
    style: s,
    label: STYLE_META[s].label,
    result: "",
    error: null,
    loading: true,
  }));
  try {
    const res = await axios.post(
      `${apiBase}/api/polish/article`,
      {
        article: generalArticle.value,
        styles: selectedStyles.value,
        recovery: recoveryAddon.value,
      },
      { headers: { Authorization: `Bearer ${authToken}` }, timeout: 120000 }
    );
    generalResults.value = (res.data?.results || []).map((r) => ({ ...r, loading: false }));
  } catch (err) {
    generalError.value =
      "润色失败：" + (err.response?.data?.detail || err.message);
    generalResults.value = [];
  } finally {
    polishingGeneral.value = false;
  }
}

function clearGeneral() {
  generalArticle.value = "";
  generalResults.value = [];
  generalError.value = "";
  selectedStyles.value = [];
  recoveryAddon.value = false;
}

// ── 见证稿润色 ────────────────────────────────────────────────
const selectedRoles     = ref([]);
const memorialArticle   = ref("");
const polishingMemorial = ref(false);
const memorialResults   = ref([]);
const memorialError     = ref("");

const canPolishMemorial = computed(() =>
  selectedRoles.value.length > 0 && (memorialArticle.value || "").trim().length > 0
);

async function runMemorialPolish() {
  if (!canPolishMemorial.value) return;
  const authToken = getAuthToken();
  if (!authToken) return;
  polishingMemorial.value = true;
  memorialError.value = "";
  memorialResults.value = selectedRoles.value.map((r) => ({
    role: r,
    label: ROLE_META[r].label,
    result: "",
    error: null,
    loading: true,
  }));
  try {
    const res = await axios.post(
      `${apiBase}/api/polish/memorial`,
      { article: memorialArticle.value, roles: selectedRoles.value },
      { headers: { Authorization: `Bearer ${authToken}` }, timeout: 120000 }
    );
    memorialResults.value = (res.data?.results || []).map((r) => ({ ...r, loading: false }));
  } catch (err) {
    memorialError.value =
      "润色失败：" + (err.response?.data?.detail || err.message);
    memorialResults.value = [];
  } finally {
    polishingMemorial.value = false;
  }
}

function clearMemorial() {
  memorialArticle.value = "";
  memorialResults.value = [];
  memorialError.value = "";
  selectedRoles.value = [];
}

// ── 召会/见证稿润色 ───────────────────────────────────────────
const churchLang      = ref("zh");
const churchType      = ref("report");
const churchArticle   = ref("");
const polishingChurch = ref(false);
const churchResult    = ref(null);
const churchError     = ref("");

const churchTypeKey = computed(() => `${churchLang.value}_${churchType.value}`);

const canPolishChurch = computed(() =>
  (churchArticle.value || "").trim().length > 0
);

async function runChurchPolish() {
  if (!canPolishChurch.value) return;
  const authToken = getAuthToken();
  if (!authToken) return;
  polishingChurch.value = true;
  churchError.value = "";
  churchResult.value = { loading: true, label: "", result: "" };
  try {
    const res = await axios.post(
      `${apiBase}/api/polish/church`,
      { article: churchArticle.value, type_key: churchTypeKey.value },
      { headers: { Authorization: `Bearer ${authToken}` }, timeout: 120000 }
    );
    churchResult.value = { ...res.data, loading: false };
  } catch (err) {
    churchError.value =
      "润色失败：" + (err.response?.data?.detail || err.message);
    churchResult.value = null;
  } finally {
    polishingChurch.value = false;
  }
}

function clearChurch() {
  churchArticle.value = "";
  churchResult.value = null;
  churchError.value = "";
}

function copyResult(text) {
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => message.success("已复制"));
}
</script>

<style scoped>
.box {
  padding: 1em;
  max-width: 720px;
  margin: 0 auto;
}
.box :deep(.ant-card) {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.06);
}
.polish-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 16px;
}

/* 说明 */
.hint {
  color: #555;
  font-size: 0.95em;
  line-height: 1.5;
  margin: 0;
}

/* 方向行 */
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
  white-space: nowrap;
}

/* 主恢复附加选项 */
.recovery-row {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.recovery-label {
  font-weight: 500;
  color: #333;
}
.recovery-hint {
  color: #8c8c8c;
  font-size: 0.88em;
}

/* 角色说明 */
.role-hints {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.role-hint-item {
  font-size: 0.9em;
  color: #555;
  display: flex;
  align-items: center;
  gap: 6px;
}
.role-tag {
  background: #f0f0f0;
  color: #595959;
  border-radius: 4px;
  padding: 1px 7px;
  font-size: 0.88em;
  white-space: nowrap;
}

/* 文本框 */
.textarea-wrap {
  margin-top: 8px;
}
.content-area :deep(.ant-input),
.result-textarea :deep(.ant-input) {
  border-radius: 8px;
  font-family: inherit;
  font-size: 0.95em;
  line-height: 1.6;
}

/* 操作行 */
.action-row {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  justify-content: center;
}
.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
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
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
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

/* 旋转动画 */
.btn-icon {
  font-size: 18px;
}
.btn-spin {
  display: inline-block;
  animation: spin 1s linear infinite;
  margin-right: 4px;
}
@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* 错误 */
.error {
  color: #cf1322;
  margin-top: 12px;
  font-size: 0.95em;
}
.panel-error {
  color: #cf1322;
  padding: 8px 0;
  font-size: 0.95em;
}
.panel-loading {
  color: #8c8c8c;
  padding: 16px 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 结果卡 */
.result-card {
  margin-top: 20px;
}
.result-card :deep(.ant-card-head) {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}
.result-title-row {
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
.copy-btn:hover {
  color: #1890ff;
  border-color: #1890ff;
}

/* 召会 Tab：语言/类型切换 */
.lang-btn-group {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.lang-btn {
  background: #fff;
  border: 2px solid #d9d9d9;
  border-radius: 6px;
  padding: 5px 18px;
  font-size: 14px;
  color: #333;
  cursor: pointer;
  transition: all 0.2s;
}
.lang-btn:hover:not(:disabled) {
  border-color: #1890ff;
  color: #1890ff;
}
.lang-btn.active {
  border-color: #1890ff;
  background: #1890ff;
  color: #fff;
  font-weight: 600;
}
.lang-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}
</style>

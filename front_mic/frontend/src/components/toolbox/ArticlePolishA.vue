<script setup>
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { LeftOutlined } from "@ant-design/icons-vue";

const router = useRouter();

const article = ref("");
const selectedStyle = ref("formal");
const styles = ref({});
const loading = ref(false);
const error = ref(null);
const result = ref(null);
const toast = ref("");
const recoveryTone = ref(false);
const mode = ref("polish");
const selectedRole = ref("coworker");
const memorialArticle = ref("");
const memorialResult = ref(null);
const memorialLoading = ref(false);
const memorialError = ref(null);
const churchLang = ref("zh");
const churchType = ref("church");
const churchArticle = ref("");
const churchResult = ref(null);
const churchLoading = ref(false);
const churchError = ref(null);

const MAX_CHARS = 100000;
const charCount = computed(() => (article.value || "").length);
const churchMode = computed(() => `${churchLang.value}_${churchType.value}`);

onMounted(async () => {
  try {
    const res = await fetch("/api/testa/styles");
    if (res.ok) {
      const data = await res.json();
      styles.value = data;
    }
  } catch (e) {
    console.error("获取风格列表失败", e);
  }
});

const styleLabels = {
  formal: "正式严谨",
  academic: "专业学术",
  concise: "简洁干练",
  literary: "优雅文学",
  social: "生动新媒体",
  conversational: "亲切口语",
  persuasive: "说服营销",
};

const roleLabels = {
  coworker: { label: "同工", desc: "真理性强、精炼有力度" },
  family: { label: "亲友", desc: "深入富有情感表达" },
  editor: { label: "编辑者", desc: "专业严谨、通用性强" },
};

function showToast(msg) {
  toast.value = msg;
  setTimeout(() => {
    if (toast.value === msg) toast.value = "";
  }, 2500);
}

function clearAll() {
  article.value = "";
  result.value = null;
  error.value = null;
}

function copyResult() {
  if (!result.value) return;
  navigator.clipboard.writeText(result.value).then(() => showToast("已复制到剪贴板"));
}

function copyMemorialResult() {
  if (!memorialResult.value) return;
  navigator.clipboard.writeText(memorialResult.value).then(() => showToast("已复制到剪贴板"));
}

async function polishMemorial() {
  const text = (memorialArticle.value || "").trim();
  if (!text) {
    memorialError.value = "请先粘贴需要润色的见证稿";
    return;
  }
  memorialLoading.value = true;
  memorialError.value = null;
  memorialResult.value = null;
  try {
    const res = await fetch("/api/testa/memorial", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ article: text, role: selectedRole.value }),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      memorialError.value = errData.detail || "润色失败，请稍后重试";
      return;
    }
    const data = await res.json();
    if (data.result) {
      memorialResult.value = data.result;
      showToast("润色完成！");
    } else {
      memorialError.value = "润色失败，请稍后重试";
    }
  } catch (e) {
    memorialError.value = (e && e.message) || "网络错误，请稍后重试";
  } finally {
    memorialLoading.value = false;
  }
}

function copyChurchResult() {
  if (!churchResult.value) return;
  navigator.clipboard.writeText(churchResult.value).then(() => showToast("已复制到剪贴板"));
}

async function polishChurch() {
  const text = (churchArticle.value || "").trim();
  if (!text) {
    churchError.value = churchLang.value === "zh" ? "请先粘贴需要润色的文章" : "Please paste the article to polish";
    return;
  }
  churchLoading.value = true;
  churchError.value = null;
  churchResult.value = null;
  try {
    const res = await fetch("/api/testa/church", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ article: text, mode: churchMode.value }),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      churchError.value = errData.detail || "润色失败，请稍后重试";
      return;
    }
    const data = await res.json();
    if (data.result) {
      churchResult.value = data.result;
      showToast(churchLang.value === "zh" ? "润色完成！" : "Polishing complete!");
    } else {
      churchError.value = "润色失败，请稍后重试";
    }
  } catch (e) {
    churchError.value = (e && e.message) || "网络错误，请稍后重试";
  } finally {
    churchLoading.value = false;
  }
}

async function polish() {
  const text = (article.value || "").trim();
  if (!text) {
    error.value = "请先粘贴需要润色的文章";
    return;
  }
  if (text.length > MAX_CHARS) {
    error.value = `文章过长，最多 ${MAX_CHARS.toLocaleString()} 字`;
    return;
  }
  loading.value = true;
  error.value = null;
  result.value = null;
  try {
    const res = await fetch("/api/testa/polish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        article: text,
        style: selectedStyle.value,
        recovery_tone: recoveryTone.value,
      }),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      error.value = errData.detail || errData.error || "润色失败，请稍后重试";
      return;
    }
    const data = await res.json();
    if (data.result) {
      result.value = data.result;
      showToast("润色完成！");
    } else {
      error.value = "润色失败，请稍后重试";
    }
  } catch (e) {
    error.value = (e && e.message) || "网络错误，请稍后重试";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="page">
    <div v-if="toast" class="toast">{{ toast }}</div>

    <div class="header">
      <a-button type="text" class="back-btn" @click="router.back()">
        <template #icon><LeftOutlined /></template>
      </a-button>
      <span class="header-title">文章润色（testA）</span>
    </div>

    <div class="version-bar">
      <div
        class="ver-btn"
        :class="{ active: mode === 'polish' }"
        @click="mode = 'polish'"
      >
        通用润色
      </div>
      <div
        class="ver-btn"
        :class="{ active: mode === 'memorial' }"
        @click="mode = 'memorial'"
      >
        恩典陵园
      </div>
      <div
        class="ver-btn"
        :class="{ active: mode === 'church' }"
        @click="mode = 'church'"
      >
        召会通讯/见证
      </div>
    </div>

    <div v-show="mode === 'polish'">
    <div class="card">
      <div class="field">
        <label class="field-label">润色风格</label>
        <div class="seg-group">
          <div
            v-for="(label, key) in styleLabels"
            :key="key"
            class="seg-btn"
            :class="{ active: selectedStyle === key, disabled: loading }"
            @click="!loading && (selectedStyle = key)"
          >
            {{ label }}
          </div>
        </div>
        <div class="recovery-row">
          <label class="recovery-label">
            <input
              type="checkbox"
              v-model="recoveryTone"
              :disabled="loading"
              class="recovery-checkbox"
            />
            主恢复色彩
          </label>
        </div>
      </div>

      <div class="field">
        <label class="field-label">文章内容 <span class="required">*</span></label>
        <a-textarea
          v-model:value="article"
          placeholder="请粘贴需要润色的文章…"
          :disabled="loading"
          :auto-size="{ minRows: 5, maxRows: 12 }"
        />
        <div class="char-row">
          <span class="char-count">{{ charCount.toLocaleString() }} / 100,000 字</span>
          <a-button class="clear-btn" :disabled="loading" @click="clearAll">清空</a-button>
        </div>
      </div>

      <div class="divider" />

      <div class="action-row">
        <a-button
          class="polish-btn"
          :loading="loading"
          :disabled="loading"
          @click="polish"
        >
          {{ loading ? "润色中…" : "润色" }}
        </a-button>
      </div>
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>

    <div v-if="result" class="card result-card">
      <div class="result-head">
        <span class="result-title">润色结果</span>
        <button class="copy-btn" @click="copyResult">
          <i class="ti ti-copy" aria-hidden="true"></i> 复制
        </button>
      </div>
      <div class="divider" />
      <pre class="result-body">{{ result }}</pre>
    </div>
    </div>

    <div v-show="mode === 'memorial'">
      <div class="card">
        <div class="field">
          <label class="field-label">润色角色</label>
          <div class="role-group">
            <div
              v-for="(info, key) in roleLabels"
              :key="key"
              class="role-btn"
              :class="{ active: selectedRole === key, disabled: memorialLoading }"
              @click="!memorialLoading && (selectedRole = key)"
            >
              <div class="role-name">{{ info.label }}</div>
              <div class="role-desc">{{ info.desc }}</div>
            </div>
          </div>
        </div>

        <div class="field">
          <label class="field-label">见证稿内容 <span class="required">*</span></label>
          <a-textarea
            v-model:value="memorialArticle"
            placeholder="请粘贴需要润色的见证稿…"
            :disabled="memorialLoading"
            :auto-size="{ minRows: 5, maxRows: 12 }"
          />
          <div class="char-row">
            <span class="char-count">{{ (memorialArticle || '').length.toLocaleString() }} / 100,000 字</span>
            <a-button
              class="clear-btn"
              :disabled="memorialLoading"
              @click="memorialArticle = ''; memorialResult = null; memorialError = null"
            >
              清空
            </a-button>
          </div>
        </div>

        <div class="divider" />

        <div class="action-row">
          <a-button
            class="polish-btn"
            :loading="memorialLoading"
            :disabled="memorialLoading"
            @click="polishMemorial"
          >
            {{ memorialLoading ? "润色中…" : "润色" }}
          </a-button>
        </div>
      </div>

      <div v-if="memorialError" class="error-msg">{{ memorialError }}</div>

      <div v-if="memorialResult" class="card result-card">
        <div class="result-head">
          <span class="result-title">润色结果</span>
          <button class="copy-btn" @click="copyMemorialResult">
            <i class="ti ti-copy" aria-hidden="true"></i> 复制
          </button>
        </div>
        <div class="divider" />
        <pre class="result-body">{{ memorialResult }}</pre>
      </div>
    </div>

    <div v-show="mode === 'church'">
      <div class="card">
        <div class="field">
          <label class="field-label">{{ churchLang === 'zh' ? '语言' : 'Language' }}</label>
          <div class="seg-group">
            <div
              class="seg-btn"
              :class="{ active: churchLang === 'zh', disabled: churchLoading }"
              @click="!churchLoading && (churchLang = 'zh')"
            >
              中文
            </div>
            <div
              class="seg-btn"
              :class="{ active: churchLang === 'en', disabled: churchLoading }"
              @click="!churchLoading && (churchLang = 'en')"
            >
              English
            </div>
          </div>
        </div>

        <div class="field">
          <label class="field-label">{{ churchLang === 'zh' ? '类型' : 'Type' }}</label>
          <div class="seg-group">
            <div
              class="seg-btn"
              :class="{ active: churchType === 'church', disabled: churchLoading }"
              @click="!churchLoading && (churchType = 'church')"
            >
              {{ churchLang === 'zh' ? '召会通讯类' : 'Church Report' }}
            </div>
            <div
              class="seg-btn"
              :class="{ active: churchType === 'testimony', disabled: churchLoading }"
              @click="!churchLoading && (churchType = 'testimony')"
            >
              {{ churchLang === 'zh' ? '见证类' : 'Testimony' }}
            </div>
          </div>
        </div>

        <div class="field">
          <label class="field-label">
            {{ churchLang === 'zh' ? '文章内容' : 'Article Content' }}
            <span class="required">*</span>
          </label>
          <a-textarea
            v-model:value="churchArticle"
            :placeholder="churchLang === 'zh' ? '请粘贴需要润色的文章…' : 'Paste the article to polish here…'"
            :disabled="churchLoading"
            :auto-size="{ minRows: 5, maxRows: 12 }"
          />
          <div class="char-row">
            <span class="char-count">{{ (churchArticle || '').length.toLocaleString() }} / 100,000 字</span>
            <a-button
              class="clear-btn"
              :disabled="churchLoading"
              @click="churchArticle = ''; churchResult = null; churchError = null"
            >
              {{ churchLang === 'zh' ? '清空' : 'Clear' }}
            </a-button>
          </div>
        </div>

        <div class="divider" />

        <div class="action-row">
          <a-button
            class="polish-btn"
            :loading="churchLoading"
            :disabled="churchLoading"
            @click="polishChurch"
          >
            {{ churchLoading ? (churchLang === 'zh' ? '润色中…' : 'Polishing…') : (churchLang === 'zh' ? '润色' : 'Polish') }}
          </a-button>
        </div>
      </div>

      <div v-if="churchError" class="error-msg">{{ churchError }}</div>

      <div v-if="churchResult" class="card result-card">
        <div class="result-head">
          <span class="result-title">{{ churchLang === 'zh' ? '润色结果' : 'Result' }}</span>
          <button class="copy-btn" @click="copyChurchResult">
            <i class="ti ti-copy" aria-hidden="true"></i>
            {{ churchLang === 'zh' ? '复制' : 'Copy' }}
          </button>
        </div>
        <div class="divider" />
        <pre class="result-body">{{ churchResult }}</pre>
      </div>
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
.version-bar {
  display: flex;
  gap: 8px;
  padding: 16px 16px 0;
}
.ver-btn {
  flex: 1;
  padding: 9px 0;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  border: 1px solid #d9d9d9;
  background: #fff;
  color: #8c8c8c;
  text-align: center;
  cursor: pointer;
}
.ver-btn.active {
  background: #1890ff;
  border-color: #1890ff;
  color: #fff;
}
.role-group {
  display: flex;
  gap: 8px;
}
.role-btn {
  flex: 1;
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid #d9d9d9;
  background: #fff;
  cursor: pointer;
  user-select: none;
  transition: all 0.15s;
  text-align: center;
}
.role-btn:hover {
  border-color: #52c41a;
}
.role-btn.active {
  background: #f6ffed;
  border-color: #52c41a;
}
.role-btn.disabled {
  opacity: 0.65;
  cursor: not-allowed;
}
.role-name {
  font-size: 14px;
  font-weight: 500;
  color: #333;
  margin-bottom: 4px;
}
.role-btn.active .role-name {
  color: #389e0d;
}
.role-desc {
  font-size: 11px;
  color: #8c8c8c;
  line-height: 1.4;
}
.card {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  margin: 12px 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
.field {
  margin-bottom: 14px;
}
.field:last-child {
  margin-bottom: 0;
}
.field-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: #333;
  margin-bottom: 6px;
}
.required {
  color: #ff4d4f;
}
.seg-group {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.seg-btn {
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid #d9d9d9;
  background: #fff;
  color: #555;
  font-size: 13px;
  cursor: pointer;
  user-select: none;
  transition: all 0.15s;
}
.seg-btn:hover {
  border-color: #52c41a;
  color: #389e0d;
}
.seg-btn.active {
  background: #52c41a;
  border-color: #52c41a;
  color: #fff;
}
.seg-btn.disabled {
  opacity: 0.65;
  cursor: not-allowed;
}
.recovery-row {
  margin-top: 10px;
}
.recovery-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #333;
  cursor: pointer;
  user-select: none;
}
.recovery-checkbox {
  width: 15px;
  height: 15px;
  cursor: pointer;
  accent-color: #52c41a;
}
.char-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 6px;
}
.char-count {
  font-size: 12px;
  color: #aaa;
}
.clear-btn {
  font-size: 12px;
  font-weight: 500;
  color: #666;
  border-color: #d9d9d9;
  height: 26px;
  padding: 0 10px;
}
.clear-btn:hover {
  border-color: #ff4d4f;
  color: #ff4d4f;
}
.divider {
  height: 1px;
  background: #f0f0f0;
  margin: 12px 0;
}
.action-row {
  display: flex;
  justify-content: center;
}
.polish-btn {
  background: #55bbff;
  border-color: #55bbff;
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 2px;
  padding: 0 48px;
  height: 36px;
  border-radius: 6px;
}
.polish-btn:hover {
  background: #7cccff;
  border-color: #7cccff;
}
.error-msg {
  margin: 0 16px 12px;
  color: #cf1322;
  font-size: 13px;
  padding: 8px 12px;
  background: #fff2f0;
  border-radius: 6px;
  border: 1px solid #ffccc7;
}
.result-card {
  margin-top: 0;
}
.result-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.result-title {
  font-size: 14px;
  font-weight: 500;
  color: #333;
  flex: 1;
}
.copy-btn {
  background: #fff;
  border: 1px solid #d9d9d9;
  color: #555;
  padding: 3px 14px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}
.copy-btn:hover {
  color: #1890ff;
  border-color: #1890ff;
}
.result-body {
  font-size: 14px;
  color: #333;
  line-height: 1.9;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
}
</style>

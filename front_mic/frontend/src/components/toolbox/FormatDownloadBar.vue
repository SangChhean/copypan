<template>
  <div class="download-section">
    <div class="direction-row">
      <span class="label">下载格式：</span>
      <div class="format-tags">
        <label
          class="format-tag"
          :class="{ active: downloadFormats.includes('docx'), disabled: emptyText || downloading }"
        >
          <input
            v-model="downloadFormats"
            type="checkbox"
            value="docx"
            :disabled="emptyText || downloading"
            class="tag-input"
          />
          DOCX
        </label>
        <label
          class="format-tag"
          :class="{ active: downloadFormats.includes('pdf'), disabled: emptyText || downloading }"
        >
          <input
            v-model="downloadFormats"
            type="checkbox"
            value="pdf"
            :disabled="emptyText || downloading"
            class="tag-input"
          />
          PDF
        </label>
      </div>
    </div>
    <div class="action-row">
      <button
        type="button"
        class="action-btn"
        :disabled="buttonDisabled"
        :title="emptyText ? '请先生成内容' : ''"
        @click="downloadFormatted"
      >
        <span v-if="downloading" class="btn-spin">⟳</span>
        <span v-if="downloading">格式化并下载中…</span>
        <span v-else>刷格式并下载</span>
      </button>
    </div>
    <p v-if="downloading" class="loading-hint">请耐心等待 1～2 分钟</p>
    <p v-if="warning" class="format-warning">{{ warning }}</p>
    <p v-if="error" class="format-error">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  text: { type: String, required: true },
  direction: { type: String, required: true },
  apiEndpoint: { type: String, required: true },
})

const downloadFormats = ref([])
const downloading = ref(false)
const error = ref('')
const warning = ref('')

const emptyText = computed(() => !props.text.trim())
const buttonDisabled = computed(
  () => emptyText.value || downloadFormats.value.length === 0 || downloading.value
)

function formatErrorDetail(detail) {
  if (!detail) return '下载失败'
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
  }
  return String(detail)
}

function triggerFileDownload(data) {
  const binary = atob(data.content_base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  const mimeType =
    data.format === 'pdf'
      ? 'application/pdf'
      : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  const blob = new Blob([bytes], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = data.filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

async function downloadFormatted() {
  error.value = ''
  warning.value = ''

  if (!props.text.trim()) {
    error.value = '请先生成内容'
    return
  }
  if (downloadFormats.value.length === 0) {
    error.value = '请至少选择一个格式'
    return
  }

  downloading.value = true
  try {
    const orderedFormats = ['docx', 'pdf'].filter((f) =>
      downloadFormats.value.includes(f)
    )

    for (const format of orderedFormats) {
      try {
        const res = await fetch(props.apiEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: props.text,
            direction: props.direction,
            output_format: format,
          }),
        })
        const data = await res.json().catch(() => ({}))

        if (!res.ok) {
          error.value = formatErrorDetail(data.detail) || '下载失败'
          continue
        }

        if (!data.content_base64) {
          error.value = data.error || `${format.toUpperCase()} 下载失败：未返回文件内容`
          continue
        }

        triggerFileDownload(data)

        if (data.error) {
          warning.value = data.error
        }
      } catch (e) {
        error.value = e.message || '下载失败'
      }
    }
  } finally {
    downloading.value = false
  }
}
</script>

<style scoped>
.download-section {
  --color-primary: #2c5f8a;
  --color-primary-light: #e8f0f7;
  --color-primary-hover: #1e4a6e;
  --color-text: #2d2d2d;
  --color-text-secondary: #6b6b6b;
  --color-border: #dde3e9;
  --radius-btn: 6px;

  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid #e8e8e0;
}

.direction-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.direction-row .label {
  font-weight: 600;
  color: var(--color-text);
  font-size: 14px;
}

.format-tags {
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

.format-tag {
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
.format-tag:hover:not(.disabled):not(.active) {
  border-color: var(--color-primary);
  color: var(--color-primary);
}
.format-tag.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
}
.format-tag.disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.action-row {
  margin-top: 12px;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 28px;
  font-size: 15px;
  font-weight: 500;
  border-radius: var(--radius-btn);
  border: none;
  background: var(--color-primary);
  color: #fff;
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

.btn-spin {
  display: inline-block;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.loading-hint {
  margin: 8px 0 0;
  color: #9e9e9e;
  font-size: 13px;
}

.format-error {
  margin: 8px 0 0;
  color: #c62828;
  font-size: 13px;
}

.format-warning {
  margin: 8px 0 0;
  color: #e67e00;
  font-size: 13px;
}
</style>

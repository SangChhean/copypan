<template>
  <div class="materials-root">
    <div class="cn-page-header">
      <button type="button" class="cn-back" @click="router.push('/')">← 返回</button>
      <span class="cn-page-title">资料下载</span>
    </div>

    <div class="materials-body cn-page-body">
      <aside class="materials-sidebar">
        <a-spin :spinning="categoriesLoading">
          <a-menu
            v-model:selectedKeys="selectedKeys"
            mode="inline"
            class="materials-menu"
            @click="onCategoryClick"
          >
            <a-menu-item v-for="cat in categories" :key="String(cat.id)">
              {{ cat.name }}（{{ cat.files_count ?? 0 }}个文件）
            </a-menu-item>
          </a-menu>
          <div v-if="!categoriesLoading && !categories.length" class="materials-empty-side">
            暂无分类
          </div>
        </a-spin>
      </aside>

      <main class="materials-main">
        <a-spin :spinning="filesLoading">
          <a-table
            v-if="selectedCategoryId"
            class="cn-table-hover"
            :columns="columns"
            :data-source="files"
            :pagination="false"
            row-key="id"
            size="middle"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'size_bytes'">
                {{ formatSize(record.size_bytes) }}
              </template>
              <template v-else-if="column.key === 'created_at'">
                {{ formatDate(record.created_at) }}
              </template>
              <template v-else-if="column.key === 'action'">
                <a-button type="primary" size="small" class="mat-dl-btn" @click="downloadFile(record)">
                  下载
                </a-button>
              </template>
            </template>
            <template #emptyText>
              <a-empty description="该分类下暂无文件" />
            </template>
          </a-table>
          <div v-else class="materials-empty-main">请选择左侧分类</div>
        </a-spin>
      </main>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import http from '@/utils/http.js'
import { authHeaders } from '@/utils/auth.js'

const router = useRouter()
const categories = ref([])
const categoriesLoading = ref(false)
const files = ref([])
const filesLoading = ref(false)
const selectedCategoryId = ref(null)
const selectedKeys = ref([])

const columns = [
  { title: '文件名', dataIndex: 'display_name', key: 'display_name' },
  { title: '大小', key: 'size_bytes', width: 100 },
  { title: '上传时间', key: 'created_at', width: 180 },
  { title: '操作', key: 'action', width: 80 },
]

function formatSize(bytes) {
  const n = Number(bytes) || 0
  if (n >= 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${n} B`
}

function formatDate(iso) {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

async function loadCategories() {
  categoriesLoading.value = true
  try {
    const res = await http.get('/api/cn/materials/categories')
    categories.value = res.data || []
    if (categories.value.length && !selectedCategoryId.value) {
      selectedCategoryId.value = categories.value[0].id
      selectedKeys.value = [String(categories.value[0].id)]
    }
  } catch (e) {
    message.error(`加载分类失败（${e.response?.status || '网络错误'}）`)
    categories.value = []
  } finally {
    categoriesLoading.value = false
  }
}

async function loadFiles() {
  if (!selectedCategoryId.value) {
    files.value = []
    return
  }
  filesLoading.value = true
  try {
    const res = await http.get('/api/cn/materials', {
      params: { category_id: selectedCategoryId.value },
    })
    files.value = res.data || []
  } catch (e) {
    message.error(`加载文件失败（${e.response?.status || '网络错误'}）`)
  } finally {
    filesLoading.value = false
  }
}

function onCategoryClick({ key }) {
  selectedCategoryId.value = Number(key)
  selectedKeys.value = [key]
}

watch(selectedCategoryId, () => {
  loadFiles()
})

async function downloadFile(record) {
  try {
    const res = await fetch(`/api/cn/materials/${record.id}/download`, {
      headers: { ...authHeaders() },
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }
    const blob = await res.blob()
    if (!blob.size) {
      message.warning('未收到文件内容（本地无 Nginx 时可设置 CN_MATERIALS_DIRECT_DOWNLOAD=1）')
      return
    }
    let name = record.display_name || 'download.pdf'
    if (!name.toLowerCase().endsWith('.pdf')) name += '.pdf'
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = name
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    message.error(e.message || '下载失败')
  }
}

onMounted(async () => {
  await loadCategories()
  await loadFiles()
})
</script>

<style lang="less" scoped>
.materials-root {
  flex: 1;
  background: var(--cn-bg-page);
}

.materials-body {
  display: flex;
  max-width: 1100px;
  padding-top: 20px;
  gap: 0;
}

.materials-sidebar {
  width: 240px;
  flex-shrink: 0;
  background: var(--cn-bg-card);
  border: 0.5px solid var(--cn-border);
  border-right: 0.5px solid var(--cn-border);
  border-radius: var(--cn-radius-lg) 0 0 var(--cn-radius-lg);
  padding: 8px 0;
}

.materials-menu {
  border: none;
  background: transparent;
}

.materials-main {
  flex: 1;
  min-width: 0;
  background: var(--cn-bg-card);
  border: 0.5px solid var(--cn-border);
  border-left: none;
  border-radius: 0 var(--cn-radius-lg) var(--cn-radius-lg) 0;
  padding: 16px;
}

.mat-dl-btn {
  padding: 4px 12px !important;
  height: auto !important;
}

.materials-empty-side,
.materials-empty-main {
  padding: 24px;
  color: var(--cn-text-secondary);
  font-size: 13px;
  text-align: center;
}
</style>

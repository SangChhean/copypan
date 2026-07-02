<template>
  <div class="materials-root">
    <div class="cn-page-head">
      <button type="button" class="cn-back" @click="router.push('/')">‹‹ 返回</button>
      <span class="cn-page-title">{{ pageTitle }}</span>
    </div>
    <div class="cn-content-wrap">
      <div class="cn-content-card cn-content-card--wide">
        <!-- 手机版：下拉选择器 -->
        <div v-if="isMobile" class="materials-mobile">
          <div class="materials-mobile-select">
            <select
              class="mat-mobile-select"
              :value="navStack[0]?.id ?? ''"
              @change="onMobileRootSelectChange"
            >
              <option value="">请选择分类</option>
              <option v-for="cat in categories" :key="cat.id" :value="cat.id">{{ cat.name }}</option>
            </select>
          </div>
          <div class="materials-mobile-head">
            <button
              v-if="navStack.length"
              type="button"
              class="mat-back-btn"
              @click="goBack"
            >‹ 返回上一级</button>
            <span class="materials-main-title">{{ navStack.length ? selectedCategoryName : '全部分类' }}</span>
            <a-button v-if="navStack.length" size="small" class="mat-dl-btn" @click="onDownloadZip(selectedCategoryId)">批量下载</a-button>
          </div>
          <div v-if="filesLoading" class="materials-empty-main"><a-spin /></div>
          <div v-else-if="!currentChildren.length && !files.length" class="materials-empty-main">暂无内容</div>
          <div v-else class="mat-file-list">
            <div
              v-for="child in currentChildren"
              :key="'folder-' + child.id"
              class="mat-file-row mat-file-row--folder"
              @click="navStack.length ? enterSubCategory(child) : enterRootCategory(child)"
            >
              <span class="mat-folder-icon">📁</span>
              <span class="mat-file-name">{{ child.name }}</span>
              <span class="mat-file-size">文件夹</span>
              <a-button size="small" class="mat-dl-btn" @click.stop="onDownloadZip(child.id)">下载</a-button>
            </div>
            <div v-for="f in files" :key="'file-' + f.id" class="mat-file-row">
              <span class="mat-file-icon">📄</span>
              <span class="mat-file-name">{{ f.display_name }}</span>
              <span class="mat-file-size">{{ formatSize(f.size_bytes) }}</span>
              <a-button size="small" class="mat-dl-btn" @click.stop="downloadFile(f)">下载</a-button>
            </div>
          </div>
        </div>

        <!-- 电脑版：左右分栏 -->
        <div v-else class="materials-layout">
          <aside class="materials-sidebar">
            <a-spin :spinning="categoriesLoading">
              <div v-if="!categoriesLoading && !categories.length" class="materials-empty-side">
                暂无分类
              </div>
              <div class="root-cat-list">
                <div
                  v-for="node in categories"
                  :key="node.id"
                  class="root-cat-item"
                  :class="{ 'root-cat-item--active': navStack[0]?.id === node.id }"
                  @click="enterRootCategory(node)"
                >
                  {{ node.name }}
                </div>
              </div>
            </a-spin>
          </aside>
          <main class="materials-main">
            <a-spin :spinning="filesLoading || zipLoading">
              <div>
                <div class="materials-main-head">
                  <button
                    v-if="navStack.length >= 1"
                    type="button"
                    class="mat-back-btn"
                    @click="goBack"
                  >‹ 返回上一级</button>
                  <span class="materials-main-title">{{ navStack.length ? selectedCategoryName : '全部分类' }}</span>
                  <a-button v-if="navStack.length" size="small" class="mat-dl-btn" @click="onDownloadZip(selectedCategoryId)">
                    批量下载
                  </a-button>
                </div>
                <div v-if="!currentChildren.length && !files.length" class="materials-empty-main">
                  暂无内容
                </div>
                <table v-else class="mat-explorer-table">
                  <thead>
                    <tr>
                      <th>名称</th>
                      <th>大小 / 类型</th>
                      <th>时间</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="child in currentChildren"
                      :key="'folder-' + child.id"
                      class="mat-explorer-row mat-explorer-row--folder"
                      @click="navStack.length ? enterSubCategory(child) : enterRootCategory(child)"
                    >
                      <td><span class="mat-folder-icon">📁</span>{{ child.name }}</td>
                      <td>文件夹</td>
                      <td>{{ formatDate(child.created_at) }}</td>
                      <td>
                        <a-button size="small" class="mat-dl-btn" @click.stop="onDownloadZip(child.id)">下载</a-button>
                      </td>
                    </tr>
                    <tr
                      v-for="f in files"
                      :key="'file-' + f.id"
                      class="mat-explorer-row"
                    >
                      <td><span class="mat-file-icon">📄</span>{{ f.display_name }}</td>
                      <td>{{ formatSize(f.size_bytes) }}</td>
                      <td>{{ formatDate(f.created_at) }}</td>
                      <td>
                        <a-button size="small" class="mat-dl-btn" @click.stop="downloadFile(f)">下载</a-button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </a-spin>
          </main>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import http from '@/utils/http.js'
import { authHeaders } from '@/utils/auth.js'

const router = useRouter()
const route = useRoute()
const materialsType = computed(() => route.query.type || 'pastoral')
watch(materialsType, () => {
  selectedCategoryId.value = null
  selectedCategoryName.value = ''
  files.value = []
  navStack.value = []
  loadCategories()
})
const pageTitle = computed(() => {
  if (materialsType.value === 'conference') return '节期特会相关纲目'
  if (materialsType.value === 'children') return '儿童服事材料'
  return '牧养材料'
})
const categories = ref([])
const categoriesLoading = ref(false)
const files = ref([])
const filesLoading = ref(false)
const zipLoading = ref(false)
const selectedCategoryId = ref(null)
const selectedCategoryName = ref('')
const navStack = ref([])

const currentChildren = computed(() => {
  if (!navStack.value.length) return categories.value
  return navStack.value[navStack.value.length - 1].children || []
})

const currentCategoryId = computed(() => {
  if (!navStack.value.length) return null
  return navStack.value[navStack.value.length - 1].id
})

const windowWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 1024)
const isMobile = computed(() => windowWidth.value <= 640)

function onResize() {
  windowWidth.value = window.innerWidth
}

function onMobileRootSelectChange(e) {
  const id = e.target.value ? Number(e.target.value) : null
  if (!id) {
    navStack.value = []
    files.value = []
    return
  }
  const node = categories.value.find(c => c.id === id)
  if (node) enterRootCategory(node)
}

// ── 工具函数 ─────────────────────────────────────────────
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

// ── 数据加载 ─────────────────────────────────────────────
async function loadCategories() {
  categoriesLoading.value = true
  try {
    const res = await http.get('/api/cn/materials/categories', {
      params: { type: materialsType.value },
    })
    categories.value = res.data || []
  } catch (e) {
    message.error(`加载分类失败（${e.response?.status || '网络错误'}）`)
    categories.value = []
  } finally {
    categoriesLoading.value = false
  }
}

async function loadFiles() {
  if (!selectedCategoryId.value) { files.value = []; return }
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

function enterRootCategory(node) {
  navStack.value = [node]
  selectedCategoryId.value = node.id
  selectedCategoryName.value = node.name
  loadFiles()
}

function enterSubCategory(node) {
  navStack.value.push(node)
  selectedCategoryId.value = node.id
  selectedCategoryName.value = node.name
  loadFiles()
}

function goBack() {
  navStack.value.pop()
  if (navStack.value.length) {
    const current = navStack.value[navStack.value.length - 1]
    selectedCategoryId.value = current.id
    selectedCategoryName.value = current.name
    loadFiles()
  } else {
    selectedCategoryId.value = null
    selectedCategoryName.value = ''
    files.value = []
  }
}

async function onDownloadZip(categoryId) {
  zipLoading.value = true
  try {
    const res = await fetch(`/api/cn/materials/categories/${categoryId}/zip`, {
      headers: { ...authHeaders() },
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }
    const blob = await res.blob()
    const disposition = res.headers.get('Content-Disposition') || ''
    const match = disposition.match(/filename\*=UTF-8''(.+)/)
    const filename = match ? decodeURIComponent(match[1]) : 'download.zip'
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    message.error(e.message || '打包下载失败')
  } finally {
    zipLoading.value = false
  }
}

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
      message.warning('未收到文件内容')
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

onMounted(() => {
  window.addEventListener('resize', onResize)
  loadCategories()
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
})
</script>

<style lang="less">
.materials-root {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--cn-bg-page);

  .materials-layout {
    display: flex;
    gap: 0;
    min-height: 400px;
  }
  .materials-sidebar {
    width: 220px;
    flex-shrink: 0;
    border-right: 0.5px solid var(--cn-border);
    padding: 8px 0;
    overflow-y: auto;
  }
  .root-cat-list {
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .root-cat-item {
    padding: 12px 14px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    background: #EBF4FB;
    color: #1A2A3A;
    border-radius: 8px;
    border: 1.5px solid #CCE4F5;
    text-align: center;
    transition: background 0.15s, color 0.15s, border-color 0.15s;
    &:hover { background: #D6E8F5; }
    &.root-cat-item--active {
      background: #1B6CA8;
      color: #ffffff;
      border-color: #1B6CA8;
    }
    &.root-cat-item--active:hover { background: #1559A0; }
  }
  .materials-main {
    flex: 1;
    min-width: 0;
    padding: 12px 0 8px 20px;
  }
  .materials-main-head {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 14px;
  }
  .materials-main-title {
    flex: 1;
    font-size: 15px;
    font-weight: 500;
    color: var(--cn-text-primary);
  }
  .mat-back-btn {
    background: none;
    border: none;
    padding: 0;
    font-size: 13px;
    color: #1B6CA8;
    cursor: pointer;
    flex-shrink: 0;
    &:hover { text-decoration: underline; }
  }
  .mat-explorer-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
    th {
      text-align: left;
      padding: 8px 12px;
      font-weight: 500;
      color: var(--cn-text-secondary);
      border-bottom: 1px solid var(--cn-border);
    }
    td {
      padding: 10px 12px;
      border-bottom: 1px solid #E0EDF6;
      color: var(--cn-text-primary);
    }
    th:nth-child(2), td:nth-child(2) { width: 120px; }
    th:nth-child(3), td:nth-child(3) { width: 180px; }
    th:nth-child(4), td:nth-child(4) { width: 80px; }
  }
  .mat-explorer-row--folder {
    cursor: pointer;
    &:hover td { background: #F0F7FC; }
  }
  .mat-folder-icon,
  .mat-file-icon {
    margin-right: 6px;
  }
  .mat-dl-btn {
    background: #1677ff !important;
    color: #ffffff !important;
    border: 1px solid #1677ff !important;
    border-radius: 6px !important;
    padding: 4px 15px !important;
    font-size: 14px !important;
    font-weight: 400 !important;
    font-family: inherit !important;
    cursor: pointer;
    height: 32px !important;
    line-height: 1.5714285714285714 !important;
    flex-shrink: 0;
    box-shadow: none !important;
  }
  .mat-dl-btn:hover {
    background: #4096ff !important;
    border-color: #4096ff !important;
    color: #ffffff !important;
  }
  .materials-empty-side,
  .materials-empty-main {
    padding: 24px;
    color: var(--cn-text-secondary);
    font-size: 14px;
    text-align: center;
  }
  .materials-mobile {
    padding: 12px 14px;
    background: #ffffff;
  }
  .materials-mobile-select {
    margin-bottom: 12px;
  }
  .mat-mobile-select {
    width: 100%;
    background: #ffffff;
    border: 1px solid #CCE4F5;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 14px;
    color: #1A2A3A;
    font-family: inherit;
    appearance: none;
    -webkit-appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%231B6CA8' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 14px center;
  }
  .materials-mobile-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
  }
  .mat-file-list {
    display: flex;
    flex-direction: column;
  }
  .mat-file-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 11px 0;
    border-bottom: 1px solid #E0EDF6;
    background: #ffffff;
    &.mat-file-row--folder {
      cursor: pointer;
      &:active { background: #F0F7FC; }
    }
  }
  .mat-file-row:last-child {
    border-bottom: none;
  }
  .mat-file-name {
    flex: 1;
    font-size: 13px;
    color: #1A2A3A;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .mat-file-size {
    font-size: 11px;
    color: #94A3B8;
    flex-shrink: 0;
  }
}
</style>

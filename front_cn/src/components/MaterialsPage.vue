<template>
  <div class="materials-root">
    <div class="cn-page-head">
      <button type="button" class="cn-back" @click="router.push('/')">‹‹ 返回</button>
      <span class="cn-page-title">资料库下载</span>
    </div>
    <div class="cn-content-wrap">
      <div class="cn-content-card cn-content-card--wide">
        <div class="materials-layout">
          <aside class="materials-sidebar">
            <a-spin :spinning="categoriesLoading">
              <div v-if="!categoriesLoading && !categories.length" class="materials-empty-side">
                暂无分类
              </div>
              <div class="tree-root">
                <TreeNode
                  v-for="node in categories"
                  :key="node.id"
                  :node="node"
                  :selected-id="selectedCategoryId"
                  :open-root-id="openRootId"
                  @select="onSelectCategory"
                  @toggle-root="onToggleRoot"
                />
              </div>
            </a-spin>
          </aside>
          <main class="materials-main">
            <a-spin :spinning="filesLoading || zipLoading">
              <div v-if="selectedCategoryId">
                <div class="materials-main-head">
                  <span class="materials-main-title">{{ selectedCategoryName }}</span>
                  <a-button type="primary" size="small" class="mat-dl-btn" @click="onDownloadZip(selectedCategoryId)">
                    批量下载
                  </a-button>
                </div>
                <a-table
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
              </div>
              <div v-else class="materials-empty-main">请选择左侧分类</div>
            </a-spin>
          </main>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { defineComponent, h, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import http from '@/utils/http.js'
import { authHeaders } from '@/utils/auth.js'

const router = useRouter()
const categories = ref([])
const categoriesLoading = ref(false)
const files = ref([])
const filesLoading = ref(false)
const zipLoading = ref(false)
const selectedCategoryId = ref(null)
const openRootId = ref(null)
const selectedCategoryName = ref('')

const columns = [
  { title: '文件名', dataIndex: 'display_name', key: 'display_name' },
  { title: '大小', key: 'size_bytes', width: 100 },
  { title: '上传时间', key: 'created_at', width: 180 },
  { title: '操作', key: 'action', width: 80 },
]

// ── 树形节点组件 ──────────────────────────────────────────
const TreeNode = defineComponent({
  name: 'TreeNode',
  props: {
    node: { type: Object, required: true },
    selectedId: { type: Number, default: null },
    openRootId: { type: Number, default: null },
  },
  emits: ['select', 'toggle-root'],
  setup(props, { emit }) {
    return () => {
      const node = props.node
      const hasChildren = node.children && node.children.length > 0
      const isOpen = props.openRootId === node.id
      const isRootSelected = props.selectedId === node.id
      const isChildSelected = node.children?.some(c => c.id === props.selectedId)
      const isActive = isRootSelected || isChildSelected

      const rootRow = h('div', {
        class: ['mat-cat-root', isActive && 'mat-cat-root--active'],
        onClick: () => {
          emit('toggle-root', node.id)
          emit('select', node)
        },
      }, [
        h('span', {}, node.name),
        hasChildren ? h('span', {
          class: ['mat-cat-arrow', isOpen && 'mat-cat-arrow--open']
        }, '›') : null,
      ])

      const childRows = hasChildren && isOpen
        ? h('div', { class: 'mat-cat-children' },
            node.children.map(child =>
              h('div', {
                key: child.id,
                class: ['mat-cat-child', props.selectedId === child.id && 'mat-cat-child--active'],
                onClick: () => emit('select', child),
              }, [
                h('span', { class: 'mat-cat-l' }, 'L'),
                h('span', {}, child.name),
              ])
            )
          )
        : null

      return h('div', {
        class: ['mat-cat-block', isActive && 'mat-cat-block--active'],
      }, [rootRow, childRows])
    }
  },
})

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
    const res = await http.get('/api/cn/materials/categories')
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

function onSelectCategory(node) {
  selectedCategoryId.value = node.id
  selectedCategoryName.value = node.name
  loadFiles()
}

function onToggleRoot(id) {
  openRootId.value = openRootId.value === id ? null : id
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

onMounted(async () => {
  await loadCategories()
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
  .tree-root {
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .mat-cat-block {
    border-radius: 10px;
    border: 1.5px solid var(--cn-border);
    overflow: hidden;
    transition: border-color 0.2s;
    &.mat-cat-block--active {
      border-color: var(--cn-gold);
    }
  }
  .mat-cat-root {
    padding: 14px 18px;
    font-size: 16px;
    font-weight: 700;
    cursor: pointer;
    background: #EDE3CC;
    color: var(--cn-text-primary);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    text-align: center;
    transition: background 0.15s, color 0.15s;
    &:hover { background: #E4D8BE; }
    &.mat-cat-root--active {
      background: var(--cn-charcoal);
      color: var(--cn-gold);
    }
    &.mat-cat-root--active:hover { background: #3E3E3E; }
  }
  .mat-cat-arrow {
    font-size: 14px;
    transition: transform 0.2s;
    display: inline-block;
    &.mat-cat-arrow--open { transform: rotate(90deg); }
  }
  .mat-cat-children { background: #F5EFE0; }
  .mat-cat-child {
    padding: 10px 18px 10px 32px;
    font-size: 14px;
    font-weight: 500;
    color: var(--cn-text-secondary);
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 8px;
    border-top: 1px solid var(--cn-border);
    transition: background 0.15s, color 0.15s;
    &:hover { background: #EDE3CC; color: var(--cn-text-primary); }
    &.mat-cat-child--active {
      background: var(--cn-charcoal);
      color: var(--cn-gold);
      font-weight: 700;
    }
  }
  .mat-cat-l {
    color: #B0A898;
    font-size: 12px;
    flex-shrink: 0;
  }
  .materials-main {
    flex: 1;
    min-width: 0;
    padding: 12px 0 8px 20px;
  }
  .materials-main-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 14px;
  }
  .materials-main-title {
    font-size: 15px;
    font-weight: 500;
    color: var(--cn-text-primary);
  }
  .mat-dl-btn {
    padding: 4px 12px !important;
    height: auto !important;
  }
  .materials-empty-side,
  .materials-empty-main {
    padding: 24px;
    color: var(--cn-text-secondary);
    font-size: 14px;
    text-align: center;
  }
}
</style>

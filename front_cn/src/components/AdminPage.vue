<template>
  <div class="admin-root">
    <header class="admin-header">
      <div class="admin-header-inner">
        <a class="admin-back" href="#/qa">← 返回问答</a>
        <span class="admin-title">管理后台</span>
      </div>
    </header>

    <main class="admin-main">
      <div class="admin-content">

        <section class="admin-section">
          <div class="admin-section-title">管理统计</div>
          <div class="admin-token-row">
            <a-button type="primary" :loading="statsLoading" @click="loadStats">
              刷新数据
            </a-button>
          </div>
          <div v-if="apiError" class="admin-error">{{ apiError }}</div>
        </section>

        <section v-if="stats" class="admin-section">
          <a-tabs v-model:activeKey="activeTab">
            <a-tab-pane key="stats" tab="统计">
              <div class="admin-stat-grid">
                <div class="admin-stat-card">
                  <div class="admin-stat-value">{{ stats.total_requests }}</div>
                  <div class="admin-stat-label">总请求数</div>
                </div>
                <div class="admin-stat-card">
                  <div class="admin-stat-value">{{ pct(stats.cache_hit_rate) }}</div>
                  <div class="admin-stat-label">缓存命中率</div>
                </div>
                <div class="admin-stat-card">
                  <div class="admin-stat-value">{{ pct(stats.found_rate_new) }}</div>
                  <div class="admin-stat-label">找到率（非缓存）</div>
                </div>
                <div class="admin-stat-card">
                  <div class="admin-stat-value">${{ stats.total_cost_usd }}</div>
                  <div class="admin-stat-label">累计费用</div>
                </div>
                <div class="admin-stat-card">
                  <div class="admin-stat-value">{{ stats.avg_elapsed_ms }}ms</div>
                  <div class="admin-stat-label">平均耗时</div>
                </div>
              </div>

              <div v-if="stats.step_fail_records && stats.step_fail_records.length" class="admin-fail-wrap">
                <div class="admin-section-title">
                  未找到记录
                  <span class="admin-section-sub">（最近 {{ stats.step_fail_records.length }} 条）</span>
                </div>
                <div class="admin-fail-list">
                  <div
                    v-for="(rec, idx) in stats.step_fail_records"
                    :key="idx"
                    class="admin-fail-item"
                  >
                    <div class="admin-fail-question">{{ rec.question }}</div>
                    <div class="admin-fail-meta">
                      <span>{{ rec.ts }}</span>
                      <span>{{ rec.total_elapsed_ms }}ms</span>
                      <span>${{ rec.total_cost_usd }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div class="admin-feedback-wrap">
                <div class="admin-section-title">答案反馈汇总</div>
                <div v-if="feedbackStats" class="admin-feedback-grid">
                  <div class="admin-stat-card">
                    <div class="admin-stat-value">{{ feedbackStats.thumbs_up || 0 }}</div>
                    <div class="admin-stat-label">👍 总数</div>
                  </div>
                  <div class="admin-stat-card">
                    <div class="admin-stat-value">{{ feedbackStats.thumbs_down || 0 }}</div>
                    <div class="admin-stat-label">👎 总数</div>
                  </div>
                  <div class="admin-stat-card">
                    <div class="admin-stat-value">{{ pct(feedbackStats.rate || 0) }}</div>
                    <div class="admin-stat-label">好评率</div>
                  </div>
                </div>
                <div v-if="feedbackStats && feedbackStats.recent_down && feedbackStats.recent_down.length" class="admin-feedback-list">
                  <div
                    v-for="(rec, idx) in feedbackStats.recent_down"
                    :key="idx"
                    class="admin-feedback-item"
                  >
                    <div class="admin-feedback-head">
                      <span>{{ rec.created_at || '-' }}</span>
                      <span>{{ rec.username || '-' }}</span>
                    </div>
                    <div class="admin-feedback-text"><b>问：</b>{{ truncateText(rec.question, 50) }}</div>
                    <div class="admin-feedback-text"><b>答：</b>{{ truncateText(rec.answer, 100) }}</div>
                  </div>
                </div>
                <div v-else-if="feedbackStats" class="admin-feedback-empty">暂无反馈数据</div>
              </div>
            </a-tab-pane>

            <a-tab-pane key="cache" tab="缓存">
              <div class="admin-cache-row">
                <span class="admin-cache-desc">清除所有 <code>cn:cache:*</code> 缓存</span>
                <div class="admin-cache-actions">
                  <a-popconfirm
                    title="确认清除所有问答缓存？"
                    ok-text="确认"
                    cancel-text="取消"
                    @confirm="clearCache"
                  >
                    <a-button danger :loading="clearLoading">清除缓存</a-button>
                  </a-popconfirm>
                  <a-button danger ghost :loading="clearStatsLoading" @click="clearStats">
                    清空统计
                  </a-button>
                </div>
              </div>
              <div v-if="clearResult" class="admin-clear-result">
                已删除 {{ clearResult.deleted }} 条缓存（前缀：{{ clearResult.prefix }}）
              </div>
            </a-tab-pane>

            <a-tab-pane key="debug" tab="调试">
              <DebugPanel embedded />
            </a-tab-pane>

            <a-tab-pane key="invites" tab="邀请码">
              <div class="admin-invite-create">
                <a-input
                  v-model:value="inviteCode"
                  placeholder="输入邀请码（留空可自动生成）"
                  class="admin-invite-input"
                  @pressEnter="createInvite"
                />
                <a-button type="primary" :loading="inviteLoading" @click="createInvite">
                  生成邀请码
                </a-button>
              </div>

              <div class="admin-table-wrap">
                <table class="admin-table">
                  <thead>
                    <tr>
                      <th>邀请码</th>
                      <th>状态</th>
                      <th>使用者</th>
                      <th>创建时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-if="invitesLoading">
                      <td colspan="4" class="admin-table-empty">加载中...</td>
                    </tr>
                    <tr v-else-if="!invites.length">
                      <td colspan="4" class="admin-table-empty">暂无邀请码</td>
                    </tr>
                    <tr v-else v-for="row in invites" :key="row.id">
                      <td>{{ row.code }}</td>
                      <td>
                        <span :class="row.used ? 'tag-fail' : 'tag-ok'">
                          {{ row.used ? '已使用' : '未使用' }}
                        </span>
                      </td>
                      <td>{{ row.used_by || '-' }}</td>
                      <td>{{ row.created_at || '-' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </a-tab-pane>

            <a-tab-pane key="limits" tab="限额设置">
              <div class="admin-table-wrap">
                <table class="admin-table">
                  <thead>
                    <tr>
                      <th>用户名</th>
                      <th>管理员</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-if="usersLoading">
                      <td colspan="3" class="admin-table-empty">加载中...</td>
                    </tr>
                    <tr v-else-if="!users.length">
                      <td colspan="3" class="admin-table-empty">暂无用户</td>
                    </tr>
                    <tr v-else v-for="row in users" :key="'lim-' + row.id">
                      <td>{{ row.username }}</td>
                      <td>{{ row.is_admin ? '是' : '否' }}</td>
                      <td>
                        <a-button size="small" @click="openLimitModal(row.username)">
                          设置限额
                        </a-button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </a-tab-pane>

            <a-tab-pane key="materials" tab="资料管理">
              <a-card title="分类管理" size="small" class="admin-mat-card">
                <div class="admin-mat-create">
                  <a-input v-model:value="newCatName" placeholder="分类名称" class="admin-mat-input" />
                  <a-input
                    v-model:value="newCatDir"
                    placeholder="目录名（仅限英文字母数字下划线横线）"
                    class="admin-mat-input"
                  />
                  <a-button type="primary" :loading="catCreating" @click="createCategory">
                    新建
                  </a-button>
                </div>
                <a-table
                  :columns="catColumns"
                  :data-source="matCategories"
                  :loading="matCategoriesLoading"
                  row-key="id"
                  size="small"
                  :pagination="false"
                >
                  <template #bodyCell="{ column, record }">
                    <template v-if="column.key === 'action'">
                      <a-button danger size="small" @click="deleteCategory(record)">
                        删除
                      </a-button>
                    </template>
                  </template>
                </a-table>
              </a-card>

              <a-card title="文件管理" size="small" class="admin-mat-card">
                <div class="admin-mat-toolbar">
                  <span>分类：</span>
                  <a-select
                    v-model:value="matSelectedCategoryId"
                    placeholder="选择分类"
                    style="min-width: 200px"
                    :options="matCategoryOptions"
                    @change="loadMatFiles"
                  />
                </div>
                <a-upload
                  :show-upload-list="false"
                  :before-upload="beforeMatUpload"
                  :custom-request="customMatUpload"
                  accept=".pdf,application/pdf"
                >
                  <a-button type="primary" :disabled="!matSelectedCategoryId">上传 PDF</a-button>
                </a-upload>
                <a-table
                  :columns="matFileColumns"
                  :data-source="matFiles"
                  :loading="matFilesLoading"
                  row-key="id"
                  size="small"
                  :pagination="false"
                  class="admin-mat-file-table"
                >
                  <template #bodyCell="{ column, record }">
                    <template v-if="column.key === 'size_bytes'">
                      {{ formatMatSize(record.size_bytes) }}
                    </template>
                    <template v-else-if="column.key === 'created_at'">
                      {{ formatMatDate(record.created_at) }}
                    </template>
                    <template v-else-if="column.key === 'action'">
                      <a-popconfirm title="确认删除该文件？" @confirm="deleteMaterial(record.id)">
                        <a-button danger size="small">删除</a-button>
                      </a-popconfirm>
                    </template>
                  </template>
                </a-table>
              </a-card>
            </a-tab-pane>

            <a-tab-pane key="users" tab="用户">
              <div class="admin-table-wrap">
                <table class="admin-table">
                  <thead>
                    <tr>
                      <th>用户名</th>
                      <th>管理员</th>
                      <th>创建时间</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-if="usersLoading">
                      <td colspan="4" class="admin-table-empty">加载中...</td>
                    </tr>
                    <tr v-else-if="!users.length">
                      <td colspan="4" class="admin-table-empty">暂无用户</td>
                    </tr>
                    <tr v-else v-for="row in users" :key="row.id">
                      <td>{{ row.username }}</td>
                      <td>{{ row.is_admin ? '是' : '否' }}</td>
                      <td>{{ row.created_at || '-' }}</td>
                      <td>
                        <a-button size="small" class="admin-user-limit-btn" @click="openLimitModal(row.username)">
                          设置限额
                        </a-button>
                        <a-popconfirm
                          title="确认删除该用户？"
                          ok-text="确认"
                          cancel-text="取消"
                          @confirm="deleteUser(row.username)"
                        >
                          <a-button danger size="small" :loading="deletingUser === row.username">
                            删除
                          </a-button>
                        </a-popconfirm>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </a-tab-pane>
          </a-tabs>
        </section>

      </div>
    </main>

    <a-modal
      v-model:open="limitModalOpen"
      :title="limitModalUser ? `${limitModalUser} 的每日限额` : '每日限额'"
      ok-text="批量保存"
      cancel-text="取消"
      :confirm-loading="limitSaving"
      @ok="saveAllLimits"
    >
      <div v-if="limitModalLoading" class="admin-limit-loading">加载中...</div>
      <div v-else class="admin-limit-form">
        <div v-for="item in limitFields" :key="item.key" class="admin-limit-row">
          <div class="admin-limit-label">
            {{ item.label }}
            <span v-if="item.hint" class="admin-limit-hint">（{{ item.hint }}）</span>
          </div>
          <div class="admin-limit-usage" v-if="limitUsage[item.key]">
            今日已用 {{ limitUsage[item.key].used ?? 0 }} / {{ limitUsage[item.key].limit ?? 0 }}
          </div>
          <a-input-number v-model:value="limitValues[item.key]" :min="-1" style="width: 120px" />
          <div v-if="limitValues[item.key] === -1" class="admin-limit-note">-1 = 不限次数</div>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import http from '@/utils/http.js'
import DebugPanel from '@/components/DebugPanel.vue'

const stats = ref(null)
const statsLoading = ref(false)
const clearLoading = ref(false)
const clearStatsLoading = ref(false)
const apiError = ref('')
const clearResult = ref(null)
const feedbackStats = ref(null)
const activeTab = ref('stats')
const inviteCode = ref('')
const invites = ref([])
const users = ref([])
const inviteLoading = ref(false)
const invitesLoading = ref(false)
const usersLoading = ref(false)
const deletingUser = ref('')

const limitModalOpen = ref(false)
const limitModalUser = ref('')
const limitModalLoading = ref(false)
const limitSaving = ref(false)
const limitValues = ref({ outline: 3, translate: 3, qa: 3, burden: 20, asr: 20 })
const limitUsage = ref({})

const limitFields = [
  { key: 'outline', label: '纲目制作' },
  { key: 'translate', label: '纲目翻译' },
  { key: 'qa', label: '职事问答' },
  { key: 'burden', label: '负担说明', hint: '防滥用护栏' },
  { key: 'asr', label: '语音转写', hint: '防滥用护栏' },
]

const matCategories = ref([])
const matCategoriesLoading = ref(false)
const matFiles = ref([])
const matFilesLoading = ref(false)
const matSelectedCategoryId = ref(null)
const newCatName = ref('')
const newCatDir = ref('')
const catCreating = ref(false)

const catColumns = [
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: '目录名', dataIndex: 'dir_name', key: 'dir_name' },
  { title: '文件数', dataIndex: 'files_count', key: 'files_count', width: 80 },
  { title: '操作', key: 'action', width: 80 },
]

const matFileColumns = [
  { title: '文件名', dataIndex: 'display_name', key: 'display_name' },
  { title: '大小', key: 'size_bytes', width: 90 },
  { title: '上传时间', key: 'created_at', width: 160 },
  { title: '操作', key: 'action', width: 80 },
]

const matCategoryOptions = computed(() =>
  matCategories.value.map((c) => ({ label: c.name, value: c.id }))
)

const MAX_MAT_MB = 200

function pct(val) {
  if (val == null) return '-'
  return (val * 100).toFixed(1) + '%'
}

async function loadStats() {
  statsLoading.value = true
  apiError.value = ''
  clearResult.value = null
  try {
    const res = await http.get('/api/qa/stats')
    stats.value = res.data
    await Promise.all([loadInvites(), loadUsers(), loadFeedbackStats()])
  } catch (e) {
    const status = e.response?.status
    if (status === 403) apiError.value = '需要管理员权限'
    else if (status === 503) apiError.value = '服务不可用（Redis 未连接）'
    else apiError.value = `请求失败（${status || '网络错误'}）`
    stats.value = null
    feedbackStats.value = null
  } finally {
    statsLoading.value = false
  }
}

async function loadInvites() {
  invitesLoading.value = true
  try {
    const res = await http.get('/api/cn/auth/invites')
    invites.value = res.data?.items || []
  } catch (e) {
    const status = e.response?.status
    apiError.value = `邀请码列表加载失败（${status || '网络错误'}）`
  } finally {
    invitesLoading.value = false
  }
}

async function loadUsers() {
  usersLoading.value = true
  try {
    const res = await http.get('/api/cn/auth/users')
    users.value = res.data?.items || []
  } catch (e) {
    const status = e.response?.status
    apiError.value = `用户列表加载失败（${status || '网络错误'}）`
  } finally {
    usersLoading.value = false
  }
}

async function deleteUser(username) {
  if (!username) return
  deletingUser.value = username
  apiError.value = ''
  try {
    await http.delete(`/api/cn/auth/users/${encodeURIComponent(username)}`)
    await loadUsers()
  } catch (e) {
    const status = e.response?.status
    apiError.value = `删除用户失败（${status || '网络错误'}）`
  } finally {
    deletingUser.value = ''
  }
}

function _randomCode() {
  return `INVITE-${Date.now().toString(36).toUpperCase()}`
}

async function createInvite() {
  inviteLoading.value = true
  apiError.value = ''
  try {
    const code = inviteCode.value.trim() || _randomCode()
    await http.post('/api/cn/auth/invite', { code })
    inviteCode.value = ''
    await loadInvites()
  } catch (e) {
    const status = e.response?.status
    apiError.value = `生成邀请码失败（${status || '网络错误'}）`
  } finally {
    inviteLoading.value = false
  }
}

async function clearCache() {
  clearLoading.value = true
  clearResult.value = null
  try {
    const res = await http.post('/api/qa/cache/clear', {})
    const cleared = res.data
    await loadStats()
    clearResult.value = cleared
  } catch (e) {
    apiError.value = `清除失败（${e.response?.status || '网络错误'}）`
  } finally {
    clearLoading.value = false
  }
}

async function clearStats() {
  if (!window.confirm('确认清空统计数据？')) return
  clearStatsLoading.value = true
  apiError.value = ''
  try {
    await http.post('/api/qa/stats/clear', {})
    window.alert('统计数据已清空')
    await loadStats()
  } catch (e) {
    apiError.value = `清空统计失败（${e.response?.status || '网络错误'}）`
  } finally {
    clearStatsLoading.value = false
  }
}

async function loadFeedbackStats() {
  try {
    const res = await http.get('/api/qa/feedback/stats')
    feedbackStats.value = res.data || null
  } catch (e) {
    console.error('load feedback stats failed', e)
    feedbackStats.value = null
  }
}

function truncateText(text, maxLen) {
  const s = (text || '').trim()
  if (!s) return '-'
  return s.length > maxLen ? `${s.slice(0, maxLen)}...` : s
}

async function openLimitModal(username) {
  limitModalUser.value = username
  limitModalOpen.value = true
  limitModalLoading.value = true
  try {
    const res = await http.get(`/api/cn/auth/users/${encodeURIComponent(username)}/limits`)
    const data = res.data || {}
    limitValues.value = { ...data.limits }
    limitUsage.value = { ...data.usage }
  } catch (e) {
    message.error(`加载限额失败（${e.response?.data?.detail || e.response?.status || '网络错误'}）`)
    limitModalOpen.value = false
  } finally {
    limitModalLoading.value = false
  }
}

async function saveAllLimits() {
  if (!limitModalUser.value) return
  limitSaving.value = true
  try {
    for (const item of limitFields) {
      await http.post(`/api/cn/auth/users/${encodeURIComponent(limitModalUser.value)}/limit`, {
        feature: item.key,
        daily_limit: limitValues.value[item.key],
      })
    }
    message.success('已更新')
    limitModalOpen.value = false
  } catch (e) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    limitSaving.value = false
  }
}

function formatMatSize(bytes) {
  const n = Number(bytes) || 0
  if (n >= 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${n} B`
}

function formatMatDate(iso) {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

async function loadMatCategories() {
  matCategoriesLoading.value = true
  try {
    const res = await http.get('/api/cn/materials/categories')
    matCategories.value = res.data || []
    if (matCategories.value.length && !matSelectedCategoryId.value) {
      matSelectedCategoryId.value = matCategories.value[0].id
    }
  } catch (e) {
    message.error(`分类加载失败（${e.response?.status || '网络错误'}）`)
  } finally {
    matCategoriesLoading.value = false
  }
}

async function loadMatFiles() {
  if (!matSelectedCategoryId.value) {
    matFiles.value = []
    return
  }
  matFilesLoading.value = true
  try {
    const res = await http.get('/api/cn/materials', {
      params: { category_id: matSelectedCategoryId.value },
    })
    matFiles.value = res.data || []
  } catch (e) {
    message.error(`文件列表加载失败（${e.response?.status || '网络错误'}）`)
  } finally {
    matFilesLoading.value = false
  }
}

async function createCategory() {
  const name = newCatName.value.trim()
  const dir_name = newCatDir.value.trim()
  if (!name || !dir_name) {
    message.warning('请填写分类名称与目录名')
    return
  }
  catCreating.value = true
  try {
    await http.post('/api/cn/materials/categories', { name, dir_name, sort_order: 0 })
    newCatName.value = ''
    newCatDir.value = ''
    message.success('分类已创建')
    await loadMatCategories()
  } catch (e) {
    message.error(e.response?.data?.detail || '创建失败')
  } finally {
    catCreating.value = false
  }
}

async function deleteCategory(record) {
  try {
    await http.delete(`/api/cn/materials/categories/${record.id}`)
    message.success('分类已删除')
    if (matSelectedCategoryId.value === record.id) {
      matSelectedCategoryId.value = matCategories.value.find((c) => c.id !== record.id)?.id ?? null
    }
    await loadMatCategories()
    await loadMatFiles()
  } catch (e) {
    message.error(e.response?.data?.detail || '删除失败')
  }
}

function beforeMatUpload(file) {
  const isPdf =
    file.type === 'application/pdf' || (file.name || '').toLowerCase().endsWith('.pdf')
  if (!isPdf) {
    message.error('只允许上传 PDF 文件')
    return false
  }
  if (file.size > MAX_MAT_MB * 1024 * 1024) {
    message.error(`文件超过 ${MAX_MAT_MB}MB 限制`)
    return false
  }
  return true
}

async function customMatUpload({ file, onSuccess, onError }) {
  if (!matSelectedCategoryId.value) {
    onError(new Error('请先选择分类'))
    return
  }
  const formData = new FormData()
  formData.append('category_id', String(matSelectedCategoryId.value))
  formData.append('file', file)
  try {
    await http.post('/api/cn/materials/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    message.success('上传成功')
    onSuccess()
    await loadMatFiles()
    await loadMatCategories()
  } catch (e) {
    message.error(e.response?.data?.detail || '上传失败')
    onError(e)
  }
}

async function deleteMaterial(id) {
  try {
    await http.delete(`/api/cn/materials/${id}`)
    message.success('已删除')
    await loadMatFiles()
    await loadMatCategories()
  } catch (e) {
    message.error(e.response?.data?.detail || '删除失败')
  }
}

watch(activeTab, (tab) => {
  if (tab === 'materials') {
    loadMatCategories().then(loadMatFiles)
  }
})

onMounted(() => {
  loadStats()
})
</script>

<style lang="less" scoped>
.admin-root {
  min-height: 100vh;
  background: var(--color-bg);
}

/* 页头 */
.admin-header {
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface);
}
.admin-header-inner {
  max-width: 760px;
  margin: 0 auto;
  padding: 14px 24px;
  display: flex;
  align-items: center;
  gap: 16px;
}
.admin-back {
  font-size: 13px;
  color: var(--color-text-secondary);
  text-decoration: none;
  &:hover { color: var(--color-primary); }
}
.admin-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text);
}

/* 主体 */
.admin-main { padding: 32px 24px; }
.admin-content {
  max-width: 760px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 32px;
}
.admin-fail-wrap {
  margin-top: 20px;
}
.admin-feedback-wrap {
  margin-top: 24px;
}
.admin-feedback-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}
.admin-feedback-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.admin-feedback-item {
  padding: 12px;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
}
.admin-feedback-head {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-bottom: 6px;
}
.admin-feedback-text {
  font-size: 13px;
  color: var(--color-text);
  line-height: 1.6;
}
.admin-feedback-empty {
  font-size: 13px;
  color: var(--color-text-secondary);
}

/* Section */
.admin-section {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 24px;
}
.admin-section-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 16px;
  letter-spacing: 0.04em;
}
.admin-section-sub {
  font-weight: 400;
  color: var(--color-text-secondary);
  font-size: 12px;
}

/* Token */
.admin-token-row {
  display: flex;
  gap: 10px;
}
.admin-token-input { flex: 1; }
.admin-error {
  margin-top: 8px;
  font-size: 13px;
  color: #cf1322;
}

/* 统计卡片 */
.admin-stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 12px;
}
.admin-stat-card {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 16px;
  text-align: center;
}
.admin-stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-primary);
  margin-bottom: 4px;
}
.admin-stat-label {
  font-size: 11px;
  color: var(--color-text-secondary);
}

/* 未找到记录 */
.admin-fail-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.admin-fail-item {
  padding: 12px;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
}
.admin-fail-question {
  font-size: 14px;
  color: var(--color-text);
  margin-bottom: 6px;
}
.admin-fail-meta {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--color-text-secondary);
}

/* 缓存 */
.admin-cache-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.admin-cache-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.admin-cache-desc {
  font-size: 13px;
  color: var(--color-text-secondary);
  code {
    background: #f0ece4;
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 12px;
    color: var(--color-primary);
  }
}
.admin-clear-result {
  margin-top: 10px;
  font-size: 13px;
  color: #389e0d;
}
.admin-invite-create {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}
.admin-invite-input {
  flex: 1;
}
.admin-table-wrap {
  overflow-x: auto;
}
.admin-table {
  width: 100%;
  border-collapse: collapse;
  th,
  td {
    border: 1px solid var(--color-border);
    padding: 8px 10px;
    font-size: 12px;
    color: var(--color-text);
    text-align: left;
  }
  th {
    background: #fafafa;
    font-weight: 600;
  }
}
.admin-table-empty {
  text-align: center !important;
  color: var(--color-text-secondary) !important;
}
.admin-placeholder {
  color: var(--color-text-secondary);
  padding: 16px 0;
}
.admin-user-limit-btn {
  margin-right: 8px;
}
.admin-mat-card {
  margin-bottom: 16px;
}
.admin-mat-create {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.admin-mat-input {
  flex: 1;
  min-width: 140px;
}
.admin-mat-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.admin-mat-file-table {
  margin-top: 12px;
}
.admin-limit-loading {
  padding: 24px;
  text-align: center;
  color: var(--color-text-secondary);
}
.admin-limit-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.admin-limit-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.admin-limit-label {
  font-weight: 600;
  font-size: 13px;
}
.admin-limit-hint {
  font-weight: 400;
  color: var(--color-text-secondary);
  font-size: 12px;
}
.admin-limit-usage {
  font-size: 12px;
  color: var(--color-text-secondary);
}
.admin-limit-note {
  font-size: 12px;
  color: var(--color-text-secondary);
}
</style>

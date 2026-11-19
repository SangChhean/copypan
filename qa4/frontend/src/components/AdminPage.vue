<template>
  <div class="admin-root">
    <header class="admin-header">
      <div class="admin-header-inner">
        <router-link class="admin-back" to="/">← 返回问答</router-link>
        <span class="admin-title">管理后台</span>
      </div>
    </header>

    <main class="admin-main">
      <div class="admin-content">
        <section class="admin-section">
          <div class="admin-section-title">管理员 Token</div>
          <div class="admin-token-row">
            <a-input-password
              v-model:value="adminToken"
              placeholder="输入 QA4_ADMIN_TOKEN（请求头 X-Admin-Token）"
              class="admin-token-input"
              @pressEnter="loadStats"
            />
            <a-button type="primary" :loading="statsLoading" @click="loadStats">
              加载统计
            </a-button>
          </div>
          <div v-if="tokenError" class="admin-error">{{ tokenError }}</div>
          <div v-if="okMsg" class="admin-ok">{{ okMsg }}</div>
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
                    <div class="admin-fail-question">{{ rec.question || '-' }}</div>
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
                <div
                  v-if="feedbackStats && feedbackStats.recent_down && feedbackStats.recent_down.length"
                  class="admin-feedback-list"
                >
                  <div
                    v-for="(rec, idx) in feedbackStats.recent_down"
                    :key="idx"
                    class="admin-feedback-item"
                  >
                    <div class="admin-feedback-head">
                      <span>{{ rec.created_at || '-' }}</span>
                      <span>{{ rec.username || '-' }}</span>
                    </div>
                    <div class="admin-feedback-text">
                      <b>问：</b>{{ truncateText(rec.question, 50) }}
                    </div>
                    <div class="admin-feedback-text">
                      <b>答：</b>{{ truncateText(rec.answer, 100) }}
                    </div>
                  </div>
                </div>
                <div v-else-if="feedbackStats" class="admin-feedback-empty">暂无反馈数据</div>
              </div>
            </a-tab-pane>

            <a-tab-pane key="cache" tab="缓存">
              <div class="admin-cache-row">
                <span class="admin-cache-desc">清除问答缓存（Redis 前缀下全部键）</span>
                <div class="admin-cache-actions">
                  <a-popconfirm
                    title="确认清除所有问答缓存？"
                    ok-text="确认"
                    cancel-text="取消"
                    @confirm="clearCache"
                  >
                    <a-button danger :loading="clearLoading">清除缓存</a-button>
                  </a-popconfirm>
                  <a-button danger ghost :loading="clearStatsLoading" @click="clearStatsMonitor">
                    清空统计
                  </a-button>
                </div>
              </div>
              <div v-if="clearResult" class="admin-clear-result">
                已删除 {{ clearResult.deleted }} 条缓存
                <span v-if="clearResult.prefix">（前缀：{{ clearResult.prefix }}）</span>
              </div>
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
                      <th>已用/上限</th>
                      <th>状态</th>
                      <th>创建时间</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-if="invitesLoading">
                      <td colspan="5" class="admin-table-empty">加载中...</td>
                    </tr>
                    <tr v-else-if="!invites.length">
                      <td colspan="5" class="admin-table-empty">暂无邀请码</td>
                    </tr>
                    <tr v-else v-for="row in invites" :key="row.code">
                      <td>{{ row.code }}</td>
                      <td>{{ row.used_count || 0 }}/{{ row.max_uses || 1 }}</td>
                      <td>
                        <span :class="inviteStatusClass(row)">{{ inviteStatus(row) }}</span>
                      </td>
                      <td>{{ row.created_at || '-' }}</td>
                      <td>
                        <a-button
                          v-if="!Number(row.disabled)"
                          size="small"
                          :loading="disablingInvite === row.code"
                          @click="disableInvite(row.code)"
                        >
                          停用
                        </a-button>
                        <span v-else>-</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </a-tab-pane>

            <a-tab-pane key="users" tab="用户">
              <div class="admin-table-wrap">
                <table class="admin-table">
                  <thead>
                    <tr>
                      <th>用户名</th>
                      <th>每日上限</th>
                      <th>状态</th>
                      <th>创建时间</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-if="usersLoading">
                      <td colspan="5" class="admin-table-empty">加载中...</td>
                    </tr>
                    <tr v-else-if="!users.length">
                      <td colspan="5" class="admin-table-empty">暂无用户</td>
                    </tr>
                    <tr v-else v-for="row in users" :key="row.username">
                      <td>{{ row.username }}</td>
                      <td>
                        <input
                          class="limit-input"
                          type="number"
                          min="0"
                          v-model.number="limitDraft[row.username]"
                        />
                        <a-button
                          size="small"
                          style="margin-left: 6px"
                          :loading="savingLimit === row.username"
                          @click="saveLimit(row.username)"
                        >
                          保存
                        </a-button>
                      </td>
                      <td>{{ Number(row.disabled) ? '停用' : '正常' }}</td>
                      <td>{{ row.created_at || '-' }}</td>
                      <td class="admin-user-actions">
                        <a-button
                          size="small"
                          :loading="togglingUser === row.username"
                          @click="toggleDisable(row)"
                        >
                          {{ Number(row.disabled) ? '启用' : '停用' }}
                        </a-button>
                        <a-popconfirm
                          title="确认删除该用户？"
                          ok-text="确认"
                          cancel-text="取消"
                          @confirm="deleteUser(row.username)"
                        >
                          <a-button
                            danger
                            size="small"
                            :loading="deletingUser === row.username"
                          >
                            删除
                          </a-button>
                        </a-popconfirm>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </a-tab-pane>

            <a-tab-pane key="traces" tab="记录">
              <a-button :loading="tracesLoading" @click="loadTraces">刷新列表</a-button>
              <ul class="admin-trace-list">
                <li
                  v-for="t in traces"
                  :key="t.request_id"
                  @click="openTrace(t)"
                >
                  {{ (t.question_preview || t.request_id || '').slice(0, 80) }}
                </li>
              </ul>
              <p v-if="esFailLabels.length" class="admin-es-fail">检索失败：{{ esFailLabels.join('、') }}</p>
              <pre v-if="traceDetail" class="admin-trace-detail">{{ traceDetailText }}</pre>
            </a-tab-pane>
          </a-tabs>
        </section>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import {
  adminStats,
  adminFeedbackStats,
  adminClearCache,
  adminClearStats,
  adminCreateInvite,
  adminListInvites,
  adminDisableInvite,
  adminListUsers,
  adminSetUserLimit,
  adminDeleteUser,
  adminDisableUser,
  adminTraces,
  adminTraceDetail,
} from '../utils/qa4Api.js'

const adminToken = ref(localStorage.getItem('qa4_admin_token') || '')
const stats = ref(null)
const feedbackStats = ref(null)
const statsLoading = ref(false)
const clearLoading = ref(false)
const clearStatsLoading = ref(false)
const clearResult = ref(null)
const tokenError = ref('')
const okMsg = ref('')
const activeTab = ref('stats')

const inviteCode = ref('')
const invites = ref([])
const inviteLoading = ref(false)
const invitesLoading = ref(false)
const disablingInvite = ref('')

const users = ref([])
const usersLoading = ref(false)
const limitDraft = reactive({})
const savingLimit = ref('')
const deletingUser = ref('')
const togglingUser = ref('')

const traces = ref([])
const tracesLoading = ref(false)
const traceDetail = ref(null)

const traceDetailText = computed(() => {
  if (!traceDetail.value) return ''
  const d = { ...(traceDetail.value.item || traceDetail.value) }
  for (const k of Object.keys(d)) {
    if (/secret|password|token|key/i.test(k) && k !== 'request_id') delete d[k]
  }
  return JSON.stringify(d, null, 2)
})

const esFailLabels = computed(() => {
  const raw = traceDetail.value?.item || traceDetail.value || {}
  const fails = Array.isArray(raw.es_failures) ? raw.es_failures : []
  const names = []
  const seen = new Set()
  for (const f of fails) {
    const name = (f && (f.logical || f.index)) || ''
    if (!name || seen.has(name)) continue
    seen.add(name)
    names.push(name)
  }
  return names
})

function pct(val) {
  if (val == null) return '-'
  return (Number(val) * 100).toFixed(1) + '%'
}

function truncateText(text, maxLen) {
  const s = (text || '').trim()
  if (!s) return '-'
  return s.length > maxLen ? `${s.slice(0, maxLen)}...` : s
}

function _randomCode() {
  return `INVITE-${Date.now().toString(36).toUpperCase()}`
}

function inviteStatus(row) {
  if (Number(row.disabled)) return '已停用'
  if (Number(row.used_count) >= Number(row.max_uses || 1)) return '已用完'
  return '可用'
}

function inviteStatusClass(row) {
  return Number(row.disabled) || Number(row.used_count) >= Number(row.max_uses || 1)
    ? 'tag-fail'
    : 'tag-ok'
}

function persistToken() {
  localStorage.setItem('qa4_admin_token', adminToken.value.trim())
}

async function loadStats() {
  if (!adminToken.value.trim()) {
    tokenError.value = '请输入 Token'
    return
  }
  statsLoading.value = true
  tokenError.value = ''
  okMsg.value = ''
  clearResult.value = null
  persistToken()
  try {
    stats.value = await adminStats(adminToken.value.trim())
    await Promise.all([loadInvites(), loadUsers(), loadFeedbackStats(), loadTraces()])
  } catch (e) {
    const msg = e.message || String(e)
    if (/401|无效/.test(msg)) tokenError.value = 'Token 无效'
    else if (/503|未配置|未初始化/.test(msg)) tokenError.value = msg
    else tokenError.value = msg
    stats.value = null
    feedbackStats.value = null
  } finally {
    statsLoading.value = false
  }
}

async function loadFeedbackStats() {
  feedbackStats.value = await adminFeedbackStats(adminToken.value.trim())
}

async function loadInvites() {
  invitesLoading.value = true
  try {
    invites.value = await adminListInvites(adminToken.value.trim())
  } finally {
    invitesLoading.value = false
  }
}

async function loadUsers() {
  usersLoading.value = true
  try {
    users.value = await adminListUsers(adminToken.value.trim())
    for (const u of users.value) {
      limitDraft[u.username] = Number(u.daily_limit) || 0
    }
  } finally {
    usersLoading.value = false
  }
}

async function createInvite() {
  if (!adminToken.value.trim()) {
    tokenError.value = '请先输入 Token'
    return
  }
  inviteLoading.value = true
  tokenError.value = ''
  okMsg.value = ''
  try {
    const code = inviteCode.value.trim() || _randomCode()
    await adminCreateInvite(adminToken.value.trim(), code)
    inviteCode.value = ''
    okMsg.value = `已生成邀请码：${code}`
    await loadInvites()
  } catch (e) {
    tokenError.value = e.message || String(e)
  } finally {
    inviteLoading.value = false
  }
}

async function disableInvite(code) {
  disablingInvite.value = code
  tokenError.value = ''
  try {
    await adminDisableInvite(adminToken.value.trim(), code)
    await loadInvites()
  } catch (e) {
    tokenError.value = e.message || String(e)
  } finally {
    disablingInvite.value = ''
  }
}

async function saveLimit(username) {
  savingLimit.value = username
  tokenError.value = ''
  okMsg.value = ''
  try {
    const lim = Number(limitDraft[username])
    if (!Number.isFinite(lim) || lim < 0) {
      tokenError.value = '额度须为非负整数'
      return
    }
    await adminSetUserLimit(adminToken.value.trim(), username, lim)
    okMsg.value = `已将 ${username} 每日上限设为 ${lim}`
    await loadUsers()
  } catch (e) {
    tokenError.value = e.message || String(e)
  } finally {
    savingLimit.value = ''
  }
}

async function deleteUser(username) {
  deletingUser.value = username
  tokenError.value = ''
  try {
    await adminDeleteUser(adminToken.value.trim(), username)
    await loadUsers()
  } catch (e) {
    tokenError.value = e.message || String(e)
  } finally {
    deletingUser.value = ''
  }
}

async function toggleDisable(row) {
  togglingUser.value = row.username
  tokenError.value = ''
  try {
    await adminDisableUser(adminToken.value.trim(), row.username, !Number(row.disabled))
    await loadUsers()
  } catch (e) {
    tokenError.value = e.message || String(e)
  } finally {
    togglingUser.value = ''
  }
}

async function clearCache() {
  clearLoading.value = true
  clearResult.value = null
  tokenError.value = ''
  try {
    clearResult.value = await adminClearCache(adminToken.value.trim())
    await loadStats()
  } catch (e) {
    tokenError.value = e.message || String(e)
  } finally {
    clearLoading.value = false
  }
}

async function clearStatsMonitor() {
  if (!window.confirm('确认清空统计监控数据？（不清空问答记录库）')) return
  clearStatsLoading.value = true
  tokenError.value = ''
  try {
    await adminClearStats(adminToken.value.trim())
    window.alert('监控统计列表已清空')
    await loadStats()
  } catch (e) {
    tokenError.value = e.message || String(e)
  } finally {
    clearStatsLoading.value = false
  }
}

async function loadTraces() {
  tracesLoading.value = true
  try {
    const data = await adminTraces(adminToken.value.trim(), 50)
    traces.value = data.items || []
  } catch (e) {
    tokenError.value = e.message || String(e)
  } finally {
    tracesLoading.value = false
  }
}

async function openTrace(t) {
  const id = t.request_id
  if (!id) return
  try {
    traceDetail.value = await adminTraceDetail(adminToken.value.trim(), id)
  } catch (e) {
    tokenError.value = e.message || String(e)
  }
}

onMounted(() => {
  if (adminToken.value.trim()) loadStats()
})
</script>

<style scoped>
.admin-root {
  min-height: 100vh;
  background: var(--color-bg, #f7f7f5);
}
.admin-header {
  border-bottom: 1px solid var(--color-border, #e8e2d9);
  background: var(--color-surface, #fff);
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
  color: var(--color-text-secondary, #666);
  text-decoration: none;
}
.admin-back:hover { color: var(--color-primary, #8b6914); }
.admin-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text, #222);
}
.admin-main { padding: 32px 24px; }
.admin-content {
  max-width: 760px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 32px;
}
.admin-section {
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e8e2d9);
  border-radius: 8px;
  padding: 24px;
}
.admin-section-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text, #222);
  margin-bottom: 16px;
}
.admin-section-sub {
  font-weight: 400;
  color: #888;
  font-size: 12px;
}
.admin-token-row { display: flex; gap: 10px; }
.admin-token-input { flex: 1; }
.admin-error { margin-top: 8px; font-size: 13px; color: #cf1322; }
.admin-ok { margin-top: 8px; font-size: 13px; color: #389e0d; }
.admin-stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 12px;
}
.admin-stat-card {
  background: var(--color-bg, #f7f7f5);
  border: 1px solid var(--color-border, #e8e2d9);
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}
.admin-stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-primary, #8b6914);
  margin-bottom: 4px;
}
.admin-stat-label { font-size: 11px; color: #888; }
.admin-fail-wrap, .admin-feedback-wrap { margin-top: 20px; }
.admin-fail-list, .admin-feedback-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.admin-fail-item, .admin-feedback-item {
  padding: 12px;
  background: var(--color-bg, #f7f7f5);
  border: 1px solid var(--color-border, #e8e2d9);
  border-radius: 8px;
}
.admin-fail-question { font-size: 14px; margin-bottom: 6px; }
.admin-fail-meta, .admin-feedback-head {
  display: flex;
  gap: 12px;
  justify-content: space-between;
  font-size: 11px;
  color: #888;
}
.admin-feedback-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}
.admin-feedback-text { font-size: 13px; line-height: 1.6; }
.admin-feedback-empty { font-size: 13px; color: #888; }
.admin-cache-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.admin-cache-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.admin-cache-desc { font-size: 13px; color: #666; }
.admin-clear-result { margin-top: 10px; font-size: 13px; color: #389e0d; }
.admin-invite-create { display: flex; gap: 10px; margin-bottom: 12px; }
.admin-invite-input { flex: 1; }
.admin-table-wrap { overflow-x: auto; }
.admin-table {
  width: 100%;
  border-collapse: collapse;
}
.admin-table th,
.admin-table td {
  border: 1px solid var(--color-border, #e8e2d9);
  padding: 8px 10px;
  font-size: 12px;
  text-align: left;
}
.admin-table th { background: #fafafa; font-weight: 600; }
.admin-table-empty { text-align: center !important; color: #888 !important; }
.limit-input {
  width: 72px;
  padding: 2px 6px;
  border: 1px solid #ddd;
  border-radius: 4px;
}
.admin-user-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.tag-ok { color: #389e0d; }
.tag-fail { color: #cf1322; }
.admin-trace-list {
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
}
.admin-trace-list li {
  cursor: pointer;
  padding: 8px 0;
  border-bottom: 1px solid #eee;
  font-size: 13px;
}
.admin-trace-detail {
  margin-top: 12px;
  background: #f5f5f5;
  padding: 12px;
  overflow: auto;
  max-height: 50vh;
  font-size: 12px;
}
@media (max-width: 768px) {
  .admin-header-inner { padding: 10px 16px; }
  .admin-main { padding: 16px 12px; }
  .admin-section { padding: 16px; }
  .admin-content { gap: 16px; }
}
</style>

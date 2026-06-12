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

        <!-- Token 输入 -->
        <section class="admin-section">
          <div class="admin-section-title">管理员 Token</div>
          <div class="admin-token-row">
            <a-input-password
              v-model:value="adminToken"
              placeholder="输入 CN_ADMIN_TOKEN"
              class="admin-token-input"
              @pressEnter="loadStats"
            />
            <a-button type="primary" :loading="statsLoading" @click="loadStats">
              加载统计
            </a-button>
          </div>
          <div v-if="tokenError" class="admin-error">{{ tokenError }}</div>
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
              <p class="admin-placeholder">分功能限额设置 UI 将于 Phase 5 实现。</p>
            </a-tab-pane>

            <a-tab-pane key="materials" tab="资料管理">
              <p class="admin-placeholder">资料管理将于 Phase 5 实现。</p>
            </a-tab-pane>

            <a-tab-pane key="users" tab="用户">
              <div class="admin-table-wrap">
                <table class="admin-table">
                  <thead>
                    <tr>
                      <th>用户名</th>
                      <th>创建时间</th>
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
                    <tr v-else v-for="row in users" :key="row.id">
                      <td>{{ row.username }}</td>
                      <td>{{ row.created_at || '-' }}</td>
                      <td>
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
  </div>
</template>

<script setup>
import { ref } from 'vue'
import axios from 'axios'
import DebugPanel from '@/components/DebugPanel.vue'

const adminToken = ref('')
const stats = ref(null)
const statsLoading = ref(false)
const clearLoading = ref(false)
const clearStatsLoading = ref(false)
const tokenError = ref('')
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

function pct(val) {
  if (val == null) return '-'
  return (val * 100).toFixed(1) + '%'
}

async function loadStats() {
  if (!adminToken.value.trim()) {
    tokenError.value = '请输入 Token'
    return
  }
  statsLoading.value = true
  tokenError.value = ''
  clearResult.value = null
  try {
    const res = await axios.get('/api/qa/stats', {
      headers: { 'X-Admin-Token': adminToken.value.trim() }
    })
    stats.value = res.data
    await Promise.all([loadInvites(), loadUsers(), loadFeedbackStats()])
  } catch (e) {
    const status = e.response?.status
    if (status === 401) tokenError.value = 'Token 无效'
    else if (status === 503) tokenError.value = '服务不可用（Redis 未连接或 Token 未配置）'
    else tokenError.value = `请求失败（${status || '网络错误'}）`
    stats.value = null
    feedbackStats.value = null
  } finally {
    statsLoading.value = false
  }
}

function _adminHeaders() {
  return { 'X-Admin-Token': adminToken.value.trim() }
}

async function loadInvites() {
  if (!adminToken.value.trim()) return
  invitesLoading.value = true
  try {
    const res = await axios.get('/api/cn/auth/invites', {
      headers: _adminHeaders(),
    })
    invites.value = res.data?.items || []
  } catch (e) {
    const status = e.response?.status
    tokenError.value = `邀请码列表加载失败（${status || '网络错误'}）`
  } finally {
    invitesLoading.value = false
  }
}

async function loadUsers() {
  if (!adminToken.value.trim()) return
  usersLoading.value = true
  try {
    const res = await axios.get('/api/cn/auth/users', {
      headers: _adminHeaders(),
    })
    users.value = res.data?.items || []
  } catch (e) {
    const status = e.response?.status
    tokenError.value = `用户列表加载失败（${status || '网络错误'}）`
  } finally {
    usersLoading.value = false
  }
}

async function deleteUser(username) {
  if (!adminToken.value.trim() || !username) return
  deletingUser.value = username
  tokenError.value = ''
  try {
    await axios.delete(`/api/cn/auth/users/${encodeURIComponent(username)}`, {
      headers: _adminHeaders(),
    })
    await loadUsers()
  } catch (e) {
    const status = e.response?.status
    tokenError.value = `删除用户失败（${status || '网络错误'}）`
  } finally {
    deletingUser.value = ''
  }
}

function _randomCode() {
  return `INVITE-${Date.now().toString(36).toUpperCase()}`
}

async function createInvite() {
  if (!adminToken.value.trim()) {
    tokenError.value = '请先输入 Token'
    return
  }
  inviteLoading.value = true
  tokenError.value = ''
  try {
    const code = inviteCode.value.trim() || _randomCode()
    await axios.post(
      '/api/cn/auth/invite',
      { code },
      { headers: _adminHeaders() },
    )
    inviteCode.value = ''
    await loadInvites()
  } catch (e) {
    const status = e.response?.status
    tokenError.value = `生成邀请码失败（${status || '网络错误'}）`
  } finally {
    inviteLoading.value = false
  }
}

async function clearCache() {
  clearLoading.value = true
  clearResult.value = null
  try {
    const res = await axios.post('/api/qa/cache/clear', {}, {
      headers: { 'X-Admin-Token': adminToken.value.trim() }
    })
    const cleared = res.data
    await loadStats()
    clearResult.value = cleared
  } catch (e) {
    tokenError.value = `清除失败（${e.response?.status || '网络错误'}）`
  } finally {
    clearLoading.value = false
  }
}

async function clearStats() {
  if (!window.confirm('确认清空统计数据？')) return
  clearStatsLoading.value = true
  tokenError.value = ''
  try {
    await axios.post('/api/qa/stats/clear', {}, {
      headers: { 'X-Admin-Token': adminToken.value.trim() }
    })
    window.alert('统计数据已清空')
    await loadStats()
  } catch (e) {
    tokenError.value = `清空统计失败（${e.response?.status || '网络错误'}）`
  } finally {
    clearStatsLoading.value = false
  }
}

async function loadFeedbackStats() {
  if (!adminToken.value.trim()) return
  try {
    const res = await axios.get('/api/qa/feedback/stats', {
      headers: _adminHeaders(),
    })
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
</style>

<template>
  <div class="admin-root">
    <header class="admin-header">
      <div class="admin-header-inner">
        <a class="admin-back" href="#/">← 返回问答</a>
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
              placeholder="输入 QA_ADMIN_TOKEN"
              class="admin-token-input"
              @pressEnter="loadStats"
            />
            <a-button type="primary" :loading="statsLoading" @click="loadStats">
              加载统计
            </a-button>
          </div>
          <div v-if="tokenError" class="admin-error">{{ tokenError }}</div>
        </section>

        <!-- 统计面板 -->
        <section v-if="stats" class="admin-section">
          <div class="admin-section-title">用量统计</div>
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
        </section>

        <!-- 未找到记录 -->
        <section v-if="stats && stats.step_fail_records && stats.step_fail_records.length" class="admin-section">
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
        </section>

        <!-- 缓存管理 -->
        <section v-if="stats" class="admin-section">
          <div class="admin-section-title">缓存管理</div>
          <div class="admin-cache-row">
            <span class="admin-cache-desc">清除所有 <code>qa:cache:*</code> 缓存</span>
            <a-popconfirm
              title="确认清除所有问答缓存？"
              ok-text="确认"
              cancel-text="取消"
              @confirm="clearCache"
            >
              <a-button danger :loading="clearLoading">清除缓存</a-button>
            </a-popconfirm>
          </div>
          <div v-if="clearResult" class="admin-clear-result">
            已删除 {{ clearResult.deleted }} 条缓存（前缀：{{ clearResult.prefix }}）
          </div>
        </section>

      </div>
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import axios from 'axios'

const adminToken = ref('')
const stats = ref(null)
const statsLoading = ref(false)
const clearLoading = ref(false)
const tokenError = ref('')
const clearResult = ref(null)

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
  } catch (e) {
    const status = e.response?.status
    if (status === 401) tokenError.value = 'Token 无效'
    else if (status === 503) tokenError.value = '服务不可用（Redis 未连接或 Token 未配置）'
    else tokenError.value = `请求失败（${status || '网络错误'}）`
    stats.value = null
  } finally {
    statsLoading.value = false
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
</style>

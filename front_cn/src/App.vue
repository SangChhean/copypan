<template>
  <div class="app-shell">
    <header v-if="showTopBar" class="cn-navbar">
      <router-link to="/" class="cn-navbar-brand">文字AI服事</router-link>
      <div class="cn-navbar-right">
        <div v-if="usage" class="cn-navbar-usage">
          <span class="cn-navbar-usage-item">
            纲目制作 <em>{{ usage.outline?.used ?? 0 }}/{{ fmtLimit(usage.outline?.limit) }}</em>
          </span>
          <span class="cn-navbar-usage-item">
            纲目翻译 <em>{{ usage.translate?.used ?? 0 }}/{{ fmtLimit(usage.translate?.limit) }}</em>
          </span>
          <span class="cn-navbar-usage-item">
            职事问答 <em>{{ usage.qa?.used ?? 0 }}/{{ fmtLimit(usage.qa?.limit) }}</em>
          </span>
        </div>
        <button
          v-if="adminVisible"
          type="button"
          class="cn-navbar-admin"
          @click="router.push('/admin')"
        >
          管理后台
        </button>
        <button type="button" class="cn-navbar-logout" @click="onLogout">退出</button>
      </div>
    </header>
    <router-view />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import http from '@/utils/http.js'
import { clearAuth, getToken, isAdmin } from '@/utils/auth.js'

const route = useRoute()
const router = useRouter()
const usage = ref(null)

const showTopBar = computed(() => route.path !== '/login' && !!getToken())
const adminVisible = computed(() => isAdmin())

function fmtLimit(limit) {
  if (limit === -1 || limit == null) return '不限'
  return limit
}

async function loadUsage() {
  if (!getToken()) {
    usage.value = null
    return
  }
  try {
    const res = await http.get('/api/cn/auth/usage')
    usage.value = res.data || null
  } catch {
    usage.value = null
  }
}

function onLogout() {
  clearAuth()
  router.replace('/login')
}

watch(
  () => route.path,
  () => {
    if (showTopBar.value) loadUsage()
  }
)

onMounted(() => {
  if (showTopBar.value) loadUsage()
})
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--cn-bg-page);
}
</style>

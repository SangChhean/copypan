<template>
  <div class="app-shell">
    <header v-if="showTopBar" class="cn-navbar">
      <div class="cn-navbar-left"></div>
      <div class="cn-navbar-brand cn-nav-brand">全备供应</div>
      <div class="cn-navbar-right">
        <template v-if="!isMobile">
          <div v-if="usage" class="cn-navbar-usage">
            <span class="cn-navbar-usage-item cn-usage-label">
              纲目制作 <em class="cn-usage-val">{{ usage.outline?.used ?? 0 }}/{{ fmtLimit(usage.outline?.limit) }}</em>
            </span>
            <span class="cn-navbar-usage-item cn-usage-label">
              职事问答 <em class="cn-usage-val">{{ usage.qa?.used ?? 0 }}/{{ fmtLimit(usage.qa?.limit) }}</em>
            </span>
          </div>
          <button v-if="adminVisible" type="button" class="cn-navbar-admin" @click="router.push('/admin')">
            管理后台
          </button>
          <button type="button" class="cn-navbar-logout" @click="onLogout">退出</button>
        </template>
        <button
          v-if="isMobile"
          type="button"
          class="cn-navbar-menu-btn"
          @click="menuOpen = !menuOpen"
          aria-label="菜单"
        >
          <span class="cn-hamburger" :class="{ open: menuOpen }"></span>
        </button>
      </div>
      <div v-if="isMobile && menuOpen" class="cn-mobile-menu">
        <div v-if="usage" class="cn-mobile-usage">
          <span>纲目制作 <em>{{ usage.outline?.used ?? 0 }}/{{ fmtLimit(usage.outline?.limit) }}</em></span>
          <span>职事问答 <em>{{ usage.qa?.used ?? 0 }}/{{ fmtLimit(usage.qa?.limit) }}</em></span>
        </div>
        <button v-if="adminVisible" type="button" class="cn-mobile-menu-item" @click="router.push('/admin'); menuOpen = false">
          管理后台
        </button>
        <button type="button" class="cn-mobile-menu-item cn-mobile-menu-logout" @click="onLogout">
          退出登录
        </button>
      </div>
    </header>
    <router-view />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import http from '@/utils/http.js'
import { clearAuth, getToken, isAdmin, setIsAdmin } from '@/utils/auth.js'

const route = useRoute()
const router = useRouter()
const usage = ref(null)

const menuOpen = ref(false)
const windowWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 1024)
const isMobile = computed(() => windowWidth.value <= 640)

const showTopBar = computed(() => route.path !== '/login' && !!getToken())
const adminVisible = computed(() => isAdmin())

function onResize() {
  windowWidth.value = window.innerWidth
  if (!isMobile.value) menuOpen.value = false
}

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
    const [usageRes, meRes] = await Promise.all([
      http.get('/api/cn/auth/usage'),
      http.get('/api/cn/auth/me'),
    ])
    usage.value = usageRes.data || null
    setIsAdmin(!!meRes.data?.is_admin)
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
    menuOpen.value = false
    if (showTopBar.value) loadUsage()
  }
)

onMounted(() => {
  window.addEventListener('resize', onResize)
  if (showTopBar.value) loadUsage()
})
onUnmounted(() => {
  window.removeEventListener('resize', onResize)
})
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--cn-bg-page);
}

.cn-navbar-left {
  grid-column: 1;
  justify-self: start;
  display: flex;
  align-items: center;
  min-width: 40px;
}
.cn-navbar-menu-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.cn-hamburger {
  position: relative;
  display: block;
  width: 22px;
  height: 2px;
  background: #ffffff;
  transition: background 0.2s;
}
.cn-hamburger::before,
.cn-hamburger::after {
  content: '';
  position: absolute;
  left: 0;
  width: 22px;
  height: 2px;
  background: #ffffff;
  transition: transform 0.2s;
}
.cn-hamburger::before { top: -7px; }
.cn-hamburger::after { top: 7px; }
.cn-hamburger.open { background: transparent; }
.cn-hamburger.open::before { transform: rotate(45deg) translate(5px, 5px); }
.cn-hamburger.open::after { transform: rotate(-45deg) translate(5px, -5px); }
.cn-mobile-menu {
  position: absolute;
  top: 56px;
  left: 0;
  right: 0;
  background: #ffffff;
  border-top: 1px solid #CCE4F5;
  padding: 10px 0 8px;
  z-index: 100;
  box-shadow: 0 4px 12px rgba(27,108,168,0.1);
}
.cn-mobile-usage {
  display: flex;
  gap: 20px;
  padding: 8px 20px 12px;
  border-bottom: 1px solid #E0EDF6;
  margin-bottom: 4px;
  font-size: 13px;
  color: #1B6CA8;
  font-weight: 500;
}
.cn-mobile-usage em {
  font-style: normal;
  font-weight: 700;
}
.cn-mobile-menu-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 13px 20px;
  background: none;
  border: none;
  font-size: 15px;
  font-family: var(--cn-font);
  color: #1A2A3A;
  cursor: pointer;
  font-weight: 500;
}
.cn-mobile-menu-item:active {
  background: #EBF4FB;
  color: #1B6CA8;
}
.cn-mobile-menu-logout {
  border-top: 1px solid #E0EDF6;
  margin-top: 2px;
  color: #4A6A84;
}
@media (max-width: 640px) {
  .cn-navbar {
    position: relative;
  }
  .cn-navbar-brand {
    font-size: 22px !important;
  }
  .cn-navbar-right {
    min-width: 40px;
    justify-self: end;
  }
}
</style>

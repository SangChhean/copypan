<template>
  <div class="app-shell">
    <header v-if="showTopBar" class="app-topbar">
      <router-link to="/" class="app-topbar-home">Pansearch 中国站</router-link>
      <button
        v-if="adminVisible"
        type="button"
        class="app-topbar-admin"
        @click="router.push('/admin')"
      >
        管理后台
      </button>
    </header>
    <router-view />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getToken, isAdmin } from '@/utils/auth.js'

const route = useRoute()
const router = useRouter()

const showTopBar = computed(() => route.path !== '/login' && !!getToken())
const adminVisible = computed(() => isAdmin())
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
}

.app-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 16px;
  background: #001529;
  color: #fff;
  font-size: 14px;
}

.app-topbar-home {
  color: #55bbff;
  text-decoration: none;
}

.app-topbar-admin {
  border: 1px solid #55bbff;
  background: transparent;
  color: #55bbff;
  border-radius: 4px;
  padding: 4px 10px;
  cursor: pointer;
}

.app-topbar-admin:hover {
  background: rgba(85, 187, 255, 0.12);
}
</style>

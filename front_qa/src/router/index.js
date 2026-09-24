import { createRouter, createWebHashHistory } from 'vue-router'
import { bindRouter, clearAuth, getToken, isTokenExpired, notifyAuthExpired } from '@/utils/auth'

const routes = [
  {
    path: '/login',
    component: () => import('@/components/LoginPage.vue'),
  },
  {
    path: '/',
    component: () => import('@/components/QAPage.vue'),
  },
  {
    path: '/admin',
    component: () => import('@/components/AdminPage.vue'),
  },
  {
    path: '/debug',
    redirect: '/admin',
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

bindRouter(router)

router.beforeEach((to, _from, next) => {
  if (to.path === '/login') {
    next()
    return
  }
  const token = getToken()
  // /admin 维持原放行条件：只要本地有 token 就进入，不在这里校验过期，也不改管理页自身逻辑。
  if (to.path === '/admin') {
    if (!token) {
      next({ path: '/login', query: { redirect: to.fullPath } })
      return
    }
    next()
    return
  }
  if (!token || isTokenExpired(token)) {
    const hadToken = !!token
    clearAuth()
    if (hadToken) notifyAuthExpired()
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }
  next()
})

export default router

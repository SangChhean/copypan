import { createRouter, createWebHashHistory } from 'vue-router'
import { bindRouter, clearAuth, getToken, isAdmin, isTokenExpired, notifyAuthExpired } from '@/utils/auth.js'

const routes = [
  {
    path: '/login',
    component: () => import('@/components/LoginPage.vue'),
  },
  {
    path: '/',
    component: () => import('@/components/HomePage.vue'),
  },
  {
    path: '/qa',
    component: () => import('@/components/QAPage.vue'),
  },
  {
    path: '/ministry-search',
    component: () => import('@/components/MinistrySearchPage.vue'),
  },
  {
    path: '/admin',
    component: () => import('@/components/AdminPage.vue'),
  },
  {
    path: '/outline',
    component: () => import('@/components/OutlinePage.vue'),
  },
  {
    path: '/bibco',
    component: () => import('@/components/BibleCo.vue'),
  },
  {
    path: '/outline-translate',
    component: () => import('@/components/OutlineTranslate.vue'),
  },
  {
    path: '/zh-convert',
    component: () => import('@/components/ZhConvert.vue'),
  },
  {
    path: '/materials',
    component: () => import('@/components/MaterialsEntry.vue'),
  },
  {
    path: '/toolbox',
    component: () => import('@/components/ToolboxLanding.vue'),
  },
  {
    path: '/roundtable',
    component: () => import('@/components/RoundtablePage.vue'),
  },
  {
    path: '/ministry-pursuit',
    component: () => import('@/components/MinistryPursuitPage.vue'),
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
  if (!token) {
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }
  // 本地已能判断过期（或 token 损坏）时直接去登录页，不先进页面再等请求 401；
  // 密钥变更等本地判断不了的情况，仍由请求层的 401 统一处理兜底
  if (isTokenExpired(token)) {
    clearAuth()
    notifyAuthExpired()
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }
  if (to.path === '/admin' && !isAdmin()) {
    next('/')
    return
  }
  next()
})

export default router

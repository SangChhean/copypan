import { createRouter, createWebHashHistory } from 'vue-router'
import { getToken, isAdmin } from '@/utils/auth.js'

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
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to, _from, next) => {
  if (to.path === '/login') {
    next()
    return
  }
  if (!getToken()) {
    next('/login')
    return
  }
  if (to.path === '/admin' && !isAdmin()) {
    next('/')
    return
  }
  next()
})

export default router

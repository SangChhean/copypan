import { createRouter, createWebHashHistory } from 'vue-router'
import { getToken } from '@/utils/auth.js'

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
    path: '/downloads',
    component: () => import('@/components/PlaceholderPage.vue'),
    props: { title: '资料下载', building: true },
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
  next()
})

export default router

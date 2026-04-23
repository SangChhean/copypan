import { createRouter, createWebHashHistory } from 'vue-router'

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

router.beforeEach((to, _from, next) => {
  if (to.path === '/login') {
    next()
    return
  }
  const token = localStorage.getItem('qa_token')
  if (!token) {
    next('/login')
    return
  }
  next()
})

export default router

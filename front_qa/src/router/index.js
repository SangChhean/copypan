import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('@/components/QAPage.vue'),
  },
  {
    path: '/admin',
    component: () => import('@/components/AdminPage.vue'),
  },
]

export default createRouter({
  history: createWebHashHistory(),
  routes,
})

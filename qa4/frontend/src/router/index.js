import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '../utils/qa4Api.js'
import LoginPage from '../components/LoginPage.vue'
import Qa4Page from '../components/Qa4Page.vue'
import AdminPage from '../components/AdminPage.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginPage },
    { path: '/', component: Qa4Page },
    { path: '/admin', component: AdminPage },
  ],
})

router.beforeEach((to) => {
  // 与 3.0 一致：/admin 也需先登录（页面入口）；接口另用 X-Admin-Token
  if (to.path !== '/login' && !getToken()) {
    return '/login'
  }
})

export default router

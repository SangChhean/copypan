import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import router from './router/index.js'
import App from './App.vue'
import './style/index.css'

/** 刷新即可确认是否为当前 Vite 开发服务加载的前端（非打包产物）。 */
function qa4FrontendStamp() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
console.log(`[qa4] frontend build ${qa4FrontendStamp()}`)

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(Antd)
app.mount('#app')

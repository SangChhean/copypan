import { createApp } from 'vue'
import { createPinia } from 'pinia'
import 'ant-design-vue/dist/reset.css'
import router from './router/index.js'
import App from './App.vue'
import './style/index.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')

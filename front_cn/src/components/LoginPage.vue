<template>
  <div class="login-root">
    <div class="login-card">
      <div class="login-title">文字AI服事</div>
      <a-tabs v-model:activeKey="activeTab">
        <a-tab-pane key="login" tab="登录">
          <a-form layout="vertical" @submit.prevent="onLogin">
            <a-form-item label="用户名" class="login-field">
              <a-input v-model:value="loginForm.username" class="login-input" placeholder="请输入用户名" />
            </a-form-item>
            <a-form-item label="密码" class="login-field">
              <a-input-password v-model:value="loginForm.password" class="login-input" placeholder="请输入密码" @pressEnter="onLogin" />
            </a-form-item>
            <a-button type="primary" block class="login-submit-btn" :loading="loading" @click="onLogin">登录</a-button>
          </a-form>
        </a-tab-pane>

        <a-tab-pane key="register" tab="注册">
          <a-form layout="vertical" @submit.prevent="onRegister">
            <a-form-item label="邀请码" class="login-field">
              <a-input v-model:value="registerForm.invite_code" class="login-input" placeholder="请输入邀请码" />
            </a-form-item>
            <a-form-item label="用户名" class="login-field">
              <a-input v-model:value="registerForm.username" class="login-input" placeholder="请输入用户名" />
            </a-form-item>
            <a-form-item label="密码" class="login-field">
              <a-input-password v-model:value="registerForm.password" class="login-input" placeholder="请输入密码" @pressEnter="onRegister" />
            </a-form-item>
            <a-button type="primary" block class="login-submit-btn" :loading="loading" @click="onRegister">注册</a-button>
          </a-form>
        </a-tab-pane>
      </a-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import http from '@/utils/http.js'
import { setToken, setUsername } from '@/utils/auth.js'

const router = useRouter()
const activeTab = ref('login')
const loading = ref(false)

const loginForm = ref({ username: '', password: '' })
const registerForm = ref({ invite_code: '', username: '', password: '' })

async function onLogin() {
  const username = loginForm.value.username.trim()
  const password = loginForm.value.password
  if (!username || !password) {
    message.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const res = await http.post('/api/cn/auth/login', { username, password })
    const data = res.data || {}
    setToken(data.token || '')
    setUsername(data.username || username)
    message.success('登录成功')
    router.replace('/')
  } catch (e) {
    message.error(e?.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}

async function onRegister() {
  const invite_code = registerForm.value.invite_code.trim()
  const username = registerForm.value.username.trim()
  const password = registerForm.value.password
  if (!invite_code || !username || !password) {
    message.warning('请完整填写邀请码、用户名和密码')
    return
  }
  loading.value = true
  try {
    await http.post('/api/cn/auth/register', { invite_code, username, password })
    message.success('注册成功，请登录')
    loginForm.value.username = username
    loginForm.value.password = ''
    activeTab.value = 'login'
  } catch (e) {
    message.error(e?.response?.data?.detail || '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<style lang="less" scoped>
.login-root {
  min-height: 100vh;
  background: var(--cn-bg-page);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.login-card {
  width: 100%;
  max-width: 380px;
  background: var(--cn-bg-card);
  border: 1px solid var(--cn-border);
  border-radius: var(--cn-radius-lg);
  padding: 32px 28px 16px;
}

.login-title {
  font-size: 18px;
  font-weight: 500;
  text-align: center;
  margin-bottom: 20px;
  color: var(--cn-gold);
  letter-spacing: 0.08em;
}

.login-field {
  margin-bottom: 12px;
}

.login-submit-btn {
  margin-top: 8px;
}
</style>

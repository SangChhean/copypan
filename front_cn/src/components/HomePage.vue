<template>
  <div class="home-root">
    <header class="home-header">
      <div class="brand">Pansearch 中国站</div>
      <div class="usage-bar" v-if="usage">
        <span>纲目 {{ usage.outline?.used ?? 0 }}/{{ usage.outline?.limit ?? 0 }}</span>
        <span>翻译 {{ usage.translate?.used ?? 0 }}/{{ usage.translate?.limit ?? 0 }}</span>
        <span>问答 {{ usage.qa?.used ?? 0 }}/{{ usage.qa?.limit ?? 0 }}</span>
      </div>
      <div class="user">{{ username }}</div>
    </header>

    <main class="home-main">
      <h1 class="home-title">功能导航</h1>
      <div class="card-grid">
        <a-card
          v-for="item in features"
          :key="item.key"
          class="feature-card"
          :class="{ disabled: item.building }"
          hoverable
          @click="go(item)"
        >
          <div class="card-title">{{ item.title }}</div>
          <div class="card-desc">{{ item.desc }}</div>
          <a-tag v-if="item.building" color="default">建设中</a-tag>
        </a-card>
      </div>
    </main>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import http from '@/utils/http.js'
import { getUsername } from '@/utils/auth.js'

const router = useRouter()
const username = ref(getUsername())
const usage = ref(null)

const features = [
  { key: 'qa', title: 'QA问答', desc: '职事信息智能问答', path: '/qa', building: false },
  { key: 'outline', title: '纲目制作', desc: 'AI 纲目制作', path: '/outline', building: true },
  { key: 'bibco', title: '经文汇集', desc: '经文查询与汇集', path: '/bibco', building: false },
  { key: 'translate', title: '纲目翻译', desc: '纲目中英互译', path: '/outline-translate', building: false },
  { key: 'zh', title: '简繁互转', desc: '简繁文本转换', path: '/zh-convert', building: false },
  { key: 'downloads', title: '资料下载', desc: 'LSM 资料下载', path: '/downloads', building: true },
]

function go(item) {
  if (item.building) return
  router.push(item.path)
}

async function loadUsage() {
  try {
    const res = await http.get('/api/cn/auth/usage')
    usage.value = res.data || null
  } catch {
    usage.value = null
  }
}

onMounted(() => {
  loadUsage()
})
</script>

<style lang="less" scoped>
.home-root {
  min-height: 100vh;
  background: var(--color-bg);
}

.home-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
}

.brand {
  font-weight: 700;
  color: var(--color-primary);
}

.usage-bar {
  display: flex;
  gap: 12px;
  margin-left: auto;
  color: var(--color-text-secondary);
  font-size: 14px;
}

.user {
  color: var(--color-text-secondary);
  font-size: 14px;
}

.home-main {
  max-width: 960px;
  margin: 0 auto;
  padding: 32px 24px;
}

.home-title {
  margin: 0 0 24px;
  font-size: 20px;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.feature-card {
  cursor: pointer;
}

.feature-card.disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.card-title {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 8px;
}

.card-desc {
  color: var(--color-text-secondary);
  margin-bottom: 8px;
}
</style>

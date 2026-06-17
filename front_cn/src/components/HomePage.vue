<template>
  <div class="home-root">
    <main class="home-main">
      <div class="home-section">
        <div class="home-section-label">工具箱</div>
        <div class="card-grid">
          <div
            v-for="item in toolboxFeatures"
            :key="item.key"
            class="feature-card cn-home-card"
            :class="{ disabled: item.building }"
            @click="go(item)"
          >
            <div class="card-top">
              <div class="card-icon">
                <component :is="item.icon" />
              </div>
              <span v-if="item.quotaKey && usage" class="card-quota cn-card-badge">
                {{ quotaText(item.quotaKey) }}
              </span>
            </div>
            <div class="card-title cn-card-title">{{ item.title }}</div>
            <div class="card-desc cn-card-desc">{{ item.desc }}</div>
          </div>
        </div>
      </div>

      <hr class="home-divider" />

      <div class="home-section">
        <div class="home-section-label">资料下载</div>
        <div class="card-grid">
          <div
            v-for="item in materialsFeatures"
            :key="item.key"
            class="feature-card cn-home-card"
            @click="go(item)"
          >
            <div class="card-top">
              <div class="card-icon">
                <component :is="item.icon" />
              </div>
            </div>
            <div class="card-title cn-card-title">{{ item.title }}</div>
            <div class="card-desc cn-card-desc">{{ item.desc }}</div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  CommentOutlined,
  FileTextOutlined,
  BookOutlined,
  FontSizeOutlined,
  CloudDownloadOutlined,
} from '@ant-design/icons-vue'
import http from '@/utils/http.js'

const router = useRouter()
const usage = ref(null)

const features = [
  {
    key: 'qa',
    title: '职事问答',
    desc: '基于职事信息的智能问答',
    path: '/qa',
    icon: CommentOutlined,
    quotaKey: 'qa',
    building: false,
  },
  {
    key: 'outline',
    title: '纲目制作',
    desc: '基于纲目主题、性质及负担点生成职事纲目',
    path: '/outline',
    icon: FileTextOutlined,
    quotaKey: 'outline',
    building: false,
  },
  {
    key: 'bibco',
    title: '经文汇集',
    desc: '中英文经文查询与下载',
    path: '/bibco',
    icon: BookOutlined,
    building: false,
  },
  {
    key: 'zh',
    title: '简繁互转',
    desc: '简繁转换与易错字检查',
    path: '/zh-convert',
    icon: FontSizeOutlined,
    building: false,
  },
  {
    key: 'conference',
    title: '节期特会相关纲目',
    desc: '一年七次特会相关纲目',
    path: '/materials?type=conference',
    icon: CloudDownloadOutlined,
    building: false,
  },
  {
    key: 'pastoral',
    title: '牧养材料',
    desc: '新人牧养和排聚会材料',
    path: '/materials?type=pastoral',
    icon: CloudDownloadOutlined,
    building: false,
  },
]

const toolboxFeatures = features.filter(f => !['pastoral', 'conference'].includes(f.key))
const materialsFeatures = features.filter(f => ['pastoral', 'conference'].includes(f.key))

function quotaText(key) {
  const u = usage.value?.[key]
  if (!u) return ''
  const lim = u.limit === -1 ? '不限' : u.limit
  return `${u.used ?? 0}/${lim}`
}

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
  flex: 1;
  background: var(--cn-bg-page);
}

.home-main {
  max-width: var(--cn-content-max-width);
  margin: 0 auto;
  padding: 32px 24px 48px;
}

.card-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.feature-card {
  background: var(--cn-bg-card);
  border: 0.5px solid var(--cn-border);
  border-radius: 12px;
  padding: 28px 26px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;

  &:hover:not(.disabled) {
    border-color: var(--cn-gold);
  }
}

.feature-card.disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 14px;
}

.card-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--cn-gold-light);
  border-radius: var(--cn-radius-md);
  color: var(--cn-gold);
  font-size: 18px;
}

.card-quota {
  background: var(--cn-gold-light);
  color: var(--cn-gold);
  padding: 2px 8px;
  border-radius: 10px;
  line-height: 1.6;
}

.card-title {
  color: var(--cn-text-primary);
  margin-bottom: 8px;
}

.card-desc {
  color: var(--cn-text-secondary);
  line-height: 1.55;
}

.home-section {
  margin-bottom: 0;
}
.home-section-label {
  font-size: 18px;
  font-weight: 500;
  color: var(--cn-text-primary);
  letter-spacing: 0.05em;
  margin-bottom: 16px;
}
.home-divider {
  border: none;
  border-top: 0.5px solid var(--cn-border);
  margin: 32px 0;
}
.feature-card-wide {
  max-width: 100%;
}

@media (max-width: 640px) {
  .card-grid {
    grid-template-columns: 1fr;
  }
}
</style>

<template>
  <div class="home-root">
    <main class="home-main">
      <div class="card-grid">
        <div
          v-for="item in features"
          :key="item.key"
          class="feature-card"
          :class="{ disabled: item.building }"
          @click="go(item)"
        >
          <div class="card-top">
            <div class="card-icon">
              <component :is="item.icon" />
            </div>
            <span v-if="item.quotaKey && usage" class="card-quota">
              {{ quotaText(item.quotaKey) }}
            </span>
          </div>
          <div class="card-title">{{ item.title }}</div>
          <div class="card-desc">{{ item.desc }}</div>
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
  SwapOutlined,
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
    desc: '生成职事纲目与负担说明',
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
    key: 'translate',
    title: '纲目翻译',
    desc: '中英双向纲目互译',
    path: '/outline-translate',
    icon: SwapOutlined,
    quotaKey: 'translate',
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
    key: 'downloads',
    title: '资料下载',
    desc: '职事相关资料浏览下载',
    path: '/materials',
    icon: CloudDownloadOutlined,
    building: false,
  },
]

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
  max-width: 960px;
  margin: 0 auto;
  padding: 32px 24px 48px;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.feature-card {
  background: var(--cn-bg-card);
  border: 0.5px solid var(--cn-border);
  border-radius: var(--cn-radius-lg);
  padding: 18px 16px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;

  &:hover:not(.disabled) {
    border-color: var(--cn-gold);
    box-shadow: var(--shadow);
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
  margin-bottom: 12px;
}

.card-icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--cn-gold-light);
  border-radius: var(--cn-radius-md);
  color: var(--cn-gold);
  font-size: 16px;
}

.card-quota {
  background: var(--cn-gold-light);
  color: var(--cn-gold);
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 10px;
  line-height: 1.6;
}

.card-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--cn-text-primary);
  margin-bottom: 6px;
}

.card-desc {
  font-size: 11px;
  color: var(--cn-text-secondary);
  line-height: 1.5;
}
</style>

<template>
  <div class="landing-root">
    <main class="landing-main">
      <button type="button" class="landing-back" @click="router.push('/')">返回首页</button>
      <div class="home-section-label">资料下载</div>
      <div class="card-grid">
        <div
          v-for="item in materialsFeatures"
          :key="item.key"
          class="feature-card cn-home-card"
          @touchstart="onTouchStart($event)"
          @touchend.prevent="onTouchEnd(item, $event)"
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
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { features, MATERIALS_FEATURE_KEYS } from '@/data/homeFeatures.js'

const router = useRouter()

const materialsFeatures = computed(() =>
  MATERIALS_FEATURE_KEYS.map(key => features.find(f => f.key === key)).filter(Boolean)
)

let touchStartX = 0
let touchStartY = 0
const TAP_MOVE_THRESHOLD = 10

function onTouchStart(e) {
  const t = e.touches[0]
  touchStartX = t.clientX
  touchStartY = t.clientY
}

function onTouchEnd(item, e) {
  const t = e.changedTouches[0]
  const dx = Math.abs(t.clientX - touchStartX)
  const dy = Math.abs(t.clientY - touchStartY)
  if (dx > TAP_MOVE_THRESHOLD || dy > TAP_MOVE_THRESHOLD) {
    return
  }
  go(item)
}

function go(item) {
  if (item.building) return
  router.push(item.path)
}
</script>

<style lang="less" scoped>
.landing-root {
  flex: 1;
  background: var(--cn-bg-page);
}

.landing-main {
  max-width: var(--cn-content-max-width);
  margin: 0 auto;
  padding: 32px 24px 48px;
}

.landing-back {
  margin-bottom: 20px;
  padding: 6px 14px;
  border: 1px solid #CCE4F5;
  border-radius: 8px;
  background: #fff;
  color: #1B6CA8;
  cursor: pointer;
  font-size: 14px;
}

.home-section-label {
  font-size: 18px;
  font-weight: 500;
  color: var(--cn-text-primary);
  letter-spacing: 0.05em;
  margin-bottom: 16px;
}

.card-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.feature-card {
  background: #EBF4FB;
  border: 1px solid #CCE4F5;
  border-radius: 12px;
  padding: 28px 26px;
  cursor: pointer;
  touch-action: manipulation;
  transition: border-color 0.2s, box-shadow 0.2s;

  &:hover:not(.disabled) {
    border-color: #1B6CA8;
    box-shadow: 0 4px 16px rgba(27,108,168,0.1);
  }
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
  background: #fff;
  border-radius: var(--cn-radius-md);
  color: #1B6CA8;
  font-size: 18px;
}

.card-title {
  color: var(--cn-text-primary);
  margin-bottom: 8px;
}

.card-desc {
  color: var(--cn-text-secondary);
  line-height: 1.55;
}

@media (max-width: 640px) {
  .card-grid {
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .feature-card {
    padding: 16px 14px;
  }
  .card-icon {
    width: 32px;
    height: 32px;
    font-size: 15px;
  }
  .card-title {
    font-size: 13px;
  }
  .card-desc {
    font-size: 11px;
  }
}
</style>

<template>
  <div class="home-root">
    <main class="home-main">
      <!-- 职事信息轮播 -->
      <div ref="ministryCarouselRef" class="ministry-carousel">
        <div class="mc-track">
          <div class="mc-slide mc-active" data-slide="0">
            <p class="mc-title">全备供应——帮助各地方召会进行家庭烹煮与按时分粮</p>
            <div class="mc-verse">
              <span class="mc-vref">西一28</span>
              <p class="mc-vtxt">我们宣扬祂，是用全般的智慧警戒各人，教导各人，好将各人在基督里成熟的献上；</p>
            </div>
            <p class="mc-btxt">主的恢复遍及全球各地，每个地方召会都有不同的属灵需要。本网站的建立，乃是为着帮助各地方召会能够各自来烹煮属灵的食物，按时分粮给不同属灵需要的圣徒。</p>
            <p class="mc-btxt">愿主兴起各地的弟兄姊妹，作分解主话的工人，并作按时分粮的管家，将众圣徒在基督里成熟的献上，共同建造基督的身体。</p>
          </div>
          <div class="mc-slide" data-slide="1">
            <p class="mc-title">家庭烹煮</p>
            <div class="mc-verse">
              <span class="mc-vref">提后二15</span>
              <p class="mc-vtxt">你当竭力将自己呈献神前，得蒙称许，作无愧的工人，正直的分解真理的话。</p>
            </div>
            <p class="mc-qtxt">「我不愿为所有的召会预备这样的信息，嘱咐众召会读同样的信息。在美国的许多召会，各召会每主日都需要不同种类的属灵帮助。在主日，不同的召会需要不同的供应。你不能将同样的饭食，供应病房中的每个人。对那些胃有毛病的人，你需要供应某种饭食；对那些心脏有问题的人，你需要供应另一种饭食。你必须有不同的饭食，以喂养不同的人。身为你们所在之地的长老，只有你们才知道你们的家人需要怎样的食物，别人不知道你们家人的需要。这事我考虑得相当多，我觉得必须由每个地方召会个别来作。家庭的烹煮必须由各家个别来作。虽然在原则上，所有的地方召会该是同样的，但在这一面，所有的召会无法是同样的。」</p>
            <p class="mc-qsrc">——李常受文集一九八六年第一册，长老训练，第八册—主当前行动的命脉，第四章</p>
          </div>
          <div class="mc-slide" data-slide="2">
            <p class="mc-title">按时分粮</p>
            <div class="mc-verse">
              <span class="mc-vref">太二四45</span>
              <p class="mc-vtxt">这样，谁是那忠信又精明的奴仆，为主人所派，管理他的家人，按时分粮给他们？</p>
            </div>
            <p class="mc-qtxt">「我一直在考虑，在排聚集用什么材料教导人最好。我们有生命课程和真理课程。虽然这些课程写得非常好，我觉得它们不很合式，因为内容太多了，新人不易消化。甚至晨兴圣言也可能不适合在排聚集里的新人。用太多食物喂养人是不好的；我们必须给他们合式的分量。在希伯来五章十二至十四节，保罗提到两种食物，就是奶和干粮。我们不该试图用干粮喂孩子。因此，我们需要有人劳苦，为排聚集编写一些合式的材料，可用作奶来喂养新人。为了使排聚集里的教导和交通有益处，需要有一些材料作为指引。我盼望有些弟兄们被主兴起来，为着排聚集编写一些合式的材料。」</p>
            <p class="mc-qsrc">——李常受文集一九九一至一九九二年第三册，关于活力排之急切需要的交通，第四章</p>
          </div>
        </div>
        <div class="mc-dots">
          <button class="mc-dot mc-dot-active" data-idx="0"></button>
          <button class="mc-dot" data-idx="1"></button>
          <button class="mc-dot" data-idx="2"></button>
        </div>
      </div>

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

      <hr class="home-divider" />

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
const ministryCarouselRef = ref(null)

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
  {
    key: 'children',
    title: '儿童服事材料',
    desc: '儿童服事相关材料',
    path: '/materials?type=children',
    icon: CloudDownloadOutlined,
    building: false,
  },
  {
    key: 'family365',
    title: '家庭時光365',
    desc: '以家庭为单位的共同追求材料',
    path: '/materials?type=family365',
    icon: CloudDownloadOutlined,
    building: false,
  },
]

const toolboxFeatures = features.filter(f => !['pastoral', 'conference', 'children', 'family365'].includes(f.key))
const materialsFeatures = features.filter(f => ['pastoral', 'conference', 'children', 'family365'].includes(f.key))

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

  const root = ministryCarouselRef.value
  if (!root) return
  const slides = root.querySelectorAll('.mc-slide')
  const dots = root.querySelectorAll('.mc-dot')
  let cur = 0

  function show(i) {
    slides.forEach(s => s.classList.remove('mc-active'))
    dots.forEach(d => d.classList.remove('mc-dot-active'))
    slides[i].classList.add('mc-active')
    dots[i].classList.add('mc-dot-active')
    cur = i
  }

  let timer = setInterval(() => show((cur + 1) % 3), 7000)

  dots.forEach(d => {
    d.addEventListener('click', () => {
      show(+d.dataset.idx)
      clearInterval(timer)
      timer = setInterval(() => show((cur + 1) % 3), 7000)
    })
  })
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
  background: #EBF4FB;
  border: 1px solid #CCE4F5;
  border-radius: 12px;
  padding: 28px 26px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;

  &:hover:not(.disabled) {
    border-color: #1B6CA8;
    box-shadow: 0 4px 16px rgba(27,108,168,0.1);
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
  background: #fff;
  border-radius: var(--cn-radius-md);
  color: #1B6CA8;
  font-size: 18px;
}

.card-quota {
  background: #fff;
  color: #1B6CA8;
  padding: 2px 8px;
  border-radius: 10px;
  line-height: 1.6;
  font-weight: 600;
  font-size: 11px;
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

.ministry-carousel {
  margin-bottom: 2rem;
}
.mc-track {
  border-radius: 12px;
  border: 0.5px solid #CCE4F5;
  background: #EBF4FB;
  overflow: hidden;
}
.mc-slide {
  display: none;
  padding: 1.75rem 2rem;
  min-height: 300px;
  box-sizing: border-box;
  flex-direction: column;
  gap: 0.9rem;
}
.mc-slide.mc-active {
  display: flex;
}
.mc-title {
  font-size: 18px;
  font-weight: 700;
  color: #000000;
  margin: 0;
  letter-spacing: 0.01em;
}
.mc-verse {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  padding: 0.5rem 0.85rem;
  background: rgba(255, 255, 255, 0.7);
  border-left: 3px solid #1B6CA8;
  border-radius: 0 6px 6px 0;
}
.mc-vref {
  font-size: 12.5px;
  font-weight: 500;
  color: #1B6CA8;
  white-space: nowrap;
  flex-shrink: 0;
}
.mc-vtxt {
  font-size: 14px;
  color: #000000;
  line-height: 1.8;
  margin: 0;
}
.mc-btxt {
  font-size: 14px;
  color: #000000;
  line-height: 1.8;
  margin: 0;
  text-indent: 2em;
}
.mc-qtxt {
  font-size: 14px;
  color: #000000;
  line-height: 1.8;
  margin: 0;
}
.mc-qsrc {
  font-size: 12px;
  color: #4A6A84;
  margin: 0.25rem 0 0;
  text-align: right;
}
.mc-dots {
  display: flex;
  gap: 10px;
  justify-content: center;
  margin-top: 0.9rem;
}
.mc-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #CCE4F5;
  cursor: pointer;
  border: none;
  padding: 0;
  transition: background 0.2s;
}
.mc-dot.mc-dot-active {
  background: #1B6CA8;
}
</style>

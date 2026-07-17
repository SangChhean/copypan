<template>
  <div class="ms-root">
    <div class="cn-page-head">
      <button type="button" class="cn-back" @click="router.push('/')">‹‹ 返回</button>
      <span class="cn-page-title">职事信息搜寻</span>
    </div>

    <div class="ms-content">
      <!-- 主分类 -->
      <div class="ms-cats">
        <button
          v-for="item in mainCats"
          :key="item.val"
          type="button"
          class="ms-cat-btn"
          :class="{ active: selectedIndex === item.val }"
          @click="onSelectIndex(item.val)"
        >
          {{ item.lab }}
        </button>
      </div>

      <!-- 搜索栏 -->
      <div class="ms-search-bar">
        <div class="ms-search-row">
          <a-select
            v-if="selectedIndex === '0'"
            v-model:value="selVar1"
            class="ms-select"
            :options="showCatsOne"
            :field-names="{ label: 'lab', value: 'val' }"
            style="width: 72px"
          />
          <a-select
            v-model:value="selVar2"
            class="ms-select"
            :options="showCats"
            :field-names="{ label: 'lab', value: 'val' }"
            style="width: 88px"
          />
          <a-input-search
            v-model:value="inputVar"
            class="ms-input"
            :placeholder="placeholder"
            :status="status"
            :disabled="inputDis"
            enter-button="搜索"
            allow-clear
            @search="onSearch"
            @change="onInputChange"
          />
        </div>
        <div class="ms-mode-row">
          <a-radio-group v-model:value="searchCat" button-style="solid" size="small">
            <a-radio-button v-for="item in matchModes" :key="item.val" :value="item.val">
              {{ item.lab }}
            </a-radio-button>
          </a-radio-group>
        </div>
      </div>

      <!-- 离线下载占位 -->
      <div class="ms-offline">
        <div class="ms-offline-text">
          <strong>下载离线版</strong>
          <span>可在无网络环境下本地搜索职事信息（部署后提供下载）</span>
        </div>
        <a-button disabled type="default">即将提供下载</a-button>
      </div>

      <!-- 欢迎 / 说明 -->
      <div v-if="viewState === 'welcome'" class="ms-welcome">
        <div class="ms-welcome-title">职事信息搜寻</div>
        <div class="ms-welcome-sub">分类筛选 · 关键词搜索 · 原文阅读</div>
        <div class="ms-hint">
          <div>A 类：经文、注解、生命读经、倪文集、李文集、其他</div>
          <div>B 类：A 类 + 诗歌、节期纲目</div>
        </div>
      </div>

      <!-- 加载 -->
      <div v-else-if="viewState === 'loading'" class="ms-loading">
        <a-spin size="large" />
        <span>正在搜索…</span>
      </div>

      <!-- 空结果 -->
      <div v-else-if="viewState === 'empty'" class="ms-empty">
        未找到相关结果，请尝试其他关键词或分类
      </div>

      <!-- 结果列表 -->
      <div v-else-if="viewState === 'results'" class="ms-results">
        <div class="ms-total">
          共搜索到 <em>{{ total }}</em> 条
        </div>

        <div v-for="item in results" :key="item.id" class="ms-card">
          <div class="ms-card-tags">
            <button
              v-for="tag in displayTags(item.tags)"
              :key="tag[0] + tag[1]"
              type="button"
              class="ms-tag"
              @click="openReading(tag[1])"
            >
              {{ tag[0] }}
            </button>
          </div>
          <div class="ms-card-title">{{ item.title }}</div>
          <div v-if="item.up" class="ms-card-up" v-html="item.up"></div>
          <div v-if="item.down" class="ms-card-down" v-html="item.down"></div>
          <div v-if="item.source?.length" class="ms-card-source">
            <span v-for="(s, i) in item.source" :key="i">{{ s }}</span>
          </div>
        </div>

        <div class="ms-pages">
          <a-pagination
            v-model:current="currentPage"
            v-model:page-size="pageSize"
            :total="total"
            :page-size-options="pageSizeOptions"
            size="small"
            show-size-changer
            show-quick-jumper
            @change="onPageChange"
            @showSizeChange="onPageChange"
          />
        </div>
      </div>
    </div>

    <!-- 阅读原文弹窗 -->
    <a-modal
      v-model:open="readingOpen"
      width="100%"
      wrap-class-name="ms-reading-modal"
      :footer="null"
      :destroy-on-close="true"
      @cancel="closeReading"
    >
      <template #title>
        <span class="ms-reading-title">阅读原文</span>
      </template>

      <div v-if="readingLoading" class="ms-loading">
        <a-spin />
        <span>加载中…</span>
      </div>
      <div v-else-if="readingError" class="ms-empty">{{ readingError }}</div>
      <div v-else-if="showData" class="ms-reading-body">
        <a-breadcrumb class="ms-breadcrumb">
          <a-breadcrumb-item v-for="(b, i) in showData.bread || []" :key="i">
            <a v-if="b.refid" @click="openReading(b.refid)">{{ b.text }}</a>
            <span v-else>{{ b.text }}</span>
          </a-breadcrumb-item>
        </a-breadcrumb>

        <div v-if="showData.showButtons == '1'" class="ms-reading-actions">
          <a-button
            size="small"
            :type="isHeading ? 'default' : 'primary'"
            @click="isHeading = false"
          >查看整篇</a-button>
          <a-button
            size="small"
            :type="isHeading ? 'primary' : 'default'"
            @click="isHeading = true"
          >只看标题</a-button>
        </div>

        <a-divider style="margin: 12px 0" />

        <div v-if="showData.cells" class="ms-cells">
          <a-button
            v-for="(c, i) in showData.cells"
            :key="i"
            type="primary"
            @click="openReading(c.refid)"
          >{{ c.text }}</a-button>
        </div>
        <div v-else-if="showData.toc" class="ms-toc">
          <div
            v-for="(t, i) in showData.toc"
            :key="i"
            :class="['ms-toc-item', t.type]"
            v-html="hiLight(t.text)"
            @click="openReading(t.refid)"
          ></div>
        </div>
        <div v-else>
          <div v-if="hideEng" class="ms-only-zh">
            <div
              v-for="(line, i) in showData.zh || []"
              :key="i"
              :class="line[1]"
              v-html="hiLight(line[0])"
            ></div>
          </div>
          <div v-else class="ms-bilingual">
            <div class="ms-col">
              <div
                v-for="(line, i) in showData.zh || []"
                :key="'zh-' + i"
                :class="line[1]"
                v-html="hiLight(line[0])"
              ></div>
            </div>
            <div class="ms-col">
              <div
                v-for="(line, i) in showData.en || []"
                :key="'en-' + i"
                :class="line[1]"
                v-html="hiLight(line[0])"
              ></div>
            </div>
          </div>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import http from '@/utils/http.js'

const router = useRouter()

const mainCats = [
  { lab: '全部', val: '0' },
  { lab: '圣经', val: '1' },
  { lab: '生命读经', val: '2' },
  { lab: '倪文集', val: '3' },
  { lab: '李文集', val: '4' },
  { lab: '其他', val: '5' },
  { lab: '诗歌', val: '6' },
  { lab: '节期纲目', val: '7' },
]

const catLabels = {
  a: '全部',
  b: '书名',
  c: '总题',
  d: '篇题',
  e: '标题',
  f: '大纲',
  g: '摘录',
  h: '大本',
  i: '经文',
  j: '注解',
  k: '系列',
  l: '纲目',
  m: '禁用',
}

const matchModes = [
  { lab: '模糊', val: 'a' },
  { lab: '平衡', val: 'b' },
  { lab: '精确', val: 'c' },
]

const showCatsOne = [
  { lab: 'A类', val: 'a' },
  { lab: 'B类', val: 'b' },
]

const selectedIndex = ref('0')
const selVar1 = ref('a')
const selVar2 = ref('a')
const searchCat = ref('a')
const inputVar = ref('')
const status = ref('')
const placeholder = ref('输入搜索内容')
const inputDis = ref(false)

const viewState = ref('welcome') // welcome | loading | results | empty
const results = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)
const pageSizeOptions = ['10', '20', '30', '40', '50']
const hilights = ref([])

const readingOpen = ref(false)
const readingLoading = ref(false)
const readingError = ref('')
const readingSource = ref(null)
const isHeading = ref(false)
const hideEng = ref(false)
const currentRefid = ref('')

function getCats(keys) {
  return keys.split('').map((k) => ({ lab: catLabels[k] || k, val: k }))
}

const showCats = computed(() => {
  const idx = selectedIndex.value
  let keys = 'm'
  if (idx === '0') keys = 'abde'
  else if (idx === '1') keys = 'ij'
  else if (idx === '2') keys = 'ade'
  else if (idx === '3') keys = 'abde'
  else if (idx === '4') keys = 'abde'
  else if (idx === '5') keys = 'ade'
  else if (idx === '6') keys = 'h'
  else if (idx === '7') keys = 'acdf'
  return getCats(keys)
})

watch(showCats, (arr) => {
  if (arr.length && !arr.some((x) => x.val === selVar2.value)) {
    selVar2.value = arr[0].val
  }
}, { immediate: true })

watch(selVar2, (v) => {
  inputDis.value = v === 'm'
})

function onSelectIndex(val) {
  selectedIndex.value = val
  currentPage.value = 1
  if (inputVar.value.trim()) onSearch()
}

function onInputChange() {
  status.value = ''
  placeholder.value = '输入搜索内容'
}

function buildArgs() {
  const cat1 = selectedIndex.value === '0' ? selVar1.value : selectedIndex.value
  return `${cat1}-${selVar2.value}-${searchCat.value}-${currentPage.value}-${pageSize.value}`
}

async function onSearch() {
  const input = inputVar.value.trim()
  if (!input) {
    status.value = 'error'
    placeholder.value = '搜索内容不能为空'
    return
  }
  if (selVar2.value === 'm') {
    viewState.value = 'empty'
    return
  }

  hilights.value = input.split(/ +/g).filter(Boolean)
  viewState.value = 'loading'

  const form = new FormData()
  form.append('input', input)
  form.append('args', buildArgs())

  try {
    const res = await http.post('/api/cn/es_search/search', form)
    const data = res.data || {}
    total.value = data.total || 0
    results.value = Array.isArray(data.msg) ? data.msg : []
    viewState.value = total.value === 0 ? 'empty' : 'results'
  } catch (e) {
    if (e?.response?.status === 401) {
      router.push('/login')
      return
    }
    message.error(e?.response?.data?.detail || '搜索失败，请稍后重试')
    viewState.value = 'empty'
  }
}

function onPageChange() {
  if (inputVar.value.trim()) onSearch()
}

/** 直接使用后端返回的 tags；不要用搜索结果自身的 id */
function displayTags(tags) {
  if (!Array.isArray(tags) || !tags.length) return []
  return tags.filter((t) => Array.isArray(t) && t.length >= 2 && t[1] && !String(t[1]).includes('outline'))
}

function closeReading() {
  readingOpen.value = false
  readingSource.value = null
  readingError.value = ''
  currentRefid.value = ''
}

/**
 * 打开阅读原文：必须使用 tags 里的 refid（如 cwwn_1-1#0），
 * 不能用搜索命中文档的 id（如 cwwn_1-1#0-7）。
 */
async function openReading(refidRaw) {
  if (!refidRaw) return
  let refid = String(refidRaw)
  let headingOnly = false

  if (refid.includes('outline')) {
    message.info('大纲视图暂未提供，请使用「查看整篇」或「只看标题」')
    return
  }
  if (refid.includes('heading')) {
    refid = refid.replace('-heading', '')
    headingOnly = true
  }

  currentRefid.value = refid
  isHeading.value = headingOnly
  readingOpen.value = true
  readingLoading.value = true
  readingError.value = ''
  readingSource.value = null

  const form = new FormData()
  form.append('refid', refid)

  try {
    const res = await http.post('/api/cn/es_search/reading', form)
    const src = res.data?._source
    if (!src) {
      readingError.value = '原文不存在或暂不可用'
      return
    }
    readingSource.value = src
    hideEng.value = !src.en
    await nextTick()
    const el = document.querySelector('.ms-reading-modal .ant-modal-body')
    if (el) el.scrollTop = 0
  } catch (e) {
    if (e?.response?.status === 401) {
      router.push('/login')
      return
    }
    readingError.value = e?.response?.data?.detail || '加载原文失败'
  } finally {
    readingLoading.value = false
  }
}

const HEADING_TYPES = ['heading', 'ot1', 'bible_reading', 'b_read', 'title', 'bookname']

const showData = computed(() => {
  const res = readingSource.value
  if (!res) return null
  if (!isHeading.value) return res

  const en = res.en || []
  const zh = res.zh || []
  return {
    en: en.filter((item) => HEADING_TYPES.includes(item[1])),
    zh: zh.filter((item) => HEADING_TYPES.includes(item[1])),
    type: res.type,
    refid: res.refid,
    bread: res.bread,
    showButtons: res.showButtons,
    cells: res.cells,
    toc: res.toc,
  }
})

function hiLight(text) {
  if (!text) return ''
  let out = String(text)
  hilights.value.forEach((kw) => {
    if (!kw) return
    out = out.split(kw).join(`<em>${kw}</em>`)
  })
  return out
}
</script>

<style scoped>
.ms-root {
  min-height: 100vh;
  background: #fff;
}

.ms-content {
  max-width: var(--cn-content-max-width, 860px);
  margin: 0 auto;
  padding: 16px 16px 48px;
}

.ms-cats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.ms-cat-btn {
  border: 1px solid var(--cn-border, #cce4f5);
  background: #fff;
  color: var(--cn-text-secondary, #4a6a84);
  border-radius: 999px;
  padding: 4px 14px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
}
.ms-cat-btn:hover {
  border-color: #1b6ca8;
  color: #1b6ca8;
}
.ms-cat-btn.active {
  background: #1b6ca8;
  border-color: #1b6ca8;
  color: #fff;
}

.ms-search-bar {
  background: #ebf4fb;
  border-radius: 8px;
  padding: 14px;
  margin-bottom: 14px;
}

.ms-search-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.ms-input {
  flex: 1;
  min-width: 0;
}

.ms-mode-row {
  margin-top: 10px;
}

.ms-offline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 1px dashed var(--cn-border, #cce4f5);
  border-radius: 8px;
  margin-bottom: 20px;
  background: #fff;
}
.ms-offline-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
  color: var(--cn-text-secondary, #4a6a84);
}
.ms-offline-text strong {
  color: #1b6ca8;
  font-size: 14px;
}

.ms-welcome {
  text-align: center;
  padding: 40px 12px;
}
.ms-welcome-title {
  font-size: 22px;
  color: #1b6ca8;
  font-weight: 600;
}
.ms-welcome-sub {
  margin-top: 6px;
  color: var(--cn-text-muted, #94a3b8);
  font-size: 14px;
}
.ms-hint {
  margin-top: 28px;
  text-align: left;
  display: inline-block;
  background: #ebf4fb;
  padding: 14px 18px;
  border-radius: 8px;
  color: var(--cn-text-secondary, #4a6a84);
  font-size: 13px;
  line-height: 1.8;
}

.ms-loading,
.ms-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 48px 12px;
  color: var(--cn-text-secondary, #4a6a84);
}

.ms-total {
  margin-bottom: 12px;
  font-size: 15px;
  color: var(--cn-text-primary, #1a2a3a);
}
.ms-total em {
  color: #1b6ca8;
  font-style: normal;
  font-weight: 700;
  font-size: 18px;
}

.ms-card {
  background: #ebf4fb;
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 12px;
}
.ms-card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.ms-tag {
  border: none;
  background: #1b6ca8;
  color: #fff;
  border-radius: 4px;
  padding: 2px 10px;
  font-size: 12px;
  cursor: pointer;
}
.ms-tag:hover {
  opacity: 0.9;
}
.ms-card-title {
  font-weight: 600;
  color: #1a2a3a;
  margin-bottom: 8px;
}
.ms-card-up :deep(em),
.ms-card-down :deep(em) {
  background: #ffe58f;
  font-style: normal;
  padding: 0 1px;
}
.ms-card-up,
.ms-card-down {
  font-size: 14px;
  line-height: 1.7;
  color: #1a2a3a;
  margin-bottom: 6px;
}
.ms-card-source {
  margin-top: 8px;
  font-size: 12px;
  color: var(--cn-text-muted, #94a3b8);
}
.ms-card-source span {
  display: block;
}

.ms-pages {
  margin-top: 20px;
  text-align: center;
}

.ms-reading-title {
  color: #1b6ca8;
  font-weight: 600;
}
.ms-reading-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.ms-cells {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.ms-toc-item {
  cursor: pointer;
  padding: 8px 10px;
  background: #ebf4fb;
  border-radius: 6px;
  margin-bottom: 6px;
}
.ms-toc-item:hover {
  background: #1b6ca8;
  color: #fff;
}
.ms-only-zh,
.ms-col {
  background: #f5f9fc;
  padding: 12px;
  border-radius: 8px;
}
.ms-bilingual {
  display: flex;
  gap: 16px;
}
.ms-bilingual .ms-col {
  flex: 1;
  min-width: 0;
}
.ms-reading-body :deep(em) {
  background: #ffe58f;
  font-style: normal;
}
.ms-reading-body :deep(.ver),
.ms-reading-body :deep(.text) {
  text-align: justify;
  padding: 6px;
  background: #fff;
  border-radius: 4px;
  margin-bottom: 6px;
}
.ms-reading-body :deep(.bookname) {
  text-align: center;
  font-weight: bold;
  font-size: x-large;
  color: #0b6108;
}
.ms-reading-body :deep(.title) {
  color: #1b6ca8;
  font-weight: bold;
  font-size: large;
  text-align: center;
  margin-bottom: 1em;
}
.ms-reading-body :deep(.heading) {
  color: #1b6ca8;
  font-weight: bold;
  text-align: center;
}
.ms-reading-body :deep(.ot1) {
  font-weight: bold;
  font-size: large;
}

@media (max-width: 640px) {
  .ms-search-row {
    flex-wrap: wrap;
  }
  .ms-input {
    width: 100%;
    flex: auto;
  }
  .ms-offline {
    flex-direction: column;
    align-items: flex-start;
  }
  .ms-bilingual {
    flex-direction: column;
  }
}
</style>

<style>
.ms-reading-modal .ant-modal {
  max-width: 100%;
  top: 0;
  padding-bottom: 0;
  margin: 0;
}
.ms-reading-modal .ant-modal-content {
  min-height: 80vh;
}
.ms-reading-modal .ant-modal-body {
  max-height: calc(100vh - 110px);
  overflow-y: auto;
}
</style>

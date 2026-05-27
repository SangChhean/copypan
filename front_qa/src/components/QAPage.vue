<template>
  <div class="qa-root">
    <!-- 页头 -->
    <header class="qa-header">
      <div class="qa-header-inner">
        <div class="qa-logo">
          <span class="qa-logo-text">职事信息问答</span>
        </div>
        <div class="qa-header-right">
          <span
            v-if="dailyUsage.limit > 0"
            class="qa-daily-usage"
            :class="usageLevelClass"
          >{{ usageDisplayText }}</span>
          <button type="button" class="qa-new-chat-btn" @click="newConversation">+ 新对话</button>
          <a-dropdown placement="bottomRight">
            <a-avatar class="qa-user-avatar">{{ avatarText }}</a-avatar>
            <template #overlay>
              <a-menu>
                <a-menu-item disabled>{{ currentUsername || '未登录' }}</a-menu-item>
                <a-menu-divider />
                <a-menu-item @click="goAdmin">管理后台</a-menu-item>
                <a-menu-item class="qa-logout-item" @click="logout">退出登录</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
      </div>
    </header>

    <!-- 主体：对话区可滚动 -->
    <main class="qa-main" ref="historyRef">
      <div v-if="messages.length === 0" class="qa-welcome">
        <div class="qa-welcome-title">真理必叫你们得以自由</div>
        <div class="qa-welcome-sub">The truth shall set you free</div>
        <div class="qa-example-list">
          <div
            v-for="ex in examples"
            :key="ex"
            class="qa-example-chip"
            @click="fillExample(ex)"
          >{{ ex }}</div>
        </div>
      </div>

      <div v-else class="qa-chat">
        <div
          v-for="msg in messages"
          :key="msg.id"
          :ref="(el) => setMessageRef(msg.id, el)"
          class="qa-msg-row"
          :class="msg.role === 'user' ? 'qa-msg-row--user' : 'qa-msg-row--assistant'"
        >
          <div v-if="msg.role === 'user'" class="qa-bubble qa-bubble-user">
            {{ msg.content }}
          </div>

          <div v-else class="qa-bubble qa-bubble-assistant">
            <div v-if="msg.loading" class="qa-loading">
              <a-spin size="small" />
              <span class="qa-loading-text">{{ assistantLoadingText(msg) }}</span>
            </div>

            <div v-else-if="!msg.found" class="qa-not-found">
              <span class="qa-not-found-icon">🔍</span>
              以下内容未能在职事信息中找到相关依据。
            </div>

            <template v-else>
              <BibleMessage
                v-if="
                  msg.intent === 'bible' &&
                  (msg.verse || (msg.verses && msg.verses.length))
                "
                :verse="msg.verse"
                :verses="msg.verses"
                :query-type="msg.queryType || 'verse'"
                :lang="msg.currentLang || 'gb'"
                :generating="msg.bibleGenerating"
              />
              <div
                v-if="msg.hasVerseData && msg.streaming && !msg.answer"
                class="qa-loading qa-loading--after-verse"
              >
                <a-spin size="small" />
                <span class="qa-loading-text">{{ assistantLoadingText(msg) }}</span>
              </div>
              <div
                class="qa-answer-body"
                :class="{ 'qa-answer-fade': msg.currentLang !== 'zh' }"
                :key="msg.currentLang"
                v-html="renderAnswer(displayAnswer(msg))"
              ></div>

              <div v-if="displaySources(msg).length" class="qa-sources" :key="'src-' + msg.currentLang">
                <div class="qa-sources-title">
                  {{ msg.currentLang === 'en' ? 'References' : (msg.currentLang === 'zh_tw' ? '引用書目' : '引用书目') }}
                </div>
                <div class="qa-sources-list">
                  <div
                    v-for="(src, srcIdx) in displaySources(msg)"
                    :key="srcIdx + '-' + src"
                    class="qa-source-item"
                  >
                    <span class="qa-source-name">{{ src }}</span>
                  </div>
                </div>
              </div>

              <div class="qa-meta" v-if="!msg.streaming">
                <span v-if="msg.cache_hit" class="qa-meta-badge qa-meta-cache">缓存</span>
                <span class="qa-meta-time">{{ msg.elapsed }}s</span>
                <span class="qa-meta-cost">${{ Number(msg.cost || 0).toFixed(4) }}</span>
              </div>

              <!-- 操作区：两行布局 -->
              <div v-if="!msg.streaming" class="qa-actions">
                <!-- 第一行：复制 + 反馈 -->
                <div class="qa-actions-row1">
                  <button
                    class="qa-feedback-btn qa-copy-btn"
                    :disabled="msg.copied"
                    @click="copyAnswer(msg)"
                  >
                    <svg
                      v-if="msg.copied"
                      xmlns="http://www.w3.org/2000/svg"
                      width="15"
                      height="15"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    >
                      <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                    <span v-if="msg.copied">copied</span>
                    <svg
                      v-if="!msg.copied"
                      xmlns="http://www.w3.org/2000/svg"
                      width="15"
                      height="15"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    >
                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                    </svg>
                    <span v-if="!msg.copied">copy</span>
                  </button>
                  <button
                    v-if="msg.found"
                    class="qa-feedback-btn"
                    :class="{
                      'is-selected': msg.feedback === 1,
                      'is-muted': msg.feedback === -1,
                    }"
                    :disabled="msg.feedback !== null || msg.feedbackSubmitting"
                    @click="submitFeedback(msg, 1)"
                  >
                    👍
                  </button>
                  <button
                    v-if="msg.found"
                    class="qa-feedback-btn"
                    :class="{
                      'is-selected': msg.feedback === -1,
                      'is-muted': msg.feedback === 1,
                    }"
                    :disabled="msg.feedback !== null || msg.feedbackSubmitting"
                    @click="submitFeedback(msg, -1)"
                  >
                    👎
                  </button>
                </div>
                <!-- 第二行：语言切换 + 朗读（同排、视觉分离） -->
                <div v-if="msg.found" class="qa-action-row2">
                  <div class="qa-lang-toggle">
                    <button
                      v-for="opt in langOptions"
                      :key="opt.value"
                      type="button"
                      class="qa-lang-toggle-btn"
                      :class="{ 'is-active': msg.currentLang === opt.value }"
                      :disabled="msg.translating"
                      @click="switchLang(msg, opt.value)"
                    >
                      <a-spin v-if="msg.translating && msg.currentLang !== opt.value" size="small" />
                      <span v-else>{{ opt.label }}</span>
                    </button>
                  </div>
                  <button
                    type="button"
                    class="qa-tts-btn"
                    :disabled="ttsState(msg) === 'loading' && ttsMsgEngine.get(msg.id) === 'polly'"
                    @click="toggleTTS(msg, 'polly')"
                    :title="ttsMsgEngine.get(msg.id) === 'polly' && ttsState(msg) === 'playing' ? '暂停' : 'Polly 朗读'"
                  >
                    <span v-if="ttsMsgEngine.get(msg.id) === 'polly' && ttsState(msg) === 'loading'">…</span>
                    <span v-else-if="ttsMsgEngine.get(msg.id) === 'polly' && ttsState(msg) === 'playing'">{{
                      ttsProgress(msg) ? `⏸ ${ttsProgress(msg)}` : '⏸'
                    }}</span>
                    <span v-else-if="ttsMsgEngine.get(msg.id) === 'polly' && ttsState(msg) === 'paused'">{{
                      ttsProgress(msg) ? `▶ ${ttsProgress(msg)}` : '▶'
                    }}</span>
                    <span v-else>🔊 Polly</span>
                  </button>
                  <button
                    v-if="SHOW_GOOGLE_TTS"
                    type="button"
                    class="qa-tts-btn qa-tts-btn--google"
                    :disabled="ttsState(msg) === 'loading' && ttsMsgEngine.get(msg.id) === 'google'"
                    @click="toggleTTS(msg, 'google')"
                    :title="ttsMsgEngine.get(msg.id) === 'google' && ttsState(msg) === 'playing' ? '暂停' : 'Google 朗读'"
                  >
                    <span v-if="ttsMsgEngine.get(msg.id) === 'google' && ttsState(msg) === 'loading'">…</span>
                    <span v-else-if="ttsMsgEngine.get(msg.id) === 'google' && ttsState(msg) === 'playing'">{{
                      ttsProgress(msg) ? `⏸ ${ttsProgress(msg)}` : '⏸'
                    }}</span>
                    <span v-else-if="ttsMsgEngine.get(msg.id) === 'google' && ttsState(msg) === 'paused'">{{
                      ttsProgress(msg) ? `▶ ${ttsProgress(msg)}` : '▶'
                    }}</span>
                    <span v-else>🔊 Google</span>
                  </button>
                  <button
                    v-if="SHOW_MINIMAX_TTS"
                    type="button"
                    class="qa-tts-btn qa-tts-btn--minimax"
                    :disabled="ttsState(msg) === 'loading' && ttsMsgEngine.get(msg.id) === 'minimax'"
                    @click="toggleTTS(msg, 'minimax')"
                    :title="ttsMsgEngine.get(msg.id) === 'minimax' && ttsState(msg) === 'playing' ? '暂停' : 'MiniMax 朗读'"
                  >
                    <span v-if="ttsMsgEngine.get(msg.id) === 'minimax' && ttsState(msg) === 'loading'">…</span>
                    <span v-else-if="ttsMsgEngine.get(msg.id) === 'minimax' && ttsState(msg) === 'playing'">{{
                      ttsProgress(msg) ? `⏸ ${ttsProgress(msg)}` : '⏸'
                    }}</span>
                    <span v-else-if="ttsMsgEngine.get(msg.id) === 'minimax' && ttsState(msg) === 'paused'">{{
                      ttsProgress(msg) ? `▶ ${ttsProgress(msg)}` : '▶'
                    }}</span>
                    <span v-else>🔊 MiniMax</span>
                  </button>
                  <button
                    v-if="SHOW_ELEVENLABS_TTS"
                    type="button"
                    class="qa-tts-btn qa-tts-btn--elevenlabs"
                    :disabled="ttsState(msg) === 'loading' && ttsMsgEngine.get(msg.id) === 'elevenlabs'"
                    @click="toggleTTS(msg, 'elevenlabs')"
                    :title="ttsMsgEngine.get(msg.id) === 'elevenlabs' && ttsState(msg) === 'playing' ? '暂停' : 'ElevenLabs 朗读'"
                  >
                    <span v-if="ttsMsgEngine.get(msg.id) === 'elevenlabs' && ttsState(msg) === 'loading'">…</span>
                    <span v-else-if="ttsMsgEngine.get(msg.id) === 'elevenlabs' && ttsState(msg) === 'playing'">{{
                      ttsProgress(msg) ? `⏸ ${ttsProgress(msg)}` : '⏸'
                    }}</span>
                    <span v-else-if="ttsMsgEngine.get(msg.id) === 'elevenlabs' && ttsState(msg) === 'paused'">{{
                      ttsProgress(msg) ? `▶ ${ttsProgress(msg)}` : '▶'
                    }}</span>
                    <span v-else>🔊 ElevenLabs</span>
                  </button>
                </div>
              </div>
            </template>

            <div v-if="!msg.loading" class="qa-disclaimer">
              <span v-if="msg.currentLang === 'en'">
                The above answer is generated by AI based on ministry messages. Please verify against the original text.
              </span>
              <span v-else-if="msg.currentLang === 'zh_tw'">
                以上答案由 AI 根據職事信息歸納生成，建議對照原文查證。
              </span>
              <span v-else>
                以上答案由 AI 根据职事信息归纳生成，建议对照原文查证。
              </span>
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- 输入区 -->
    <footer class="qa-footer">
      <div class="qa-input-wrap">
        <button
          class="qa-mic-btn"
          :class="{ active: voiceMode }"
          :disabled="loading || audioState === 'processing'"
          @click="clickMic"
        >
          <svg
            v-if="!voiceMode"
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M12 1a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
            <path d="M19 10v1a7 7 0 0 1-14 0v-1"></path>
            <line x1="12" y1="19" x2="12" y2="23"></line>
            <line x1="8" y1="23" x2="16" y2="23"></line>
          </svg>
          <svg
            v-else
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
        <a-textarea
          v-if="!voiceMode"
          :key="textareaKey"
          ref="textareaRef"
          v-model:value="question"
          :placeholder="'请输入问题'"
          :auto-size="{ minRows: 1, maxRows: 5 }"
          :maxlength="500"
          :disabled="loading"
          class="qa-textarea"
          @keydown.enter.exact.prevent="submit"
        />
        <div v-else class="qa-voice-area">
          <div v-if="audioState === 'recording'" class="qa-recording-panel">
            <div class="qa-recording-top">
              <span class="qa-recording-dot"></span>
              <span class="qa-recording-label">录音中...</span>
              <span class="qa-recording-timer">{{ recordingTimeStr }}</span>
            </div>
            <div class="qa-recording-tip">请保持语速平缓，发音正确</div>
            <div class="qa-recording-wave">
              <span
                v-for="(h, i) in waveHeights"
                :key="i"
                class="qa-wave-bar"
                :style="{ height: h + 'px' }"
              ></span>
            </div>
          </div>
          <button
            class="qa-press-btn"
            :class="{
              pressing: pressing,
              processing: audioState === 'processing'
            }"
            :disabled="audioState === 'processing'"
            @mousedown.prevent="startRecording"
            @mouseup="stopRecording"
            @mouseleave="stopRecording"
            @touchstart.prevent="startRecording"
            @touchend.prevent="stopRecording"
            @touchcancel.prevent="stopRecording"
          >
            <span v-if="audioState === 'processing'">识别中...</span>
            <span v-else-if="pressing">松开 结束</span>
            <span v-else>按住 说话</span>
          </button>
        </div>
        <a-button
          type="primary"
          :loading="loading"
          :disabled="!question.trim()"
          class="qa-submit-btn"
          @click="submit"
        >问</a-button>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { ref, nextTick, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { marked } from 'marked'
import { message } from 'ant-design-vue'
import BibleMessage from './BibleMessage.vue'

const POLLY_API = 'https://x2vi7ecfqk3q7qqfpruvveqkj40vbnxc.lambda-url.us-east-1.on.aws'
const SHOW_GOOGLE_TTS = true
const SHOW_MINIMAX_TTS = true
const SHOW_ELEVENLABS_TTS = true

const BIBLE_BOOK_MAP = {
  '创': '创世记',
  '出': '出埃及记',
  '利': '利未记',
  '民': '民数记',
  '申': '申命记',
  '书': '约书亚记',
  '士': '士师记',
  '得': '路得记',
  '撒上': '撒母耳记上',
  '撒下': '撒母耳记下',
  '王上': '列王纪上',
  '王下': '列王纪下',
  '代上': '历代志上',
  '代下': '历代志下',
  '拉': '以斯拉记',
  '尼': '尼希米记',
  '斯': '以斯帖记',
  '伯': '约伯记',
  '诗': '诗篇',
  '箴': '箴言',
  '传': '传道书',
  '歌': '雅歌',
  '赛': '以赛亚书',
  '耶': '耶利米书',
  '哀': '耶利米哀歌',
  '结': '以西结书',
  '但': '但以理书',
  '何': '何西阿书',
  '珥': '约珥书',
  '摩': '阿摩司书',
  '俄': '俄巴底亚书',
  '拿': '约拿书',
  '弥': '弥迦书',
  '鸿': '那鸿书',
  '哈': '哈巴谷书',
  '番': '西番雅书',
  '该': '哈该书',
  '亚': '撒迦利亚书',
  '玛': '玛拉基书',
  '太': '马太福音',
  '可': '马可福音',
  '路': '路加福音',
  '约': '约翰福音',
  '徒': '使徒行传',
  '罗': '罗马书',
  '林前': '哥林多前书',
  '林后': '哥林多后书',
  '加': '加拉太书',
  '弗': '以弗所书',
  '腓': '腓立比书',
  '西': '歌罗西书',
  '帖前': '帖撒罗尼迦前书',
  '帖后': '帖撒罗尼迦后书',
  '提前': '提摩太前书',
  '提后': '提摩太后书',
  '多': '提多书',
  '门': '腓利门书',
  '来': '希伯来书',
  '雅': '雅各书',
  '彼前': '彼得前书',
  '彼后': '彼得后书',
  '约壹': '约翰一书',
  '约贰': '约翰二书',
  '约叁': '约翰三书',
  '犹': '犹大书',
  '启': '启示录',
}

const SIMPLIFIED_TO_STANDARD = {
  '二一': '二十一',
  '二二': '二十二',
  '二三': '二十三',
  '二四': '二十四',
  '二五': '二十五',
  '二六': '二十六',
  '二七': '二十七',
  '二八': '二十八',
  '二九': '二十九',
  '三一': '三十一',
  '三二': '三十二',
  '三三': '三十三',
  '三四': '三十四',
  '三五': '三十五',
  '三六': '三十六',
  '三七': '三十七',
  '三八': '三十八',
  '三九': '三十九',
  '四一': '四十一',
  '四二': '四十二',
  '四三': '四十三',
  '四四': '四十四',
  '四五': '四十五',
  '四六': '四十六',
  '四七': '四十七',
  '四八': '四十八',
  '四九': '四十九',
  '五一': '五十一',
  '五二': '五十二',
  '五三': '五十三',
  '五四': '五十四',
  '五五': '五十五',
  '五六': '五十六',
  '五七': '五十七',
  '五八': '五十八',
  '五九': '五十九',
  '六一': '六十一',
  '六二': '六十二',
  '六三': '六十三',
  '六四': '六十四',
  '六五': '六十五',
  '六六': '六十六',
  '六七': '六十七',
  '六八': '六十八',
  '六九': '六十九',
  '七一': '七十一',
  '七二': '七十二',
  '七三': '七十三',
  '七四': '七十四',
  '七五': '七十五',
  '七六': '七十六',
  '七七': '七十七',
  '七八': '七十八',
  '七九': '七十九',
  '八一': '八十一',
  '八二': '八十二',
  '八三': '八十三',
  '八四': '八十四',
  '八五': '八十五',
  '八六': '八十六',
  '八七': '八十七',
  '八八': '八十八',
  '八九': '八十九',
  '九一': '九十一',
  '九二': '九十二',
  '九三': '九十三',
  '九四': '九十四',
  '九五': '九十五',
  '九六': '九十六',
  '九七': '九十七',
  '九八': '九十八',
  '九九': '九十九',
}

let pollyReplacementMap = null
async function loadPollyReplacementMap() {
  if (pollyReplacementMap !== null) return pollyReplacementMap
  try {
    const res = await fetch('/polly_replacement_map.json')
    pollyReplacementMap = res.ok ? await res.json() : {}
  } catch {
    pollyReplacementMap = {}
  }
  return pollyReplacementMap
}

function chineseToStandardReading(text) {
  if (SIMPLIFIED_TO_STANDARD[text]) return SIMPLIFIED_TO_STANDARD[text]
  if (/^\d+$/.test(text)) return String(Number(text))
  return text
}

function expandBibleVerses(text) {
  text = text.replace(/（[^）]*）|\([^)]*\)/g, '')
  const bookPattern = Object.keys(BIBLE_BOOK_MAP)
    .sort((a, b) => b.length - a.length)
    .join('|')
  const pattern = new RegExp(
    `(${bookPattern})` +
      `(?:([一二三四五六七八九十〇零]+)(\\d[\\d~\\-～,，；;]*)` +
      '|(\\d+)章(\\d+)(?:节)?)',
    'g'
  )
  return text.replace(pattern, (match, book, chCh, verse1, arCh, verse2) => {
    const fullBook = BIBLE_BOOK_MAP[book] || book
    if (chCh && verse1) {
      const std = chineseToStandardReading(chCh)
      const verseClean = verse1.replace(/[~\-～]/g, '至')
      return `${fullBook}${std}章${verseClean}节`
    }
    if (arCh && verse2) return `${fullBook}${arCh}章${verse2}节`
    return match
  })
}

async function prepareTextForTTS(rawText, lang = 'zh') {
  let text = rawText
  // 1. 去掉参考书目及其后所有内容（简体、繁体、英文）
  text = text.replace(/(引用书目|引用書目|参考书目|參考書目|\[References\]|References)[\s\S]*$/m, '')
  // 2. 去掉 HTML 标签
  text = text.replace(/<[^>]+>/g, '')
  // 3. 去掉 ⟪...⟫ 原文引用块
  text = text.replace(/\u27ea[^\u27eb]*\u27eb/g, '')
  // 4. 去掉 Markdown 标题和分割线
  text = text.replace(/^#{1,6}\s+/gm, '')
  text = text.replace(/^[-*_]{3,}\s*$/gm, '')
  // 5. 去掉粗体、斜体
  text = text.replace(/\*\*(.*?)\*\*/g, '$1')
  text = text.replace(/\*(.*?)\*/g, '$1')
  // 6. 去掉引用编号上标（句末数字如 「...」1 或 。2）
  text = text.replace(/([。！？」』])\d+/g, '$1')
  text = text.replace(/^\d+\s*/gm, '')
  // 7. 去掉行首孤立数字（如段落开头的 "1\n"）
  text = text.replace(/^\d+$/gm, '')
  // 8. 展开经节引用
  text = expandBibleVerses(text)
  // 9. 全角空格转句号
  text = text.replace(/\u3000/g, '。')
  // 10. 应用 Polly 替换规则
  const replacementMap = await loadPollyReplacementMap()
  const sortedKeys = Object.keys(replacementMap).sort((a, b) => b.length - a.length)
  for (const key of sortedKeys) {
    text = text.replaceAll(key, replacementMap[key])
  }
  // 中文停顿处理（仅简体和繁体）
  if (lang !== 'en') {
    text = text.replace(/——/g, '，')
    text = text.replace(/：/g, '，')
    text = text.replace(/；/g, '，')
  }
  // 11. 清理多余空行
  text = text.replace(/\n{3,}/g, '\n\n').trim()
  return text
}

function chunkTextForTTS(text, maxLen = 80) {
  if (text.length <= maxLen) return [text]
  const chunks = []
  const paragraphs = text.split(/\n\n+/).filter((p) => p.trim())
  for (const para of paragraphs) {
    if (para.length <= maxLen) {
      chunks.push(para.trim())
      continue
    }
    const sentences = para.match(/[^。！？；\n]+[。！？；\n]*/g) || [para]
    let cur = ''
    for (const s of sentences) {
      const t = s.trim()
      if (!t) continue
      if (cur.length + t.length <= maxLen) {
        cur += t
      } else {
        if (cur) chunks.push(cur.trim())
        if (t.length > maxLen) {
          // 按空格截断，避免英文单词被切断
          const words = t.split(' ')
          let wordBuf = ''
          for (const word of words) {
            if ((wordBuf + ' ' + word).trim().length <= maxLen) {
              wordBuf = wordBuf ? wordBuf + ' ' + word : word
            } else {
              if (wordBuf) chunks.push(wordBuf.trim())
              wordBuf = word
            }
          }
          if (wordBuf) chunks.push(wordBuf.trim())
          cur = ''
        } else {
          cur = t
        }
      }
    }
    if (cur) chunks.push(cur.trim())
  }
  return chunks.filter((c) => c.length > 0)
}

/** 复制到剪贴板：同步清洗（不经 Polly JSON） */
function stripAnswerPlain(text) {
  if (!text) return ''
  return text
    .replace(/\u27ea[^\u27eb]*\u27eb/g, '')
    .replace(/<sup[^>]*>.*?<\/sup>/gi, '')
    .replace(/\[\d+\]/g, '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*(.*?)\*/g, '$1')
    .replace(/#{1,6}\s/g, '')
    .replace(/`{1,3}[^`]*`{1,3}/g, '')
    .replace(/\n{2,}/g, '\n')
    .replace(/参考书目[\s\S]*$/m, '')
    .replace(/References[\s\S]*$/mi, '')
    .replace(/書目[\s\S]*$/m, '')
    .replace(/[\u27ea\u27eb\u29f8]/g, '')
    .replace(/【[^】]*】/g, '')
    .replace(/\([a-zA-Z0-9\s,.-]+\)/g, '')
    .trim()
}

const router = useRouter()
const question = ref('')
const textareaKey = ref(0)
const loading = ref(false)

function assistantLoadingText(msg) {
  return msg.hasVerseData ? '正在查找相关职事信息…' : '正在检索职事信息…'
}
const textareaRef = ref(null)
const currentUsername = ref(localStorage.getItem('qa_username') || '')
/** 发往接口的最近 3 轮 { question, answer } */
const history = ref([])
/** 界面气泡：user / assistant，assistant 含 loading 与展示字段 */
const messages = ref([])
const historyRef = ref(null)

const dailyUsage = ref({ used: 0, limit: 30 })

const headerLang = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    const m = messages.value[i]
    if (m.role === 'assistant' && m.currentLang) return m.currentLang
  }
  return 'zh'
})

const usageDisplayText = computed(() => {
  const { used, limit } = dailyUsage.value
  if (headerLang.value === 'en') return `Today ${used}/${limit}`
  return `今日 ${used}/${limit}`
})

const usageLevelClass = computed(() => {
  const { used, limit } = dailyUsage.value
  if (limit > 0 && used >= limit) return 'qa-daily-usage--danger'
  if (limit > 0 && used >= limit * 0.8) return 'qa-daily-usage--warn'
  return ''
})

async function fetchDailyUsage() {
  const token = localStorage.getItem('qa_token') || ''
  if (!token) return
  try {
    const res = await fetch('/api/qa/auth/usage', {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) return
    const data = await res.json()
    dailyUsage.value = {
      used: Number(data.used) || 0,
      limit: Number(data.limit) || 30,
    }
  } catch {
    /* ignore */
  }
}

function incrementDailyUsageLocal() {
  const { used, limit } = dailyUsage.value
  if (limit <= 0) return
  dailyUsage.value = { used: Math.min(used + 1, limit), limit }
}

onMounted(() => {
  fetchDailyUsage()
})

let nextMessageId = 0
const messageRefMap = new Map()

const examples = [
  '神的经纶的中心是什么？',
  '生命与性情有何关系？',
  '召会是基督的身体，如何理解？',
  '圣灵的膏抹是什么意思？',
  '创世记生命读经第三十篇的重点是什么？',
]

const langOptions = [
  { label: '简体', value: 'zh' },
  { label: '繁體', value: 'zh_tw' },
  { label: 'English', value: 'en' },
]

function fillExample(ex) {
  question.value = ex
}

const avatarText = (currentUsername.value || '?').slice(0, 1).toUpperCase()

function goAdmin() {
  router.push('/admin')
}

function logout() {
  localStorage.removeItem('qa_token')
  localStorage.removeItem('qa_username')
  router.replace('/login')
}

function newConversation() {
  window.location.reload()
}

function renderAnswer(text) {
  if (!text) return ''
  let body = text
  if (body.includes('【引用书目】')) {
    body = body.split('【引用书目】')[0]
  }
  if (body.includes('[References]')) {
    body = body.split('[References]')[0]
  }
  let html = marked.parse(body.trim())
  // 匹配引用编号：右引号（中英文，含直引号与弯引号 \u201d\u2019）后可跟空白/逗号/句号，再跟 1～2 位数字
  html = html.replace(
    /([」"'"\u201d\u2019\u0022\u0027])([\s.,]*?)(\d{1,2})(?=\s|<|$)/g,
    (match, quote, punct, num) => {
      return `${quote}${punct}<sup class="qa-cite-num">${num}</sup>`
    }
  )
  // 句末标点后紧跟数字（无引号）；(?<!\d) 降低 3.14 类小数误匹配
  html = html.replace(/(?<!\d)([.!?])(\d{1,2})(?=\s|<|$)/g, (match, punct, num) => {
    return `${punct}<sup class="qa-cite-num">${num}</sup>`
  })
  return html
}

/** 当前气泡应展示的 answer（按 currentLang 选） */
function displayAnswer(msg) {
  if (!msg) return ''
  if (msg.currentLang === 'zh') return msg.answer || ''
  const tr = msg.translatedAnswers?.[msg.currentLang]
  return tr ? tr.answer : (msg.answer || '')
}

/** 当前气泡应展示的 sources */
function displaySources(msg) {
  if (!msg) return []
  if (msg.currentLang === 'zh') return msg.sources || []
  const tr = msg.translatedAnswers?.[msg.currentLang]
  return tr ? (tr.sources || []) : (msg.sources || [])
}

// TTS（Polly Lambda / Google）
const ttsMsgId = ref(null)
const ttsMsgEngine = ref(new Map()) // msgId -> 'polly' | 'google' | 'minimax' | 'elevenlabs'
const ttsPlaying = ref(false)
const ttsPaused = ref(false)
const ttsAudioCtx = ref(null)
const ttsActiveRequests = ref(new Set())
const ttsDestroyed = ref(false)
const ttsProgressPct = ref(0)

function ttsProgress(msg) {
  if (ttsMsgId.value !== msg.id) return ''
  if (ttsProgressPct.value <= 0) return ''
  return `${ttsProgressPct.value}%`
}

function ttsState(msg) {
  if (ttsMsgId.value !== msg.id) return 'idle'
  if (ttsPlaying.value && !ttsPaused.value) return 'playing'
  if (ttsPaused.value) return 'paused'
  return 'loading'
}

function stopTTS() {
  ttsDestroyed.value = true
  ttsActiveRequests.value.forEach((ctrl) => ctrl.abort())
  ttsActiveRequests.value.clear()
  if (ttsAudioCtx.value) {
    ttsAudioCtx.value.close()
    ttsAudioCtx.value = null
  }
  ttsPlaying.value = false
  ttsPaused.value = false
  ttsMsgId.value = null
  ttsProgressPct.value = 0
}

async function toggleTTS(msg, engine = 'google') {
  const currentEngine = ttsMsgEngine.value.get(msg.id)
  if (ttsMsgId.value === msg.id && currentEngine === engine) {
    if (ttsAudioCtx.value) {
      if (ttsPaused.value) {
        ttsAudioCtx.value.resume()
        ttsPaused.value = false
      } else {
        ttsAudioCtx.value.suspend()
        ttsPaused.value = true
      }
      return
    }
  }

  stopTTS()
  ttsDestroyed.value = false
  const nextEngine = new Map(ttsMsgEngine.value)
  nextEngine.set(msg.id, engine)
  ttsMsgEngine.value = nextEngine
  ttsMsgId.value = msg.id
  const currentMsgId = msg.id

  const lang = msg.currentLang || 'zh'
  let rawText = ''
  if (lang === 'en') rawText = msg.translatedAnswers?.en?.answer || msg.answer || ''
  else rawText = msg.answer || '' // 简体和繁体都读简体原文
  console.log('[TTS] msg.id:', msg.id, 'currentLang:', msg.currentLang, 'answer前20:', (msg.answer || '').substring(0, 20), 'zh_tw:', msg.translatedAnswers?.zh_tw?.answer?.substring(0, 20))

  const plainText = await prepareTextForTTS(rawText, lang)
  if (!plainText || ttsMsgId.value !== currentMsgId) {
    if (ttsMsgId.value === currentMsgId) ttsMsgId.value = null
    return
  }

  const chunks = engine === 'minimax'
    ? [plainText]
    : engine === 'elevenlabs'
      ? chunkTextForTTS(plainText, lang === 'en' ? 400 : 180)
      : engine === 'google'
        ? (() => {
            const minLen = lang === 'en' ? 200 : 100
            const maxLen = lang === 'en' ? 800 : 300
            const lines = plainText.split(/\n+/).map(s => s.trim()).filter(s => s.length > 0)
            const merged = []
            let current = ''
            for (const line of lines) {
              if (current.length === 0) {
                current = line
              } else if (current.length + line.length < maxLen) {
                current += '。' + line
              } else {
                if (current.length >= minLen) {
                  merged.push(current)
                  current = line
                } else {
                  current += '。' + line
                }
              }
            }
            if (current) merged.push(current)
            return merged
          })()
        : chunkTextForTTS(plainText, lang === 'en' ? 400 : 80)
  if (!chunks.length) {
    if (ttsMsgId.value === currentMsgId) ttsMsgId.value = null
    return
  }

  const ctx = new AudioContext()
  ttsAudioCtx.value = ctx
  ttsPlaying.value = true

  const audioQueue = new Array(chunks.length).fill(null)
  let playIndex = 0
  let fetchIndex = 0

  async function fetchChunkOnce(i) {
    if (ttsDestroyed.value) return
    const ctrl = new AbortController()
    ttsActiveRequests.value.add(ctrl)
    try {
      let res
      if (engine === 'google') {
        res = await fetch('/api/qa/tts', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${localStorage.getItem('qa_token') || ''}`,
          },
          body: JSON.stringify({
            text: chunks[i],
            lang: lang === 'zh_tw' ? 'zh_tw' : lang === 'en' ? 'en' : 'zh',
          }),
          signal: ctrl.signal,
        })
      } else if (engine === 'minimax') {
        res = await fetch('/api/qa/tts/minimax', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${localStorage.getItem('qa_token') || ''}`,
          },
          body: JSON.stringify({
            text: chunks[i],
            lang: lang === 'zh_tw' ? 'zh_tw' : lang === 'en' ? 'en' : 'zh',
          }),
          signal: ctrl.signal,
        })
      } else if (engine === 'elevenlabs') {
        res = await fetch('/api/qa/tts/elevenlabs', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${localStorage.getItem('qa_token') || ''}`,
          },
          body: JSON.stringify({
            text: chunks[i],
            lang: lang === 'zh_tw' ? 'zh_tw' : lang === 'en' ? 'en' : 'zh',
          }),
          signal: ctrl.signal,
        })
      } else {
        const voice = lang === 'en' ? 'Joanna' : 'Zhiyu'
        const params = new URLSearchParams({ text: chunks[i], voice })
        res = await fetch(`${POLLY_API}/?${params}`, { signal: ctrl.signal })
      }
      if (!res.ok || ttsDestroyed.value) {
        if (engine === 'elevenlabs') {
          message.warning('ElevenLabs 朗读失败')
        }
        return
      }
      const buf = await res.arrayBuffer()
      audioQueue[i] = await ctx.decodeAudioData(buf)
    } catch {
      // ignore abort
    } finally {
      ttsActiveRequests.value.delete(ctrl)
    }
  }

  function tryPlay() {
    if (ttsDestroyed.value) return
    if (playIndex >= chunks.length) {
      ttsPlaying.value = false
      ttsMsgId.value = null
      return
    }
    if (!audioQueue[playIndex]) {
      // 当前段还没准备好，100ms 后重试
      setTimeout(tryPlay, 100)
      return
    }
    const source = ctx.createBufferSource()
    source.buffer = audioQueue[playIndex]
    source.connect(ctx.destination)
    const currentPlay = playIndex
    source.onended = () => {
      if (ttsDestroyed.value) return
      playIndex++
      // 播放完当前段，预加载下下段
      const nextFetch = currentPlay + 2
      if (nextFetch < chunks.length && !audioQueue[nextFetch]) {
        fetchChunkOnce(nextFetch)
      }
      tryPlay()
    }
    source.start()
  }

  // 启动：先加载第0段和第1段
  fetchChunkOnce(0).then(() => {
    tryPlay()
    if (chunks.length > 1) fetchChunkOnce(1)
  })
}

/** 答案下方语言切换。zh / 已缓存：直接切；未缓存：调用 /api/qa/translate（暂未实现，501 仅 console）。 */
async function switchLang(msg, lang) {
  if (!msg || msg.currentLang === lang) return
  stopTTS()
  if (lang === 'zh') {
    msg.currentLang = 'zh'
    return
  }
  if (msg.translatedAnswers?.[lang]) {
    msg.currentLang = lang
    return
  }
  msg.translating = true
  try {
    const token = localStorage.getItem('qa_token') || ''
    const res = await fetch('/api/qa/translate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        text: msg.answer || '',
        sources: msg.sources || [],
        target_lang: lang,
        question: msg.question || '',
        cache_key: msg.cache_key || '',
      }),
    })
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`)
    }
    const data = await res.json()
    msg.translatedAnswers[lang] = {
      answer: data.answer || '',
      sources: data.sources || [],
    }
    msg.currentLang = lang
  } catch (e) {
    console.error('translate fallback failed', e)
    message.warning('翻译失败，请稍后重试')
  } finally {
    msg.translating = false
  }
}

// 打字机队列
const typewriterQueue = ref([])
let typewriterTimer = null
const audioState = ref('idle') // 'idle' | 'recording' | 'processing'
const voiceMode = ref(false) // 是否处于语音模式
const pressing = ref(false) // 是否正在长按「按住 说话」
let mediaRecorder = null
let audioChunks = []
let audioStopTimer = null
const recordingSeconds = ref(0)
const waveHeights = ref(Array(12).fill(3))
let recordingTimer = null
let analyserNode = null
let audioContext = null
let waveAnimFrame = null

const recordingTimeStr = computed(() => {
  const m = String(Math.floor(recordingSeconds.value / 60)).padStart(2, '0')
  const s = String(recordingSeconds.value % 60).padStart(2, '0')
  return `${m}:${s}`
})

function startTypewriter(targetMsg) {
  if (typewriterTimer) return
  typewriterTimer = setInterval(() => {
    if (typewriterQueue.value.length === 0) return
    const char = typewriterQueue.value.shift()
    const idx = messages.value.findIndex((m) => m.id === targetMsg.id)
    if (idx !== -1) {
      messages.value[idx].answer += char
    }
  }, 20) // 每 20ms 一个字符
}

function stopTypewriter() {
  if (typewriterTimer) {
    clearInterval(typewriterTimer)
    typewriterTimer = null
  }
  typewriterQueue.value = []
}

async function uploadAudio() {
  audioState.value = 'processing'
  try {
    const token = localStorage.getItem('qa_token') || ''
    if (!token) throw new Error('no token')
    const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' })
    const formData = new FormData()
    formData.append('file', blob, 'recording.webm')
    const res = await fetch('/api/qa/asr', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
      },
      body: formData,
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    const text = (data?.text || '')
    question.value = ''
    voiceMode.value = false
    pressing.value = false
    await nextTick()
    for (let i = 0; i < text.length; i++) {
      await new Promise((r) => setTimeout(r, 30))
      question.value += text[i]
    }
    await nextTick()
    if (textareaRef.value?.focus) {
      textareaRef.value.focus()
    } else if (textareaRef.value?.resizableTextArea?.textArea?.focus) {
      textareaRef.value.resizableTextArea.textArea.focus()
    }
  } catch (e) {
    message.error('语音识别失败，请重试')
  } finally {
    audioState.value = 'idle'
    audioChunks = []
  }
}

async function clickMic() {
  if (!voiceMode.value) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      stream.getTracks().forEach((t) => t.stop())
      voiceMode.value = true
    } catch (err) {
      const name = err?.name || ''
      if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
        message.warning('未检测到麦克风，请连接麦克风后重试')
      } else if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
        message.warning('请允许麦克风权限后重试')
      } else {
        message.warning('麦克风启动失败，请重试')
      }
    }
  } else {
    voiceMode.value = false
    pressing.value = false
    if (audioState.value === 'recording') stopRecording()
  }
}

async function startRecording() {
  if (loading.value || audioState.value !== 'idle') return
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
      },
    })
    audioChunks = []
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : 'audio/webm'
    mediaRecorder = new MediaRecorder(stream, {
      mimeType,
      audioBitsPerSecond: 128000,
    })
    mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        audioChunks.push(event.data)
      }
    }
    mediaRecorder.onstop = async () => {
      if (audioStopTimer) {
        clearTimeout(audioStopTimer)
        audioStopTimer = null
      }
      stream.getTracks().forEach((track) => track.stop())
      await uploadAudio()
    }
    mediaRecorder.start()
    audioState.value = 'recording'
    recordingSeconds.value = 0
    recordingTimer = setInterval(() => {
      recordingSeconds.value += 1
    }, 1000)
    audioContext = new AudioContext()
    const source = audioContext.createMediaStreamSource(stream)
    analyserNode = audioContext.createAnalyser()
    analyserNode.fftSize = 64
    source.connect(analyserNode)
    const dataArray = new Uint8Array(analyserNode.frequencyBinCount)
    const updateWave = () => {
      if (audioState.value !== 'recording') return
      analyserNode.getByteFrequencyData(dataArray)
      waveHeights.value = Array.from({ length: 12 }, (_, i) => {
        const idx = Math.floor((i * dataArray.length) / 12)
        const val = dataArray[idx] || 0
        return Math.max(3, Math.round((val / 255) * 32))
      })
      waveAnimFrame = requestAnimationFrame(updateWave)
    }
    updateWave()
    audioStopTimer = setTimeout(() => {
      if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop()
      }
    }, 60000)
    pressing.value = true
  } catch (e) {
    pressing.value = false
    message.warning('请允许麦克风权限后重试')
  }
}

function stopRecording() {
  if (audioState.value !== 'recording') return
  pressing.value = false
  if (audioStopTimer) {
    clearTimeout(audioStopTimer)
    audioStopTimer = null
  }
  if (recordingTimer) {
    clearInterval(recordingTimer)
    recordingTimer = null
  }
  recordingSeconds.value = 0
  waveHeights.value = Array(12).fill(3)
  if (waveAnimFrame) {
    cancelAnimationFrame(waveAnimFrame)
    waveAnimFrame = null
  }
  analyserNode = null
  if (audioContext) {
    audioContext.close()
    audioContext = null
  }
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop()
  }
}

async function submit() {
  const q = question.value.trim()
  if (!q || loading.value) return

  question.value = ''
  textareaKey.value += 1
  loading.value = true
  await nextTick()

  messages.value.push({
    id: ++nextMessageId,
    role: 'user',
    content: q,
    loading: false,
  })

  const assistantMsg = {
    id: ++nextMessageId,
    role: 'assistant',
    content: '',
    loading: true,
    streaming: true,
    answer: '',
    /** 流式过程中先视为有答案，避免 loading 结束后短暂出现「未找到」；最终以 done / error 为准 */
    found: true,
    sources: [],
    concepts: [],
    cache_hit: false,
    cache_key: '',
    elapsed: 0,
    cost: 0,
    request_id: '',
    question: q,
    verse: null,
    verses: null,
    queryType: null,
    bibleGenerating: false,
    intent: null,
    feedback: null,
    feedbackSubmitting: false,
    copied: false,
    /** 流式遇到「【引用书目】」后为 true，后续 token 不再入打字机队列 */
    _bodyDone: false,
    /** 翻译相关：currentLang 决定气泡显示哪种语言；translatedAnswers 缓存每种语言译文 */
    translatedAnswers: { zh_tw: null, en: null },
    currentLang: 'zh',
    translating: false,
    hasVerseData: false,
  }
  messages.value.push(assistantMsg)

  const assistantRow = () => {
    const i = messages.value.findIndex((m) => m.id === assistantMsg.id)
    return i !== -1 ? messages.value[i] : assistantMsg
  }

  await scrollToBottom()

  // 追问补全：若当前问题疑似追问（不含书名但含篇章词），用上一轮问题的书名补全
  let finalQuestion = q
  const lastTurn = history.value[history.value.length - 1]
  let hasChapter = false
  let hasBookName = false
  let isTooShort = false
  let bookMatch = null
  if (lastTurn) {
    hasChapter = /第?[零一二三四五六七八九十百千]+[篇章课]|第\d+[篇章课]/.test(finalQuestion)
    hasBookName =
      /文集|读经|训练|特会|总论|课程|福音|使徒|罗马|创世|出埃及|利未|民数|申命|约书亚|士师|路得|撒母耳|列王|历代|以斯|约伯|诗篇|箴言|传道|雅歌|以赛亚|耶利米|以西结|但以理|何西阿|约珥|阿摩司|俄巴底|约拿|弥迦|那鸿|哈巴谷|西番雅|哈该|撒迦利亚|玛拉基|马太|马可|路加|约翰|歌林多|加拉太|以弗所|腓利比|歌罗西|帖撒|提摩太|提多|腓利门|希伯来|雅各|彼得|犹大|启示/.test(
        finalQuestion,
      )
    isTooShort = finalQuestion.length <= 15
    if (hasChapter && !hasBookName && isTooShort) {
      const prevQ = lastTurn.question
      bookMatch = prevQ.match(/^(.+?)(?:第[零一二三四五六七八九十百千\d]+[篇章课]|的)/)
      if (bookMatch && bookMatch[1].length >= 4) {
        finalQuestion = bookMatch[1].trim() + finalQuestion
      }
    }
  }

  try {
    const sendTime = Date.now()
    let firstTokenReceived = false

    await navigator.locks.request('qa-stream', async () => {
      const token = localStorage.getItem('qa_token') || ''
      const response = await fetch('/api/qa/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          question: finalQuestion,
          skip_cache: false,
          debug: false,
          history: history.value.map((h) => ({
            question: h.question,
            answer: h.answer,
          })),
        }),
      })

      if (!response.ok) {
        if (response.status === 429) {
          await fetchDailyUsage()
          let detail = '今日问答次数已达上限，请明天再来'
          try {
            const errBody = await response.json()
            if (errBody.detail) detail = errBody.detail
          } catch {
            /* ignore */
          }
          const err = new Error(detail)
          err.status = 429
          throw err
        }
        throw new Error(`HTTP ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        buffer = buffer.replace(/\r\n/g, '\n')
        let sepIdx
        while ((sepIdx = buffer.indexOf('\n\n')) !== -1) {
          const rawEvent = buffer.slice(0, sepIdx)
          buffer = buffer.slice(sepIdx + 2)
          for (const line of rawEvent.split('\n')) {
            if (!line.startsWith('data:')) continue
            const raw = line.startsWith('data: ') ? line.slice(6).trim() : line.slice(5).trim()
            if (!raw) continue
            let chunk
            try {
              chunk = JSON.parse(raw)
            } catch {
              continue
            }
            if (chunk.type === 'verse_data') {
              const idx = messages.value.findIndex((m) => m.id === assistantMsg.id)
              if (idx !== -1) {
                const d = chunk.data
                messages.value[idx].intent = 'bible'
                messages.value[idx].bibleGenerating = true
                messages.value[idx].hasVerseData = true
                messages.value[idx].loading = false
                if (d && d.verses) {
                  messages.value[idx].verses = d.verses
                  messages.value[idx].queryType = d.query_type || 'chapter'
                  messages.value[idx].verse = null
                } else {
                  messages.value[idx].verse = d
                  messages.value[idx].verses = null
                  messages.value[idx].queryType = 'verse'
                }
              }
            } else if (chunk.type === 'token') {
              if (!firstTokenReceived) {
                firstTokenReceived = true
                const row = assistantRow()
                if (row) {
                  row.elapsed = ((Date.now() - sendTime) / 1000).toFixed(1)
                }
                // 经文问答不自动滚动，用户可能正在阅读经文区块
                if (row?.intent !== 'bible') {
                  await scrollToMessageTop(assistantMsg.id - 1)
                }
              }
              const idx = messages.value.findIndex((m) => m.id === assistantMsg.id)
              if (idx !== -1) {
                messages.value[idx].loading = false
              }
              const text = chunk.text || ''
              const row = assistantRow()
              if (row && row._bodyDone) {
                // 已进入书目区，不再打字
              } else if (row?.intent === 'bible') {
                let bodyText = text
                if (text.includes('【引用书目】')) {
                  bodyText = text.split('【引用书目】')[0]
                  if (row) row._bodyDone = true
                }
                for (const char of bodyText) {
                  typewriterQueue.value.push(char)
                }
                startTypewriter(assistantMsg)
              } else {
                let bodyText = text
                if (text.includes('【引用书目】')) {
                  bodyText = text.split('【引用书目】')[0]
                  if (row) row._bodyDone = true
                }
                for (const char of bodyText) {
                  typewriterQueue.value.push(char)
                }
                startTypewriter(assistantMsg)
              }
            } else if (chunk.type === 'done') {
              await new Promise((resolve) => {
                const wait = setInterval(() => {
                  if (typewriterQueue.value.length === 0) {
                    clearInterval(wait)
                    resolve()
                  }
                }, 50)
              })
              stopTypewriter()
              const row = assistantRow()
              row.found = chunk.found ?? true
              if (!row.answer) {
                row.answer = chunk.answer || ''
              }
              row.sources = chunk.sources || []
              row.concepts = chunk.concepts || []
              row.cache_hit = chunk.cache_hit ?? false
              row.cache_key = chunk.cache_key || ''
              row.request_id = chunk.request_id || ''
              if (!firstTokenReceived) {
                row.elapsed = ((chunk.elapsed_ms || 0) / 1000).toFixed(1)
              }
              row.cost = chunk.cost || 0
              row.loading = false
              row.streaming = false
              row.bibleGenerating = false
              incrementDailyUsageLocal()
            } else if (chunk.type === 'error') {
              stopTypewriter()
              const row = assistantRow()
              row.bibleGenerating = false
              row.answer = '请求失败，请稍后重试。'
              row.found = false
              row.loading = false
              row.streaming = false
            }
          }
        }
      }
    })
  } catch (e) {
    stopTypewriter()
    const r = assistantRow()
    r.bibleGenerating = false
    if (e?.status === 429) {
      await fetchDailyUsage()
      message.warning(e.message || '今日问答次数已达上限，请明天再来')
      r.found = false
      r.answer = e.message || '今日问答次数已达上限，请明天再来'
      r.loading = false
      r.streaming = false
    } else if (firstTokenReceived) {
      // 已有内容输出，连接中断但答案部分可用，保留已有内容
      r.found = r.found ?? true
      r.loading = false
      r.streaming = false
    } else {
      // 完全没收到任何内容，显示报错
      r.found = false
      r.answer = '请求失败，请稍后重试。'
    }
  } finally {
    stopTypewriter()
    const r = assistantRow()
    r.loading = false
    r.streaming = false
    r.bibleGenerating = false
    loading.value = false
    question.value = ''
    // 存补全后的问句，便于下一轮从 history 提取书名再做追问补全（气泡仍用上面的 q）
    history.value.push({
      question: finalQuestion,
      answer: r.answer || '',
    })
    history.value = history.value.slice(-3)
    await nextTick()
  }
}

async function submitFeedback(msg, rating) {
  if (!msg || msg.feedback !== null || msg.feedbackSubmitting) return
  const token = localStorage.getItem('qa_token') || ''
  if (!token) return

  msg.feedbackSubmitting = true
  try {
    const res = await fetch('/api/qa/feedback', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        request_id: msg.request_id || '',
        question: msg.question || '',
        answer: msg.answer || '',
        rating,
      }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    msg.feedback = rating
  } catch (e) {
    console.error('submit feedback failed', e)
  } finally {
    msg.feedbackSubmitting = false
  }
}

async function copyAnswer(msg) {
  if (!msg || msg.copied) return
  try {
    const rawAnswer = displayAnswer(msg)
    const srcs = displaySources(msg)
    const cleanAnswer = stripAnswerPlain(rawAnswer || '')
    const sourcesHeader = msg.currentLang === 'en' ? 'References' : '【引用书目】'
    const sourcesText = srcs && srcs.length
      ? `\n\n${sourcesHeader}\n` + srcs.join('\n')
      : ''
    const fullText = cleanAnswer + sourcesText
    await navigator.clipboard.writeText(fullText)
    msg.copied = true
    setTimeout(() => {
      msg.copied = false
    }, 1500)
  } catch (e) {
    console.error('copy answer failed', e)
  }
}

async function scrollToBottom() {
  await nextTick()
  if (historyRef.value) {
    historyRef.value.scrollTop = historyRef.value.scrollHeight
  }
}

function setMessageRef(id, el) {
  if (el) {
    messageRefMap.set(id, el)
  } else {
    messageRefMap.delete(id)
  }
}

async function scrollToMessageTop(messageId) {
  await nextTick()
  const el = messageRefMap.get(messageId)
  if (el && typeof el.scrollIntoView === 'function') {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}
</script>

<style lang="less" scoped>
.qa-root {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--color-bg);
}

/* 页头 */
.qa-header {
  flex-shrink: 0;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface);
}
.qa-header-inner {
  max-width: min(860px, 90vw);
  margin: 0 auto;
  padding: 14px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.qa-header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.qa-daily-usage {
  font-size: 13px;
  color: var(--color-text-secondary);
  white-space: nowrap;
  user-select: none;
}
.qa-daily-usage--warn {
  color: #e6a23c;
}
.qa-daily-usage--danger {
  color: #f5222d;
}
.qa-new-chat-btn {
  border: 1px solid var(--color-border);
  background: #fff;
  border-radius: 16px;
  padding: 4px 12px;
  font-size: 13px;
  color: var(--color-text-secondary);
  cursor: pointer;
  line-height: 1.5;
  transition: border-color 0.2s, color 0.2s, background 0.2s;
  &:hover {
    border-color: var(--color-primary);
    color: var(--color-primary);
    background: #fdf8ee;
  }
}
.qa-logo {
  display: flex;
  align-items: center;
  gap: 8px;
}
.qa-logo-text {
  font-size: 30px;
  font-weight: 400;
  color: var(--color-primary);
  letter-spacing: 0.05em;
  font-family: 'KaiTi', 'Kaiti SC', 'STKaiti', serif;
}
.qa-user-avatar {
  cursor: pointer;
  background-color: #8b6914;
  user-select: none;
}
:deep(.qa-logout-item) {
  color: #ff4d4f;
}

/* 主体：中间可滚动 */
.qa-main {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 24px;
}

/* 欢迎区 */
.qa-welcome {
  max-width: 600px;
  margin: 60px auto 0;
  text-align: center;
}
.qa-welcome-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 8px;
}
.qa-welcome-sub {
  font-size: 13px;
  color: #a8a39c;
  font-style: italic;
  margin-bottom: 32px;
}
.qa-example-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: center;
}
.qa-example-chip {
  padding: 8px 16px;
  border: 1px solid var(--color-border);
  border-radius: 20px;
  font-size: 13px;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.2s;
  background: var(--color-surface);
  &:hover {
    border-color: var(--color-primary);
    color: var(--color-primary);
    background: #fdf8ee;
  }
}

/* 对话流 */
.qa-chat {
  max-width: min(860px, 90vw);
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-bottom: 8px;
}

.qa-msg-row {
  display: flex;
  width: 100%;
}
.qa-msg-row--user {
  justify-content: flex-end;
}
.qa-msg-row--assistant {
  justify-content: flex-start;
}

/* 气泡 */
.qa-bubble {
  border-radius: var(--radius);
  padding: 14px 18px;
  line-height: 1.8;
  font-size: 15px;
}
.qa-bubble-user {
  max-width: 78%;
  background: var(--color-primary);
  color: #fff;
  border-bottom-right-radius: 2px;
  word-break: break-word;
}
.qa-bubble-assistant {
  max-width: 92%;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow);
  border-bottom-left-radius: 2px;
  word-break: break-word;
}

/* 加载 */
.qa-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--color-text-secondary);
}
.qa-loading-text { font-size: 14px; }
.qa-loading--after-verse {
  margin-top: 12px;
}

/* 未找到 */
.qa-not-found {
  color: var(--color-text-secondary);
  font-size: 14px;
}
.qa-not-found-icon { margin-right: 6px; }

/* 答案正文 */
.qa-answer-body {
  color: var(--color-text);
  margin-bottom: 12px;
}
.qa-answer-body :deep(.qa-cite-num) {
  font-size: 10px;
  vertical-align: super;
  color: var(--color-text-secondary);
  margin-left: 1px;
}

/* 引用书目 */
.qa-sources {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border);
}
.qa-sources-title {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-bottom: 6px;
  font-weight: 600;
  letter-spacing: 0.05em;
}
.qa-sources-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}
.qa-source-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 4px 0;
  border-bottom: 1px solid var(--color-border);
  &:last-child { border-bottom: none; }
}
.qa-source-name {
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

/* 元信息 */
.qa-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
}
.qa-meta-badge {
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 10px;
  font-weight: 600;
}
.qa-meta-cache {
  background: #e6f4ff;
  color: #1677ff;
}
.qa-meta-time, .qa-meta-cost {
  font-size: 11px;
  color: var(--color-text-secondary);
}

.qa-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}
.qa-actions-row1 {
  display: flex;
  align-items: center;
  gap: 8px;
}
.qa-feedback-btn {
  border: 1px solid var(--color-border);
  background: #fff;
  border-radius: 14px;
  padding: 2px 10px;
  cursor: pointer;
  font-size: 14px;
  line-height: 1.6;
  transition: all 0.2s;
}
.qa-feedback-btn.is-selected {
  border-color: var(--color-primary);
  background: #f5ead2;
  color: #7a5a0f;
}
.qa-feedback-btn.is-muted {
  opacity: 0.45;
}
.qa-feedback-btn:disabled {
  cursor: not-allowed;
}
.qa-copy-btn {
  min-width: 84px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

/* 答案下方：语言组 + 朗读按钮（同排、分组分离） */
.qa-action-row2 {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}
.qa-lang-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--color-border);
  border-radius: 20px;
  overflow: hidden;
  background: #fff;
  align-self: flex-start;
}
.qa-tts-btn {
  flex-shrink: 0;
  background: none;
  border: 1px solid #d9d9d9;
  border-radius: 16px;
  padding: 2px 10px;
  font-size: 15px;
  cursor: pointer;
  color: #666;
  transition: background 0.15s;
}
.qa-tts-btn:hover:not(:disabled) {
  background: #f5f5f5;
}
.qa-tts-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.qa-tts-btn--google {
  margin-left: 4px;
  color: var(--color-primary);
}
.qa-tts-btn--minimax {
  margin-left: 4px;
  color: var(--color-primary);
  opacity: 0.85;
}
.qa-tts-btn--elevenlabs {
  margin-left: 4px;
  color: var(--color-primary);
  opacity: 0.85;
}
.qa-lang-toggle-btn {
  border: none;
  background: transparent;
  padding: 6px 18px;
  font-size: 14px;
  color: var(--color-text-secondary);
  cursor: pointer;
  line-height: 1.6;
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, color 0.15s;
  &:not(:last-child) {
    border-right: 1px solid var(--color-border);
  }
  &:hover:not(:disabled):not(.is-active) {
    background: #faf5ea;
    color: var(--color-primary);
  }
  &.is-active {
    background: #f5ead2;
    color: #7a5a0f;
    font-weight: 600;
  }
  &:disabled {
    cursor: not-allowed;
  }
}

/* 切换语言时正文淡入 */
.qa-answer-fade {
  animation: qa-answer-fadein 0.2s ease;
}
@keyframes qa-answer-fadein {
  from { opacity: 0; }
  to   { opacity: 1; }
}

/* 免责说明 */
.qa-disclaimer {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--color-border);
  font-size: 12px;
  color: var(--color-disclaimer);
  font-style: italic;
}

/* 输入区 */
.qa-footer {
  flex-shrink: 0;
  border-top: 1px solid var(--color-border);
  background: var(--color-surface);
  padding: 16px 24px 20px;
}
.qa-input-wrap {
  max-width: min(860px, 90vw);
  margin: 0 auto;
  display: flex;
  flex-direction: row;
  gap: 8px;
  align-items: center;
}
.qa-textarea {
  flex: 1;
  min-width: 0;
  border-radius: var(--radius) !important;
  font-family: inherit !important;
  font-size: 15px !important;
  resize: none;
}
.qa-submit-btn {
  height: 40px;
  min-width: 80px;
  padding: 0 18px;
  border-radius: var(--radius) !important;
  font-size: 16px;
  font-weight: 600;
  flex-shrink: 0;
  align-self: center;
  margin-bottom: 0;
}
.qa-mic-btn {
  flex-shrink: 0;
  align-self: center;
  margin-bottom: 0;
  background: #fff1f0;
  border: none;
  border-radius: 50%;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  padding: 0;
  color: #ff4d4f;
  transition: background 0.2s;
}
.qa-mic-btn:hover {
  background: #ffd6d6;
}
.qa-mic-btn.active {
  background: #ffd6d6;
  color: #ff4d4f;
}
.qa-mic-btn.recording {
  background: #fff1f0;
  color: #ff4d4f;
  animation: mic-pulse 1s ease-in-out infinite;
}
.qa-mic-btn.processing { color: #bbb; cursor: default; }
.qa-voice-area {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.qa-press-btn {
  width: 100%;
  height: 40px;
  border-radius: 20px;
  border: 1.5px solid #d9d9d9;
  background: #fafafa;
  font-size: 15px;
  color: #555;
  cursor: pointer;
  transition: all 0.15s;
  user-select: none;
  -webkit-user-select: none;
}
.qa-press-btn.pressing {
  background: #fff1f0;
  border-color: #ff4d4f;
  color: #ff4d4f;
  transform: scale(0.98);
}
.qa-press-btn.processing {
  background: #fafafa;
  color: #aaa;
  cursor: default;
}
.qa-press-btn:not(.pressing):not(.processing):hover {
  border-color: #aaa;
  background: #f0f0f0;
}
.qa-recording-panel {
  background: #fff;
  border: 1px solid #ffa39e;
  border-radius: 12px;
  padding: 12px 16px;
  margin-bottom: 8px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  animation: recording-fadein 0.2s ease;
}
@keyframes recording-fadein {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}
.qa-recording-top {
  display: flex;
  align-items: center;
  gap: 8px;
}
.qa-recording-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #ff4d4f;
  animation: mic-pulse 1s ease-in-out infinite;
  flex-shrink: 0;
}
.qa-recording-label {
  font-size: 14px;
  color: #ff4d4f;
  font-weight: 500;
  flex: 1;
}
.qa-recording-timer {
  font-size: 14px;
  color: #888;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.05em;
}
.qa-recording-tip {
  font-size: 12px;
  color: #888;
  line-height: 1.5;
}
.qa-recording-wave {
  display: flex;
  align-items: center;
  gap: 3px;
  height: 36px;
  padding: 0 2px;
}
.qa-wave-bar {
  width: 4px;
  border-radius: 2px;
  background: #ff4d4f;
  transition: height 0.08s ease;
  min-height: 3px;
}
@keyframes mic-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.qa-input-hint {
  max-width: min(860px, 90vw);
  margin: 6px auto 0;
  font-size: 11px;
  color: var(--color-text-secondary);
  text-align: right;
}

@media (max-width: 768px) {
  /* 顶栏固定：与底栏输入区对称，中间主区域单独滚动 */
  .qa-header {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 101;
    background: var(--color-surface);
    border-bottom: 1px solid var(--color-border);
    /* 刘海屏安全区 */
    padding-top: env(safe-area-inset-top, 0px);
  }

  .qa-header-inner {
    padding: 10px 16px;
    min-height: 48px;
    box-sizing: border-box;
  }

  .qa-logo-text {
    font-size: 22px;
    line-height: 1.25;
  }

  .qa-footer {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    z-index: 100;
    background: var(--color-bg);
    padding: 12px 16px;
    padding-bottom: calc(12px + env(safe-area-inset-bottom, 0px));
    border-top: 1px solid var(--color-border);
  }

  /*
   * 主区域预留：必须 ≥ 实际固定顶栏/底栏高度，否则首尾文字会被遮住。
   * 底栏含多行输入时会变高，故底部留白加大并用 min 兜底。
   */
  .qa-main {
    box-sizing: border-box;
    padding-left: 16px;
    padding-right: 16px;
    padding-top: calc(12px + env(safe-area-inset-top, 0px) + 56px);
    padding-bottom: calc(max(140px, 32vh) + env(safe-area-inset-bottom, 0px));
    scroll-padding-top: calc(8px + env(safe-area-inset-top, 0px) + 56px);
    scroll-padding-bottom: calc(max(140px, 32vh) + env(safe-area-inset-bottom, 0px));
  }

  /* 欢迎区原先 margin-top 较大，与顶栏留白叠加后首屏过空，略收紧 */
  .qa-welcome {
    margin-top: 24px;
  }
}
</style>

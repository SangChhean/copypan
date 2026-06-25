/**
 * 启动 JSDOM 环境，加载 data/ 全部数据文件和 scripts.js
 * 最大化复用现有搜索逻辑，不重写
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { JSDOM } = require('jsdom');
const Fuse = require('fuse.js');
const { parseSearchItems } = require('./search_parse');


const DATA_DIR = process.env.DATA_DIR
  || path.resolve(__dirname, '../data');

const HTML_SHELL = `<!DOCTYPE html><html><body>
  <div id="history" class="history"></div>
  <textarea id="user-input"></textarea>
  <button id="send-button"></button>
  <button id="voice-button"></button>
  <button id="category-toggle"></button>
  <div id="category-options" class="hidden">
    <button data-category="诗歌"></button>
    <button data-category="经节"></button>
    <button data-category="注解"></button>
    <button data-category="职事信息"></button>
    <button data-category="问答"></button>
  </div>
  <div id="infoModal" class="modal"></div>
</body></html>`;

const DATA_FILES = [
  'traditional_to_simplified.js',
  'simplified_to_traditional.js',
  'qu-bie-ci-exclusion-map.js',
  'hymns.js',
  'shi_ge.js',
  'zhu_jie_wen_da.js',
  'cha_kan_zheng_pian.js',
  'jing_jie_wen_da.js',
  'xiao_bai_ke.js',
  'bible_verse.js',
  'private/1_zhi_shi_xin_xi.js',
  'jing_jie_zhu_shi.js',
];

function resolveDataPath(relativePath) {
  return path.join(DATA_DIR, relativePath);
}

function loadScriptFile(domWindow, filePath) {
  const code = fs.readFileSync(filePath, 'utf8');
  domWindow.eval(code);
}

function createFetchMock() {
  return async function fetchMock(url, options) {
    let rel = String(url);
    if (rel.startsWith('http://') || rel.startsWith('https://')) {
      throw new Error(`External fetch not supported: ${rel}`);
    }
    rel = rel.replace(/^\//, '').split('?')[0];
    const filePath = resolveDataPath(rel);
    if (!fs.existsSync(filePath)) {
      return { ok: false, status: 404, json: async () => ({}), text: async () => '' };
    }
    const content = fs.readFileSync(filePath, 'utf8');
    const contentType = rel.endsWith('.json') ? 'application/json' : 'text/html';
    return {
      ok: true,
      status: 200,
      headers: { get: (h) => (h === 'content-type' ? contentType : null) },
      json: async () => JSON.parse(content),
      text: async () => content,
    };
  };
}

let _env = null;

async function setupEnvironment() {
  if (_env) return _env;

  console.log(`[bootstrap] DATA_DIR = ${DATA_DIR}`);
  const dom = new JSDOM(HTML_SHELL, {
    url: 'http://localhost/',
    pretendToBeVisual: true,
    runScripts: 'outside-only',
  });

  const { window } = dom;
  const capturedMessages = [];

  window.Fuse = Fuse;
  window.fetch = createFetchMock();
  window.selectedLang = 'zh-CN';
  window.selectedCategory = null;

  // 无 UI 副作用的桩函数
  window.showLoading = () => {};
  window.removeLoading = () => {};
  window.scrollToBottom = () => {};
  window.appendCopyButton = () => {};
  window.appendReadButtonToMessageContent = () => {};
  window.appendRegenerateButton = () => {};
  window.alert = (msg) => console.warn('[alert]', msg);

  for (const file of DATA_FILES) {
    const fp = resolveDataPath(file);
    if (!fs.existsSync(fp)) {
      throw new Error(`Missing data file: ${fp}`);
    }
    console.log(`[bootstrap] loading ${file}`);
    loadScriptFile(window, fp);
  }

  const scriptsPath = resolveDataPath('scripts.js');
  console.log('[bootstrap] loading scripts.js');
  loadScriptFile(window, scriptsPath);

  // 拦截 appendMessage，收集结果；Bot/API 路径也做繁体展示
  window.appendMessage = async function patchedAppend(sender, message, originalUserInput) {
    let out = message;
    if (sender !== '用户' && typeof window.maybeToTraditional === 'function') {
      out = window.maybeToTraditional(out);
    }
    capturedMessages.push({ sender, message: out, originalUserInput });
  };

  // 弹窗展示改为写入搜索结果（注解 HTML、图表等）
  window.showHymnModalRaw = function patchedShowHymnModalRaw(title, content) {
    const safeTitle = String(title || '').trim();
    let safeContent = String(content || '');
    if (typeof window.extractChatHTMLContent === 'function') {
      safeContent = window.extractChatHTMLContent(safeContent);
    }
    window.appendMessage('AI', `<strong>${safeTitle}</strong>\n${safeContent}`);
  };

  _env = {
    window,
    document: window.document,
    capturedMessages,
    resetCapture() {
      capturedMessages.length = 0;
    },
    async search(query, category = null, lang = 'zh-CN') {
      capturedMessages.length = 0;
      if (typeof window.__setSelectedCategory === 'function') {
        window.__setSelectedCategory(category || null);
      } else {
        window.selectedCategory = category || null;
      }
      window.selectedLang = lang;
      const raw = String(query || '').trim();
      window.lastUserRawInput = raw;
      if (typeof window.isTraditionalText === 'function') {
        window.userInputWasTraditional = window.isTraditionalText(raw) || lang === 'zh-TW';
      } else {
        window.userInputWasTraditional = lang === 'zh-TW';
      }

      const userInput = window.document.getElementById('user-input');
      const sendButton = window.document.getElementById('send-button');
      userInput.value = raw;

      await window.sendMessage();

      sendButton.disabled = false;

      const userMsgs = capturedMessages.filter((m) => m.sender === '用户');
      const aiMsgs = capturedMessages.filter((m) => m.sender === 'AI');

      const lastAi = aiMsgs.length > 0 ? aiMsgs[aiMsgs.length - 1].message : null;
      const notFoundPatterns = [
        '暂时未找到',
        '未找到您要的答案',
        '未找到',
        '所有优先级都未找到',
        '在诗歌分类中未找到',
      ];
      const found = !!lastAi && !notFoundPatterns.some((p) => lastAi.includes(p));

      return {
        found,
        message: lastAi,
        items: found && lastAi ? parseSearchItems(lastAi, 20) : [],
        query: userMsgs[0]?.message || query,
        category: category || null,
        lang: window.userInputWasTraditional ? 'zh-TW' : 'zh-CN',
      };
    },
  };

  console.log('[bootstrap] environment ready');
  return _env;
}

module.exports = { setupEnvironment, DATA_DIR };

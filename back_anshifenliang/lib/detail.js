const fs = require('fs');
const path = require('path');

const { DATA_DIR } = require('./bootstrap');

/** API/机器人用：只取 body 正文，不含 style/script，保留注解上标样式 */
function fixRecoveryBibleGlyphCorruption(text) {
  if (!text || typeof text !== 'string' || !text.includes('\uFFFD')) return text;
  const map = { k: '祂', q: '痲', F: '镕', Z: '繸', m: '醡' };
  return text.replace(/\uFFFD(.)/g, (match, ch) => map[ch] || match);
}

function readHtmlBodyForApi(html, w) {
  if (w && typeof w.extractChatHTMLContent === 'function') {
    return w.extractChatHTMLContent(html);
  }
  const bodyMatch = html.match(/<body[^>]*>([\s\S]*)<\/body>/i);
  let content = bodyMatch ? bodyMatch[1] : html;
  return fixRecoveryBibleGlyphCorruption(content
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .trim());
}

function matchHymnKey(dict, title) {
  if (dict[title]) return title;
  const keys = Object.keys(dict);
  let matched = keys.find((k) => k.includes(title));
  if (matched) return matched;
  matched = keys.find((k) => title.includes(k));
  if (matched) return matched;
  const cleanTitle = title.replace(/[^\u4e00-\u9fa5\d]/g, '');
  return keys.find((k) => {
    const cleanKey = k.replace(/[^\u4e00-\u9fa5\d]/g, '');
    return cleanKey.includes(cleanTitle) || cleanTitle.includes(cleanKey);
  }) || null;
}

function getDetailFromEnv(searchEnv, source, title, lang = 'zh-CN') {
  const w = searchEnv.window;
  w.selectedLang = lang;
  const useTraditional = lang === 'zh-TW';

  let lookupTitle = title;
  if (typeof w.convertTraditionalToSimplified === 'function') {
    lookupTitle = w.convertTraditionalToSimplified(title);
  }

  if (source === 'catalog') {
    return null;
  }

  if (source === 'foo_jie_single') {
    const { getFootnoteByTitle } = require('./foo_jie_single');
    const footnote = getFootnoteByTitle(lookupTitle);
    if (!footnote) return null;
    return applyTraditionalToDetail({
      title: footnote.title,
      source,
      content: footnote.content,
    }, w, useTraditional);
  }

  if (source === 'zhu_jie_html') {
    const indexPath = path.join(DATA_DIR, 'private/zhu_jie_html/2_index.json');
    if (!fs.existsSync(indexPath)) return null;
    const index = JSON.parse(fs.readFileSync(indexPath, 'utf8'));
    const fileName = index[lookupTitle];
    if (!fileName) return null;
    const htmlPath = path.join(DATA_DIR, 'private/zhu_jie_html', fileName);
    if (!fs.existsSync(htmlPath)) return null;
    const html = fs.readFileSync(htmlPath, 'utf8');
    const content = readHtmlBodyForApi(html, w);
    return applyTraditionalToDetail({ title: lookupTitle, source, content }, w, useTraditional);
  }

  if (source === 'jing_wen_with_index') {
    const indexPath = path.join(DATA_DIR, 'private/jing_wen_html/2_index.json');
    if (!fs.existsSync(indexPath)) return null;
    const index = JSON.parse(fs.readFileSync(indexPath, 'utf8'));
    const fileName = index[lookupTitle];
    if (!fileName) return null;
    const htmlPath = path.join(DATA_DIR, 'private/jing_wen_html', fileName);
    if (!fs.existsSync(htmlPath)) return null;
    const html = fs.readFileSync(htmlPath, 'utf8');
    const content = readHtmlBodyForApi(html, w);
    return applyTraditionalToDetail({ title: lookupTitle, source, content }, w, useTraditional);
  }

  if (source && source.startsWith('private/')) {
    const filePath = path.join(DATA_DIR, source);
    if (!fs.existsSync(filePath)) return null;
    const html = fs.readFileSync(filePath, 'utf8');
    const content = readHtmlBodyForApi(html, w);
    return applyTraditionalToDetail({ title: lookupTitle, source, content }, w, useTraditional);
  }

  const dictMap = {
    hymns: w.hymns,
    shi_ge: w.shi_ge,
    zhu_jie_wen_da: w.zhu_jie_wen_da,
    jing_jie_wen_da: w.jing_jie_wen_da,
    bible_verse: w.bibleVerse,
    xiao_bai_ke: w.xiao_bai_ke,
  };

  const dict = dictMap[source];
  if (!dict || typeof dict !== 'object') return null;

  let matchedKey = lookupTitle;
  if (source === 'hymns') {
    matchedKey = matchHymnKey(dict, lookupTitle);
    if (!matchedKey) return null;
  } else if (!dict[matchedKey]) {
    matchedKey = Object.keys(dict).find((k) => k === lookupTitle || k.includes(lookupTitle) || lookupTitle.includes(k));
    if (!matchedKey) return null;
  }

  const raw = dict[matchedKey];
  if (!raw) return null;

  const content = typeof w.formatMessage === 'function' ? w.formatMessage(raw) : raw;
  return applyTraditionalToDetail({ title: matchedKey, source, content }, w, useTraditional);
}

function applyTraditionalToDetail(detail, w, useTraditional) {
  if (!detail || !useTraditional || typeof w.convertToTraditional !== 'function') {
    return detail;
  }
  return {
    ...detail,
    title: w.convertToTraditional(detail.title),
    content: w.convertToTraditional(detail.content),
  };
}

module.exports = { getDetailFromEnv, applyTraditionalToDetail };

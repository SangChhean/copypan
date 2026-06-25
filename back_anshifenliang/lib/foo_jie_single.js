const fs = require('fs');
const path = require('path');

const { DATA_DIR } = require('./bootstrap');

const FOO_DIR = path.join(DATA_DIR, 'private/foo_jie_single');
const FILES_DIR = path.join(FOO_DIR, 'files');

let titleIndex = null;
let contentIndex = null;

function loadIndexes() {
  if (titleIndex) return { titleIndex, contentIndex };

  const titlePath = path.join(FOO_DIR, 'title_index.json');
  const contentPath = path.join(FOO_DIR, 'content_index.json');

  if (!fs.existsSync(titlePath)) {
    titleIndex = {};
    contentIndex = [];
    return { titleIndex, contentIndex };
  }

  titleIndex = JSON.parse(fs.readFileSync(titlePath, 'utf8'));
  contentIndex = fs.existsSync(contentPath)
    ? JSON.parse(fs.readFileSync(contentPath, 'utf8'))
    : [];

  return { titleIndex, contentIndex };
}

function lookupTitle(title) {
  const { titleIndex: idx } = loadIndexes();
  if (!title) return null;
  const t = title.trim();
  return idx[t] || idx[`恢复本圣经　${t}`] || null;
}

function readFootnoteHtml(fileName) {
  const filePath = path.join(FILES_DIR, fileName);
  if (!fs.existsSync(filePath)) return null;
  const raw = fs.readFileSync(filePath, 'utf8');
  try {
    const parsed = JSON.parse(raw);
    return typeof parsed === 'string' ? parsed : null;
  } catch {
    return raw;
  }
}

function getFootnoteByTitle(title) {
  const fileName = lookupTitle(title);
  if (!fileName) return null;
  const content = readFootnoteHtml(fileName);
  if (!content) return null;

  const h3 = content.match(/<h3[^>]*>([\s\S]*?)<\/h3>/i);
  const displayTitle = h3
    ? h3[1].replace(/<[^>]+>/g, '').trim()
    : title;

  return { title: displayTitle, content, file: fileName };
}

function searchFootnoteContent(query, limit = 20) {
  const { contentIndex: rows } = loadIndexes();
  const q = String(query || '').trim();
  if (!q || q.length < 2) return [];

  const hits = [];
  for (const row of rows) {
    if (row.text && row.text.includes(q)) {
      hits.push(row);
      if (hits.length >= limit) break;
    }
  }
  return hits;
}

function isReady() {
  return fs.existsSync(path.join(FOO_DIR, 'title_index.json'));
}

module.exports = {
  loadIndexes,
  lookupTitle,
  getFootnoteByTitle,
  searchFootnoteContent,
  isReady,
  FOO_DIR,
};
